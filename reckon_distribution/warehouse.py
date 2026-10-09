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
def get_children(doctype, parent=None, company=None, is_root=False, **kwargs):
    """Use the server tenant Company for the native Warehouse Tree."""
    from erpnext.stock.doctype.warehouse.warehouse import get_children as erpnext_get_children

    if not user_can_bypass_tenant():
        company = require_tenant().company
    return erpnext_get_children(
        doctype=doctype,
        parent=parent,
        company=company,
        is_root=is_root,
        **kwargs,
    )
