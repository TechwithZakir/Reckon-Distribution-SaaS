from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.purchase_receipt import validate_purchase_receipt


class TestPurchaseReceiptControls(FrappeTestCase):
    def _receipt(self, **row_values):
        row = frappe._dict(
            {
                "idx": 1,
                "item_code": "_Test Item",
                "qty": 10,
                "is_stock_item": 0,
                "warehouse": None,
                "purchase_order_item": None,
                "rd_paid_qty": 10,
                "rd_free_qty": 0,
                "rd_shortage_qty": 0,
                "rd_dispute_note": None,
                **row_values,
            }
        )
        return frappe._dict(
            {
                "company": "_Test Tenant Company A",
                "supplier": "_Test Supplier",
                "docstatus": 0,
                "rd_promotion_source": None,
                "rd_promotion_reference": None,
                "rd_promotion_terms": None,
                "items": [row],
            }
        )

    def test_paid_and_free_quantities_must_reconcile_to_received_qty(self):
        receipt = self._receipt(rd_paid_qty=8, rd_free_qty=2)
        receipt.rd_promotion_source = "Supplier circular"
        receipt.rd_promotion_reference = "PROMO-001"
        receipt.rd_promotion_terms = "Two free units supplied with this receipt"

        validate_purchase_receipt(receipt)

    def test_free_goods_require_supplier_provenance(self):
        receipt = self._receipt(rd_paid_qty=8, rd_free_qty=2)

        with self.assertRaises(frappe.ValidationError):
            validate_purchase_receipt(receipt)

    def test_paid_and_free_quantities_cannot_overstate_stock_receipt(self):
        receipt = self._receipt(rd_paid_qty=8, rd_free_qty=1)

        with self.assertRaises(frappe.ValidationError):
            validate_purchase_receipt(receipt)

    def test_shortage_requires_dispute_note(self):
        receipt = self._receipt(rd_shortage_qty=2)

        with self.assertRaises(frappe.ValidationError):
            validate_purchase_receipt(receipt)
