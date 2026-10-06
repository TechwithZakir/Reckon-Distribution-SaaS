from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from reckon_saas_platform.constants import TENANT_BYPASS_ROLES


class TenantResolutionError(frappe.PermissionError):
    pass


class CrossCompanyAccessError(frappe.PermissionError):
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


def bind_doc_to_tenant(doc, user: str | None = None) -> None:
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return

    if not hasattr(doc, "company"):
        raise TenantResolutionError(_("Tenant-owned documents must have a Company field."))

    tenant = require_tenant(user=user, company=getattr(doc, "company", None) or None)
    if doc.is_new() and not getattr(doc, "company", None):
        doc.company = tenant.company

    if doc.company != tenant.company:
        raise CrossCompanyAccessError(_("Document company does not match tenant context."))


def validate_tenant_company_immutable(doc) -> None:
    if doc.is_new() or not hasattr(doc, "company"):
        return

    previous_company = frappe.db.get_value(doc.doctype, doc.name, "company")
    if previous_company and previous_company != doc.company:
        frappe.throw(_("Company cannot be changed after insert."))


def validate_tenant_owned_doc(doc, user: str | None = None) -> None:
    validate_tenant_company_immutable(doc)
    bind_doc_to_tenant(doc, user=user)


def get_tenant_owned_query(user: str | None = None, doctype: str | None = None) -> str:
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return ""

    tenant = require_tenant(user=user)
    doctype = doctype or "Tenant Security Test Record"
    return f"`tab{doctype}`.`company` = {frappe.db.escape(tenant.company)}"


def has_tenant_owned_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return True

    if permission_type in {"create", "write", "delete", "submit", "cancel", "amend"}:
        return getattr(doc, "company", None) in get_user_companies(user)

    try:
        assert_company_matches_tenant(getattr(doc, "company", None), user=user)
    except TenantResolutionError:
        return False
    return True


def get_tenant_doc(doctype: str, name: str, user: str | None = None):
    doc = frappe.get_doc(doctype, name)
    if not has_tenant_owned_permission(doc, user=user, permission_type="read"):
        raise CrossCompanyAccessError(_("Not permitted for tenant company."))
    return doc


def guard_api_company(company: str | None = None, user: str | None = None) -> TenantContext:
    return require_tenant(user=user, company=company)


def guarded_link_search(
    doctype: str,
    txt: str = "",
    searchfield: str = "name",
    user: str | None = None,
    fields: Iterable[str] | None = None,
) -> list[dict]:
    tenant = require_tenant(user=user)
    return frappe.get_all(
        doctype,
        filters={"company": tenant.company, searchfield: ["like", f"%{txt}%"]},
        fields=list(fields or ["name", "company"]),
    )


def guarded_export_rows(doctype: str, user: str | None = None) -> list[dict]:
    tenant = require_tenant(user=user)
    return frappe.get_all(doctype, filters={"company": tenant.company}, fields=["name", "company"])


def guarded_background_job_company(company: str, user: str | None = None) -> str:
    return guard_api_company(company=company, user=user).company


def assert_file_belongs_to_tenant(attached_to_doctype: str, attached_to_name: str, user: str | None = None) -> None:
    doc = get_tenant_doc(attached_to_doctype, attached_to_name, user=user)
    assert_company_matches_tenant(doc.company, user=user)


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
