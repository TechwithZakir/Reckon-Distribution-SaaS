from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant


def validate_warehouse(doc, method=None) -> None:
    """Keep native ERPNext Warehouse records inside the active tenant Company."""
    if user_can_bypass_tenant():
        return

    tenant = require_tenant()
    if not doc.company:
        doc.company = tenant.company
    if doc.company != tenant.company:
        frappe.throw(
            _("This Distribution Warehouse must belong to your Company: {0}.").format(tenant.company),
            frappe.PermissionError,
        )


def get_company_query(user=None, doctype=None) -> str:
    """Restrict Company link/list lookups to the active tenant Company."""
    if user_can_bypass_tenant(user):
        return ""
    tenant = require_tenant(user=user)
    return f"`tabCompany`.`name` = {frappe.db.escape(tenant.company)}"


def has_company_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    if user_can_bypass_tenant(user):
        return True
    tenant = require_tenant(user=user)
    return bool(doc and doc.name == tenant.company)


@frappe.whitelist()
def get_children(
    doctype, parent=None, company=None, is_root=False, include_disabled=False, **kwargs
):
    """Use the server tenant Company for the native Warehouse Tree."""
    from erpnext.stock.doctype.warehouse.warehouse import get_children as erpnext_get_children

    if not user_can_bypass_tenant():
        company = require_tenant().company
    return erpnext_get_children(
        doctype=doctype,
        parent=parent,
        company=company,
        is_root=is_root,
        include_disabled=include_disabled,
    )


def validate_tenant_assignment(doc, method=None) -> None:
    """A normal tenant login may have only one active Company assignment."""
    if not doc.get("active") or not doc.get("user") or not doc.get("company"):
        return
    existing = frappe.get_all(
        "Tenant User Assignment",
        filters={"user": doc.user, "active": 1, "name": ["!=", doc.name]},
        fields=["company"],
    )
    other_companies = {row.company for row in existing if row.company and row.company != doc.company}
    if other_companies:
        frappe.throw(
            _("User {0} already has an active Company assignment: {1}.").format(
                doc.user, ", ".join(sorted(other_companies))
            ),
            frappe.PermissionError,
        )


def sync_tenant_user_permission(doc, method=None) -> None:
    """Materialize the assignment as Frappe's standard Company User Permission."""
    if not doc.get("user"):
        return
    active = frappe.get_all(
        "Tenant User Assignment",
        filters={"user": doc.user, "active": 1},
        fields=["company"],
    )
    companies = {row.company for row in active if row.company}
    if len(companies) > 1:
        frappe.throw(
            _("User {0} cannot have access to multiple Companies.").format(doc.user),
            frappe.PermissionError,
        )

    for permission in frappe.get_all(
        "User Permission", filters={"user": doc.user, "allow": "Company"}, pluck="name"
    ):
        frappe.delete_doc("User Permission", permission, ignore_permissions=True, force=True)

    if companies:
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": doc.user,
                "allow": "Company",
                "for_value": next(iter(companies)),
                "apply_to_all_doctypes": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True)
