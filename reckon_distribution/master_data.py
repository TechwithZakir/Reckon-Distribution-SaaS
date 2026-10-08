from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _

from reckon_distribution.tenant_security import (
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

SUPPORTED_MASTER_TYPES = frozenset(
    {
        "Item",
        "Item Group",
        "Brand",
        "Price List",
        "Item Price",
        "Supplier",
        "Customer",
        "Warehouse",
        "Payment Terms Template",
        "Account",
    }
)

SHARED_MASTER_TYPES = {
    "Item": "Item",
    "Supplier": "Supplier",
    "Customer": "Customer",
    "Item Price": "Item Price",
    "Price List": "Price List",
}


def get_shared_master_query(user: str | None = None, doctype: str | None = None) -> str:
    """Restrict native ERPNext master lists and link searches to tenant scope."""
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return ""
    master_type = SHARED_MASTER_TYPES.get(doctype or "")
    if not master_type:
        return ""
    tenant = require_tenant(user=user)
    field = "name" if master_type != "Item Price" else "name"
    return (
        f"`tab{doctype}`.`{field}` in ("
        "select master_name from `tabDistribution Master Scope` "
        f"where company = {frappe.db.escape(tenant.company)} "
        f"and master_type = {frappe.db.escape(master_type)} and active = 1)"
    )


def has_shared_master_permission(
    doc,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
    debug: bool = False,
) -> bool:
    """Apply tenant scope to native master reads and mutations."""
    user = user or frappe.session.user
    permission_type = ptype or permission_type
    if user_can_bypass_tenant(user):
        return True
    master_type = SHARED_MASTER_TYPES.get(doc.doctype)
    if not master_type:
        return False
    tenant = require_tenant(user=user)
    if doc.is_new() and permission_type in {"create", "write"}:
        return True
    if not frappe.db.exists(
        "Distribution Master Scope",
        {"company": tenant.company, "master_type": master_type, "master_name": doc.name, "active": 1},
    ):
        return False
    if permission_type in {"write", "delete", "submit", "cancel", "amend"}:
        other_company_scope = frappe.db.exists(
            "Distribution Master Scope",
            {
                "master_type": master_type,
                "master_name": doc.name,
                "company": ["!=", tenant.company],
                "active": 1,
            },
        )
        return not other_company_scope
    return True


def auto_scope_shared_master(doc, method=None) -> None:
    """Bind a native master created by a tenant user to that user's Company."""
    if user_can_bypass_tenant() or not doc.is_new() and frappe.db.exists(
        "Distribution Master Scope", {"master_type": SHARED_MASTER_TYPES.get(doc.doctype), "master_name": doc.name}
    ):
        return
    master_type = SHARED_MASTER_TYPES.get(doc.doctype)
    if not master_type:
        return
    tenant = require_tenant()
    scope_name = frappe.db.exists(
        "Distribution Master Scope",
        {"company": tenant.company, "master_type": master_type, "master_name": doc.name},
    )
    if not scope_name:
        frappe.get_doc(
            {
                "doctype": "Distribution Master Scope",
                "company": tenant.company,
                "master_type": master_type,
                "master_name": doc.name,
                "access_scope": "Manage",
                "active": 1,
            }
        ).insert()


def normalize_item_code(doc, method=None) -> None:
    """Use the business-facing Item Name as the unique ERPNext Item Code."""
    if doc.doctype != "Item" or user_can_bypass_tenant() or not doc.get("item_name"):
        return
    doc.item_code = doc.item_name.strip()


def validate_shared_master_change(doc, method=None) -> None:
    if doc.is_new() or user_can_bypass_tenant():
        return
    if not has_shared_master_permission(doc, permission_type="write"):
        frappe.throw(_("This master is not editable for your Company."), frappe.PermissionError)


def validate_master_reference(doc) -> None:
    validate_tenant_owned_doc(doc)
    if doc.master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(doc.master_type))
    if not frappe.db.exists(doc.master_type, doc.master_name):
        frappe.throw(_("{0} {1} does not exist.").format(doc.master_type, doc.master_name))
    duplicate = frappe.db.exists(
        "Distribution Master Scope",
        {
            "company": doc.company,
            "master_type": doc.master_type,
            "master_name": doc.master_name,
            "name": ["!=", doc.name],
        },
    )
    if duplicate:
        frappe.throw(
            _("{0} {1} is already enabled for company {2}.").format(
                doc.master_type, doc.master_name, doc.company
            )
        )


def validate_master_scope(
    company: str, master_type: str, master_name: str, user: str | None = None
) -> None:
    tenant = require_tenant(user=user, company=company)
    if master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(master_type))
    if not frappe.db.exists(master_type, master_name):
        frappe.throw(_("{0} {1} does not exist.").format(master_type, master_name))
    if not frappe.db.exists(
        "Distribution Master Scope",
        {
            "company": tenant.company,
            "master_type": master_type,
            "master_name": master_name,
            "active": 1,
        },
    ):
        frappe.throw(
            _("{0} {1} is not enabled for company {2}.").format(
                master_type, master_name, tenant.company
            )
        )


@frappe.whitelist()
def search_company_master(
    master_type: str,
    txt: str = "",
    user: str | None = None,
    fields: Iterable[str] | None = None,
) -> list[dict]:
    tenant = require_tenant(user=user)
    if master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(master_type))
    selected_fields = list(fields or ["company", "master_name", "master_type", "access_scope"])
    if "company" not in selected_fields:
        selected_fields.insert(0, "company")
    if "master_name" not in selected_fields:
        selected_fields.insert(0, "master_name")
    return frappe.get_all(
        "Distribution Master Scope",
        filters={
            "company": tenant.company,
            "master_type": master_type,
            "active": 1,
            "master_name": ["like", f"%{txt}%"],
        },
        fields=selected_fields,
        order_by="master_name asc",
    )


@frappe.whitelist()
def assert_company_master(company: str, master_type: str, master_name: str) -> dict:
    validate_master_scope(company, master_type, master_name)
    return {"company": company, "master_type": master_type, "master_name": master_name}
