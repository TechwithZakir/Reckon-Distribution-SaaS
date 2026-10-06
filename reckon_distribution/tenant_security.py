from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from reckon_distribution.constants import TENANT_BYPASS_ROLES


class TenantResolutionError(frappe.PermissionError):
    pass


@dataclass(frozen=True)
class TenantContext:
    user: str
    company: str


def user_can_bypass_tenant(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True

    roles = set(frappe.get_roles(user))
    return bool(roles.intersection(TENANT_BYPASS_ROLES))


def get_user_companies(user: str | None = None, active_only: bool = True) -> list[str]:
    user = user or frappe.session.user
    filters: dict[str, object] = {"user": user}
    if active_only:
        filters["active"] = 1

    rows = frappe.get_all(
        "Tenant User Assignment",
        filters=filters,
        fields=["company", "valid_from", "valid_to"],
        order_by="is_default desc, creation asc",
    )

    today = getdate(nowdate())
    companies: list[str] = []
    for row in rows:
        if row.valid_from and getdate(row.valid_from) > today:
            continue
        if row.valid_to and getdate(row.valid_to) < today:
            continue
        if row.company not in companies:
            companies.append(row.company)

    return companies


def resolve_tenant(user: str | None = None, company: str | None = None) -> TenantContext:
    user = user or frappe.session.user

    if user in {"Guest", None}:
        raise TenantResolutionError(_("Guest users do not have a tenant context."))

    companies = get_user_companies(user)

    if company:
        if company not in companies and not user_can_bypass_tenant(user):
            raise TenantResolutionError(_("User is not assigned to company {0}.").format(company))
        return TenantContext(user=user, company=company)

    if len(companies) == 1:
        return TenantContext(user=user, company=companies[0])

    if not companies:
        raise TenantResolutionError(_("User has no active tenant company assignment."))

    raise TenantResolutionError(_("User has multiple tenant company assignments."))


def require_tenant(user: str | None = None, company: str | None = None) -> TenantContext:
    return resolve_tenant(user=user, company=company)


def assert_company_matches_tenant(company: str, user: str | None = None) -> None:
    tenant = require_tenant(user=user, company=company)
    if tenant.company != company:
        raise TenantResolutionError(_("Company does not match tenant context."))


def get_tenant_user_assignment_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return ""

    escaped_user = frappe.db.escape(user)
    return f"`tabTenant User Assignment`.`user` = {escaped_user}"


def has_tenant_user_assignment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return True

    if permission_type in {"create", "write", "delete", "submit", "cancel", "amend"}:
        return False

    return getattr(doc, "user", None) == user
