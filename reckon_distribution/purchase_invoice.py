from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import get_tenant_doc, validate_tenant_owned_doc


def validate_purchase_invoice(doc, method=None) -> None:
    """Keep native supplier invoices inside the authenticated Company boundary."""
    validate_tenant_owned_doc(doc)
    if doc.get("supplier"):
        validate_master_scope(doc.company, "Supplier", doc.supplier)
    if doc.get("rd_source_purchase_receipt"):
        receipt = get_tenant_doc("Purchase Receipt", doc.rd_source_purchase_receipt)
        if receipt.company != doc.company:
            frappe.throw(_("Purchase Invoice and Purchase Receipt must use the same Company."))
        if receipt.docstatus != 1:
            frappe.throw(_("The source Purchase Receipt must be submitted."))
        if doc.get("update_stock"):
            frappe.throw(_("A Purchase Invoice generated from a Purchase Receipt cannot update stock."))


def validate_supplier_payment_entry(doc, method=None) -> None:
    """Validate supplier advances/payments against the tenant Company and Supplier."""
    if doc.get("party_type") != "Supplier" or not doc.get("party"):
        return
    validate_tenant_owned_doc(doc)
    validate_master_scope(doc.company, "Supplier", doc.party)
