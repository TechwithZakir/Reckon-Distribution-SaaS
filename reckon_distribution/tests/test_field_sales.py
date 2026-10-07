from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.field_sales import _order_item, save_sr_order


class TestFieldSales(FrappeTestCase):
    def test_uom_conversion_is_server_calculated(self):
        item = frappe._dict(
            {
                "stock_uom": "Nos",
                "uoms": [frappe._dict({"uom": "Carton", "conversion_factor": 12})],
            }
        )
        with patch("reckon_distribution.field_sales.validate_master_scope"), patch(
            "reckon_distribution.field_sales.frappe.get_doc", return_value=item
        ), patch("reckon_distribution.field_sales.frappe.db.get_value", return_value=250):
            row = _order_item("_Test Tenant Company A", {"item_code": "_Test Item", "uom": "Carton", "qty": 2}, "Retail")

        self.assertEqual(row["conversion_factor"], 12)
        self.assertEqual(row["stock_qty"], 24)
        self.assertEqual(row["rate"], 250)

    def test_order_rejects_client_free_quantity(self):
        payload = {
            "company": "_Test Tenant Company A",
            "customer": "_Test Customer A",
            "route": "_Test Route A",
            "price_list": "Retail",
            "idempotency_key": "offline-order-001",
            "items": [{"item_code": "_Test Item", "qty": 1, "free_qty": 1}],
        }
        tenant = frappe._dict({"company": payload["company"]})
        with patch("reckon_distribution.field_sales.require_tenant", return_value=tenant), patch(
            "reckon_distribution.field_sales.frappe.db.get_value", return_value=None
        ), patch("reckon_distribution.field_sales._assert_assigned_customer"), patch(
            "reckon_distribution.field_sales.validate_master_scope"
        ):
            with self.assertRaises(frappe.ValidationError):
                save_sr_order(payload)

    def test_invalid_gps_is_rejected(self):
        payload = {
            "company": "_Test Tenant Company A",
            "customer": "_Test Customer A",
            "route": "_Test Route A",
            "idempotency_key": "visit-gps-001",
            "gps_latitude": 100,
            "gps_longitude": 90,
        }
        tenant = frappe._dict({"company": payload["company"]})
        with patch("reckon_distribution.field_sales.require_tenant", return_value=tenant), patch(
            "reckon_distribution.field_sales.frappe.db.get_value", return_value=None
        ), patch("reckon_distribution.field_sales._assert_assigned_customer"):
            from reckon_distribution.field_sales import record_outlet_visit

            with self.assertRaises(frappe.ValidationError):
                record_outlet_visit(payload)
