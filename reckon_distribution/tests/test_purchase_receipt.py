from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.purchase_receipt import validate_purchase_receipt


class TestPurchaseReceiptControls(FrappeTestCase):
    def _receipt(self, supplier="_Test Supplier", **row_values):
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
                "supplier": supplier,
                "docstatus": 0,
                "rd_promotion_source": None,
                "rd_promotion_reference": None,
                "rd_promotion_terms": None,
                "items": [row],
            }
        )

    def test_paid_and_free_quantities_must_reconcile_to_received_qty(self):
        receipt = self._receipt(rd_paid_qty=8, rd_free_qty=2, conversion_factor=2, stock_qty=20)
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

    def test_stock_uom_quantity_must_match_conversion_factor(self):
        receipt = self._receipt(rd_paid_qty=8, rd_free_qty=2, conversion_factor=2, stock_qty=19)
        receipt.rd_promotion_source = "Supplier circular"
        receipt.rd_promotion_reference = "PROMO-001"
        receipt.rd_promotion_terms = "Two free units supplied with this receipt"

        with self.assertRaises(frappe.ValidationError):
            validate_purchase_receipt(receipt)

    def test_shortage_requires_dispute_note(self):
        receipt = self._receipt(rd_shortage_qty=2)

        with self.assertRaises(frappe.ValidationError):
            validate_purchase_receipt(receipt)

    def test_tenant_user_cannot_validate_receipt_for_another_company(self):
        user = "purchase-tenant-a@example.com"
        company_a = "_Test Tenant Company A"
        company_b = "_Test Tenant Company B"
        item = frappe.db.get_value("Item", {}, "name")
        supplier = frappe.db.get_value("Supplier", {}, "name")
        if not item or not supplier:
            self.skipTest("ERPNext Item and Supplier fixtures are unavailable")

        assignment = frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": user,
                "company": company_a,
                "role_profile": "Master Data Manager",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        scopes = []
        for master_type, master_name in [("Item", item), ("Supplier", supplier)]:
            scopes.append(
                frappe.get_doc(
                    {
                        "doctype": "Distribution Master Scope",
                        "company": company_a,
                        "master_type": master_type,
                        "master_name": master_name,
                        "access_scope": "Manage",
                        "active": 1,
                    }
                ).insert(ignore_permissions=True)
            )

        frappe.set_user(user)
        try:
            receipt = self._receipt(item_code=item, supplier=supplier)
            receipt.company = company_b
            with self.assertRaises(frappe.PermissionError):
                validate_purchase_receipt(receipt)
        finally:
            frappe.set_user("Administrator")
            for scope in scopes:
                frappe.delete_doc(
                    "Distribution Master Scope", scope.name, ignore_permissions=True, force=True
                )
            frappe.delete_doc(
                "Tenant User Assignment", assignment.name, ignore_permissions=True, force=True
            )
