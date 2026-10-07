from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    assert_company_matches_tenant,
    user_can_bypass_tenant,
)


def validate_purchase_receipt(doc, method=None) -> None:
    """Validate supplier-provided paid/free quantities before ERPNext posts stock."""
    if not doc.company:
        frappe.throw(_("Purchase Receipt Company is required."))

    _validate_company(doc.company)
    _validate_master_links(doc)
    has_free_goods = False
    has_shortage = False

    for row in doc.items:
        paid_qty = flt(row.get("rd_paid_qty"))
        free_qty = flt(row.get("rd_free_qty"))
        shortage_qty = flt(row.get("rd_shortage_qty"))

        if paid_qty < 0 or free_qty < 0 or shortage_qty < 0:
            frappe.throw(_("Paid, free, and shortage quantities cannot be negative."))

        if paid_qty or free_qty:
            if abs((paid_qty + free_qty) - flt(row.qty)) > 0.000001:
                frappe.throw(
                    _("Row {0}: paid quantity plus free quantity must equal received quantity.").format(
                        row.idx
                    )
                )

        if free_qty:
            has_free_goods = True
            if not doc.get("rd_promotion_source") or not doc.get("rd_promotion_reference"):
                frappe.throw(
                    _(
                        "Supplier promotion source and reference are required when free goods are received."
                    )
                )
            if not doc.get("rd_promotion_terms"):
            frappe.throw(
                _("Supplier promotion terms are required when free goods are received.")
            )

        if shortage_qty:
            has_shortage = True
            if not row.get("rd_dispute_note"):
                frappe.throw(_("Row {0}: shortage/dispute note is required.").format(row.idx))
            _validate_shortage_against_order(row)

        if row.get("is_stock_item") and not row.get("warehouse"):
            frappe.throw(
                _("Row {0}: warehouse is required for stock Item {1}.").format(
                    row.idx, row.item_code
                )
            )

    if has_shortage and doc.docstatus == 1:
        frappe.throw(_("A Purchase Receipt with an unresolved shortage cannot be submitted."))

    if has_free_goods and not doc.get("supplier"):
        frappe.throw(_("Supplier is required when recording supplier-provided free goods."))


def _validate_company(company: str) -> None:
    """Apply tenant resolution for API/background submissions without blocking System Manager."""
    try:
        assert_company_matches_tenant(company)
    except frappe.PermissionError:
        if frappe.session.user not in {"Administrator"} and "System Manager" not in frappe.get_roles():
            raise


def _validate_master_links(doc) -> None:
    if user_can_bypass_tenant():
        return

    validate_master_scope(doc.company, "Supplier", doc.supplier)
    for row in doc.items:
        validate_master_scope(doc.company, "Item", row.item_code)
        if row.get("warehouse"):
            validate_master_scope(doc.company, "Warehouse", row.warehouse)


def _validate_shortage_against_order(row) -> None:
    if not row.get("purchase_order_item"):
        return

    ordered_qty = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "qty")
    if ordered_qty is None:
        frappe.throw(_("Purchase Order Item {0} was not found.").format(row.purchase_order_item))
    if flt(row.qty) + flt(row.rd_shortage_qty) > flt(ordered_qty) + 0.000001:
        frappe.throw(
            _("Row {0}: received plus shortage exceeds the ordered quantity.").format(row.idx)
        )
