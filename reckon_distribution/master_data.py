from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _

from reckon_distribution.tenant_security import require_tenant, validate_tenant_owned_doc

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
