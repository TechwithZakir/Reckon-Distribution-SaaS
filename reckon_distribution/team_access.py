from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import nowdate

from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
)
from reckon_distribution.warehouse import sync_user_company_permission

ROLE_MAP = {
    "Company Admin": "Reckon Distribution Admin",
    "Company Manager": "Reckon Distribution Manager",
    "Master Data Manager": "Reckon Master Data Manager",
    "SR": "Reckon Distribution User",
    "DSR": "Reckon Distribution User",
}
MANAGER_ROLES = {"Reckon Distribution Admin", "Reckon Distribution Manager"}


@frappe.whitelist()
def get_team_companies() -> dict:
    _require_manager()
    if user_can_bypass_tenant():
        return {"locked": False, "companies": frappe.get_all("Company", fields=["name"])}
    tenant = require_tenant()
    return {"locked": True, "companies": [{"name": tenant.company}]}


@frappe.whitelist()
def list_team(company: str | None = None) -> list[dict]:
    tenant = require_tenant(company=company)
    _require_manager()
    return frappe.db.sql(
        """
        select name, user, role_profile, active, is_default, valid_from, valid_to, route_scope
        from `tabTenant User Assignment`
        where company = %s
        order by active desc, user asc
        """,
        tenant.company,
        as_dict=True,
    )


@frappe.whitelist()
def create_team_access(payload: str | dict) -> str:
    data = frappe.parse_json(payload) if isinstance(payload, str) else payload
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    profile = data.get("role_profile")
    password = data.get("password") or ""
    password_confirm = data.get("password_confirm") or ""
    if not email or "@" not in email or not full_name:
        frappe.throw(_("Full name and a valid email are required."))
    if profile not in ROLE_MAP:
        frappe.throw(_("Select a valid Company role."))
    if not password:
        frappe.throw(_("Set a password for the new team member."))
    _validate_password_pair(password, password_confirm)
    _assert_manageable_user(email, tenant.company)
    _validate_route(data.get("route"), tenant.company)

    user = _get_or_create_user(email, full_name, ROLE_MAP[profile], password)
    existing = frappe.db.get_value(
        "Tenant User Assignment",
        {"user": user.name, "company": tenant.company},
        "name",
    )
    if existing:
        assignment = frappe.get_doc("Tenant User Assignment", existing)
        assignment.role_profile = profile
        assignment.active = 1
        assignment.route_scope = data.get("route") or ""
        assignment.valid_from = data.get("valid_from") or nowdate()
        assignment.save(ignore_permissions=True)
    else:
        assignment = frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": user.name,
                "company": tenant.company,
                "role_profile": profile,
                "active": 1,
                "is_default": not frappe.db.exists(
                    "Tenant User Assignment", {"user": user.name, "active": 1, "is_default": 1}
                ),
                "valid_from": data.get("valid_from") or nowdate(),
                "route_scope": data.get("route") or "",
                "notes": _("Created from Company Team & Access guide."),
            }
        )
        assignment.insert(ignore_permissions=True)
    sync_user_company_permission(user.name, expected_company=tenant.company)
    _ensure_role(user, ROLE_MAP[profile])
    return assignment.name


@frappe.whitelist()
def deactivate_team_access(assignment: str) -> str:
    doc = get_tenant_doc("Tenant User Assignment", assignment)
    _require_manager()
    _assert_manageable_user(doc.user, doc.company)
    doc.active = 0
    doc.is_default = 0
    doc.save(ignore_permissions=True)
    sync_user_company_permission(doc.user)
    return doc.name


@frappe.whitelist()
def update_team_access(payload: str | dict) -> str:
    data = frappe.parse_json(payload) if isinstance(payload, str) else payload
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    assignment = get_tenant_doc("Tenant User Assignment", data.get("name"))
    if assignment.company != tenant.company:
        frappe.throw(_("This team member belongs to another Company."), frappe.PermissionError)
    _assert_manageable_user(assignment.user, tenant.company)
    _validate_route(data.get("route"), tenant.company)
    if data.get("role_profile") not in ROLE_MAP:
        frappe.throw(_("Select a valid Company role."))
    assignment.role_profile = data["role_profile"]
    assignment.route_scope = data.get("route") or ""
    assignment.active = 1 if data.get("active", True) else 0
    assignment.save(ignore_permissions=True)
    sync_user_company_permission(
        assignment.user, expected_company=tenant.company if assignment.active else None
    )
    user = frappe.get_doc("User", assignment.user)
    password = data.get("password") or ""
    password_confirm = data.get("password_confirm") or ""
    if password:
        _validate_password_pair(password, password_confirm)
        _set_password(user, password)
    _ensure_role(user, ROLE_MAP[assignment.role_profile])
    return assignment.name


def _validate_route(route: str | None, company: str) -> None:
    if route and not frappe.db.exists("Distribution Route", {"name": route, "company": company, "active": 1}):
        frappe.throw(_("Select an active route belonging to your Company."), frappe.PermissionError)


def _assert_manageable_user(user: str, company: str) -> None:
    if user_can_bypass_tenant() or not frappe.db.exists("User", user):
        return
    if user_can_bypass_tenant(user):
        frappe.throw(_("Platform administrators cannot be managed as team members."), frappe.PermissionError)
    assignments = frappe.get_all("Tenant User Assignment", filters={"user": user}, pluck="company")
    if not assignments or set(assignments) != {company}:
        frappe.throw(_("This existing user cannot be managed by your Company."), frappe.PermissionError)


def _get_or_create_user(email: str, full_name: str, role: str | None = None, password: str | None = None):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": full_name,
            "full_name": full_name,
            "user_type": "System User",
            "send_welcome_email": 0,
            "enabled": 1,
            "roles": [{"role": role}] if role else [],
            "new_password": password or "",
        }
    )
    user.insert(ignore_permissions=True)
    return user


def _ensure_role(user, role: str) -> None:
    if role not in frappe.get_roles(user.name):
        user.add_roles(role)
    frappe.clear_cache(user=user.name)


def _set_password(user, password: str) -> None:
    user.new_password = password
    user.save(ignore_permissions=True)


def _validate_password_pair(password: str, password_confirm: str) -> None:
    if password != password_confirm:
        frappe.throw(_("Password and confirmation do not match."))
    if len(password) < 8:
        frappe.throw(_("Password must be at least 8 characters."))


def _require_manager() -> None:
    if user_can_bypass_tenant() or MANAGER_ROLES.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Company Admin or Company Manager access is required."), frappe.PermissionError)
