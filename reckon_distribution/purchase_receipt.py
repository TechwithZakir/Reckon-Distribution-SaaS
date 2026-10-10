from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    assert_company_matches_tenant,
    get_tenant_doc,
    user_can_bypass_tenant,
)


def create_purchase_invoice_from_receipt(doc, method=None):
    """Create the configured native Purchase Invoice exactly once after receipt submit."""
    if doc.docstatus != 1:
        return

    settings = frappe.db.get_value(
        "Distribution Settings",
        {"company": doc.company},
        ["supplier_invoice_policy", "auto_invoice_requires_supplier_bill"],
        as_dict=True,
    ) or frappe._dict()
    policy = settings.get("supplier_invoice_policy") or "Auto-create Draft"
    if policy == "Manual":
        doc.db_set("rd_invoice_status", "Manual", update_modified=False)
        return

    existing = doc.get("rd_purchase_invoice") or frappe.db.get_value(
        "Purchase Invoice",
        {"rd_source_purchase_receipt": doc.name, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        doc.db_set("rd_purchase_invoice", existing, update_modified=False)
        doc.db_set(
            "rd_invoice_status",
            frappe.db.get_value("Purchase Invoice", existing, "status") or "Draft",
            update_modified=False,
        )
        return existing

    invoice = _map_purchase_invoice(doc)
    if not invoice.items:
        doc.db_set("rd_invoice_status", "Not Required", update_modified=False)
        return

    if policy == "Auto-submit":
        requires_bill = int(settings.get("auto_invoice_requires_supplier_bill") or 0)
        if requires_bill and (not doc.get("bill_no") or not doc.get("bill_date")):
            frappe.throw(
                _("Supplier bill number and bill date are required for Auto-submit invoice policy.")
            )
        if not frappe.has_permission("Purchase Invoice", ptype="submit"):
            frappe.throw(_("You do not have permission to auto-submit Purchase Invoices."))

    invoice.insert(ignore_permissions=True)
    if policy == "Auto-submit":
        invoice.submit()

    doc.db_set("rd_purchase_invoice", invoice.name, update_modified=False)
    doc.db_set(
        "rd_invoice_status",
        "Submitted" if invoice.docstatus == 1 else "Draft",
        update_modified=False,
    )
    doc.db_set("rd_invoice_created_on", frappe.utils.now_datetime(), update_modified=False)
    return invoice.name


def _map_purchase_invoice(receipt):
    """Use ERPNext's mapper, then remove supplier-free quantities before insert."""
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

    invoice = make_purchase_invoice(receipt.name)
    invoice.update_stock = 0
    invoice.rd_source_purchase_receipt = receipt.name

    source_rows = {row.name: row for row in receipt.get("items") or [] if row.name}
    billable_items = []
    for item in invoice.get("items") or []:
        source = source_rows.get(item.get("purchase_receipt_item"))
        if source:
            paid_qty = flt(source.get("rd_paid_qty"))
            free_qty = flt(source.get("rd_free_qty"))
            if paid_qty or free_qty:
                item.qty = paid_qty
                item.stock_qty = paid_qty * (flt(item.conversion_factor) or 1)
        if flt(item.qty) <= 0:
            continue
        billable_items.append(item)
    invoice.set("items", billable_items)
    invoice.run_method("set_missing_values")
    invoice.calculate_taxes_and_totals()
    return invoice


def validate_purchase_receipt(doc, method=None) -> None:
    """Validate supplier-provided paid/free quantities before ERPNext posts stock."""
    if not doc.company:
        frappe.throw(_("Purchase Receipt Company is required."))

    _validate_company(doc.company)
    _validate_master_links(doc)
    has_free_goods = False
    has_shortage = False

    for row in doc.get("items") or []:
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
            _validate_stock_uom_quantity(row)

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
        _validate_batch_reference(row)

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
    for row in doc.get("items") or []:
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


def _validate_stock_uom_quantity(row) -> None:
    conversion_factor = flt(row.get("conversion_factor")) or 1
    expected_stock_qty = flt(row.qty) * conversion_factor
    actual_stock_qty = flt(row.get("stock_qty"))
    if actual_stock_qty and abs(actual_stock_qty - expected_stock_qty) > 0.000001:
        frappe.throw(
            _("Row {0}: received stock quantity does not match the UOM conversion factor.").format(
                row.idx
            )
        )


def _validate_batch_reference(row) -> None:
    batch_no = row.get("batch_no")
    if not batch_no or not row.get("item_code"):
        return
    batch_item = frappe.db.get_value("Batch", batch_no, "item")
    if not batch_item:
        frappe.throw(_("Batch {0} does not exist.").format(batch_no))
    if batch_item != row.item_code:
        frappe.throw(
            _("Batch {0} belongs to Item {1}, not Item {2}.").format(
                batch_no, batch_item, row.item_code
            )
        )


@frappe.whitelist()
def reconcile_purchase_receipt_stock(receipt: str) -> dict:
    doc = get_tenant_doc("Purchase Receipt", receipt)
    if doc.docstatus != 1:
        frappe.throw(_("Purchase Receipt {0} must be submitted before stock reconciliation.").format(receipt))

    source_qty = sum(flt(row.stock_qty) for row in doc.get("items") or [])
    ledger_qty = frappe.db.sql(
        """
        select coalesce(sum(actual_qty), 0)
        from `tabStock Ledger Entry`
        where voucher_type = 'Purchase Receipt'
          and voucher_no = %s
          and is_cancelled = 0
        """,
        receipt,
    )[0][0]
    ledger_qty = flt(ledger_qty)
    return {
        "receipt": receipt,
        "source_stock_qty": source_qty,
        "ledger_stock_qty": ledger_qty,
        "reconciled": abs(source_qty - ledger_qty) <= 0.000001,
    }
