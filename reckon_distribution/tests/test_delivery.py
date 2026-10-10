from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.delivery import (
    approve_return_inspection,
    validate_delivery_note,
    validate_return_inspection,
)


class TestDistributionDelivery(FrappeTestCase):
    def _delivery(self, category="Saleable"):
        return frappe._dict(
            {
                "company": "_Test Tenant Company A",
                "customer": "_Test Customer A",
                "rd_route": "_Test Route A",
                "rd_dsr": "dsr@example.com",
                "items": [
                    frappe._dict(
                        {
                            "idx": 1,
                            "item_code": "_Test Item",
                            "rd_stock_category": category,
                            "rd_supplier_free_source": "PR-TEST-001" if category == "Supplier Free" else None,
                        }
                    )
                ],
            }
        )

    def test_delivery_requires_assigned_route_and_customer(self):
        delivery = self._delivery()
        route = frappe._dict({"company": delivery.company, "assigned_user": delivery.rd_dsr})
        with patch("reckon_distribution.delivery.require_tenant"), patch(
            "reckon_distribution.delivery.validate_master_scope"
        ), patch("reckon_distribution.delivery.get_tenant_doc", return_value=route), patch(
            "reckon_distribution.delivery.frappe.db.exists", return_value=False
        ):
            with self.assertRaises(frappe.PermissionError):
                validate_delivery_note(delivery)

    def test_supplier_free_delivery_requires_submitted_source(self):
        delivery = self._delivery("Supplier Free")
        route = frappe._dict({"company": delivery.company, "assigned_user": delivery.rd_dsr})
        with patch("reckon_distribution.delivery.require_tenant"), patch(
            "reckon_distribution.delivery.validate_master_scope"
        ), patch("reckon_distribution.delivery.get_tenant_doc", side_effect=[route, frappe._dict({"company": delivery.company, "docstatus": 0})]), patch(
            "reckon_distribution.delivery.frappe.db.exists", return_value=True
        ):
            with self.assertRaises(frappe.ValidationError):
                validate_delivery_note(delivery)

    def test_damaged_return_cannot_be_marked_restock(self):
        inspection = frappe._dict(
            {
                "company": "_Test Tenant Company A",
                "customer": "_Test Customer A",
                "delivery_note": "DN-TEST-001",
                "item_code": "_Test Item",
                "qty": 1,
                "condition": "Damaged",
                "disposition": "Restock",
            }
        )
        delivery = frappe._dict({"company": inspection.company, "customer": inspection.customer})
        with patch("reckon_distribution.delivery.validate_tenant_owned_doc"), patch(
            "reckon_distribution.delivery.require_tenant"
        ), patch("reckon_distribution.delivery.validate_master_scope"), patch(
            "reckon_distribution.delivery.get_tenant_doc", return_value=delivery
        ):
            with self.assertRaises(frappe.ValidationError):
                validate_return_inspection(inspection)

    def test_return_approval_creates_one_material_receipt(self):
        inspection = frappe._dict(
            {
                "name": "RET-TEST-001",
                "company": "_Test Tenant Company A",
                "item_code": "_Test Item",
                "qty": 2,
                "uom": "Nos",
                "warehouse": "Quarantine - TCA",
                "status": "Draft",
                "stock_entry": None,
                "save": lambda: None,
            }
        )
        stock_entry = frappe._dict({"name": "STE-RETURN-001", "insert": lambda: None, "submit": lambda: None})
        with patch("reckon_distribution.delivery.get_tenant_doc", return_value=inspection), patch(
            "reckon_distribution.delivery._is_manager", return_value=True
        ), patch("reckon_distribution.delivery.nowdate", return_value="2026-10-07"), patch(
            "reckon_distribution.delivery.now_datetime", return_value="2026-10-07 12:00:00"
        ), patch(
            "reckon_distribution.delivery.frappe.get_doc", return_value=stock_entry
        ) as get_doc:
            result = approve_return_inspection(inspection.name)

        self.assertEqual(result, "STE-RETURN-001")
        self.assertEqual(inspection.status, "Approved")
        self.assertEqual(get_doc.call_args.args[0]["stock_entry_type"], "Material Receipt")
