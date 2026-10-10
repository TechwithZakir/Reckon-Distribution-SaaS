from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.field_sales import (
    _order_item,
    get_assigned_outlets,
    get_dsr_delivery_catalog,
    get_dsr_delivery_context,
    get_retailer_summary,
    save_sr_order,
)


class TestFieldSales(FrappeTestCase):
    def test_delivery_context_defaults_to_assigned_route_and_company_warehouse(self):
        tenant = frappe._dict({"company": "_Test Tenant Company A"})
        routes = [frappe._dict({"name": "_Test Route A", "route_name": "Route A"})]
        with patch("reckon_distribution.field_sales.require_tenant", return_value=tenant), patch(
            "reckon_distribution.field_sales.frappe.session.user", "dsr@example.com"
        ), patch("reckon_distribution.field_sales.frappe.get_all", side_effect=[routes, ["Van - TCA"]]), patch(
            "reckon_distribution.field_sales.frappe.db.get_value", side_effect=[None, None]
        ):
            result = get_dsr_delivery_context()

        self.assertEqual(result["default_route"], "_Test Route A")
        self.assertEqual(result["default_warehouse"], "Van - TCA")

    def test_retailer_summary_uses_erpnext_v16_balance_signature(self):
        tenant = frappe._dict({"company": "_Test Tenant Company A"})
        with patch("reckon_distribution.field_sales.require_tenant", return_value=tenant), patch(
            "reckon_distribution.field_sales._assert_assigned_customer"
        ), patch("erpnext.accounts.utils.get_balance_on", return_value=1250
        ) as get_balance:
            result = get_retailer_summary("_Test Customer A", "_Test Route A")

        self.assertEqual(result["net_due"], 1250)
        get_balance.assert_called_once_with(
            party_type="Customer",
            party="_Test Customer A",
            company="_Test Tenant Company A",
        )

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

    def test_dsr_catalog_keeps_unpriced_stock_visible(self):
        tenant = frappe._dict({"company": "_Test Tenant Company A"})
        item = frappe._dict({"item_name": "Test Item", "stock_uom": "Nos", "uoms": []})

        def get_all(doctype, **kwargs):
            if doctype == "Distribution Master Scope":
                return ["_Test Item"]
            if doctype == "Item":
                return []
            if doctype == "Item Price":
                return []
            self.fail(f"Unexpected get_all for {doctype}")

        with patch("reckon_distribution.field_sales.require_tenant", return_value=tenant), patch(
            "reckon_distribution.field_sales._assert_warehouse"
        ), patch(
            "reckon_distribution.field_sales.get_or_create_company_sales_price_list", return_value="Retail"
        ), patch("reckon_distribution.field_sales.validate_master_scope"), patch(
            "reckon_distribution.field_sales.frappe.get_all", side_effect=get_all
        ), patch("reckon_distribution.field_sales.frappe.get_doc", return_value=item), patch(
            "erpnext.stock.utils.get_stock_balance", return_value=12
        ):
            catalog = get_dsr_delivery_catalog("_Test Van")

        self.assertEqual(catalog[0]["item_code"], "_Test Item")
        self.assertEqual(catalog[0]["available_qty"], 12)
        self.assertFalse(catalog[0]["is_priced"])

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

    def test_bypass_user_without_tenant_assignment_gets_empty_outlet_list(self):
        with patch("reckon_distribution.field_sales.user_can_bypass_tenant", return_value=True), patch(
            "reckon_distribution.field_sales.get_user_companies", return_value=[]
        ), patch("reckon_distribution.field_sales.require_tenant") as require_tenant:
            self.assertEqual(get_assigned_outlets(), [])
            require_tenant.assert_not_called()
