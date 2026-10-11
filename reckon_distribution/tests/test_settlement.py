from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.settlement import (
    _challan_stock_source,
    create_day_settlement,
    validate_day_settlement,
)


class TestDSRDaySettlement(FrappeTestCase):
    def _doc(self, variance_reason=None):
        return frappe._dict(
            {
                "name": "SET-TEST-001",
                "company": "_Test Tenant Company A",
                "challan": "VLC-TEST-001",
                "route": "_Test Route A",
                "dsr": "dsr@example.com",
                "status": "Draft",
                "opening_cash": 100,
                "confirmed_cash_collections": 50,
                "approved_expenses": 10,
                "approved_refunds": 0,
                "cash_handover": 140,
                "counted_cash": 140,
                "cash_variance_reason": variance_reason,
                "stock_items": [
                    frappe._dict(
                        {
                            "item_code": "_Test Item",
                            "opening_qty": 10,
                            "loaded_qty": 5,
                            "paid_delivery_qty": 8,
                            "free_delivery_qty": 1,
                            "accepted_return_qty": 1,
                            "closing_qty": 7,
                            "variance_reason": variance_reason,
                        }
                    )
                ],
            }
        )

    def test_stock_and_cash_equations_reconcile(self):
        doc = self._doc()
        route = frappe._dict({"company": doc.company, "assigned_user": doc.dsr})
        with patch("reckon_distribution.settlement.validate_tenant_owned_doc"), patch(
            "reckon_distribution.settlement.require_tenant"
        ), patch("reckon_distribution.settlement._sync_settlement_from_challan"), patch(
            "reckon_distribution.settlement.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.settlement.frappe.db.exists", return_value=False):
            validate_day_settlement(doc)

        self.assertEqual(doc.stock_items[0].expected_closing_qty, 7)
        self.assertEqual(doc.stock_items[0].variance_qty, 0)
        self.assertEqual(doc.expected_cash, 140)
        self.assertEqual(doc.cash_variance, 0)

    def test_variance_requires_explanation(self):
        doc = self._doc()
        doc.status = "Pending Approval"
        doc.cash_handover = 135
        route = frappe._dict({"company": doc.company, "assigned_user": doc.dsr})
        with patch("reckon_distribution.settlement.validate_tenant_owned_doc"), patch(
            "reckon_distribution.settlement.require_tenant"
        ), patch("reckon_distribution.settlement._sync_settlement_from_challan"), patch(
            "reckon_distribution.settlement.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.settlement.frappe.db.exists", return_value=False):
            with self.assertRaises(frappe.ValidationError):
                validate_day_settlement(doc)

    def test_stock_source_includes_approved_returns_for_the_daily_challan(self):
        challan = frappe._dict(
            {
                "items": [
                    frappe._dict(
                        {"item_code": "_Test Item", "qty": 10, "conversion_factor": 2}
                    )
                ],
                "van_warehouse": "_Test Van Warehouse A",
            }
        )
        delivery = frappe._dict(
            {
                "delivery_note": "DN-TEST-001",
                "item_code": "_Test Item",
                "qty": 3,
                "stock_qty": 3,
            }
        )
        returned = frappe._dict({"item_code": "_Test Item", "qty": 1, "uom": "Nos"})

        with patch("reckon_distribution.settlement._stock_uom", return_value="Nos"), patch(
            "reckon_distribution.settlement._challan_delivery_rows", return_value=[delivery]
        ), patch("reckon_distribution.settlement.frappe.get_all", return_value=[returned]), patch(
            "reckon_distribution.settlement._stock_quantity", return_value=1
        ):
            source = _challan_stock_source(challan)

        self.assertEqual(source["_Test Item"]["loaded_qty"], 20)
        self.assertEqual(source["_Test Item"]["delivered_qty"], 3)
        self.assertEqual(source["_Test Item"]["returned_qty"], 1)

    def test_create_settlement_links_the_daily_challan(self):
        challan = frappe._dict(
            {
                "name": "VLC-TEST-001",
                "company": "_Test Tenant Company A",
                "posting_date": "2026-10-11",
                "route": "_Test Route A",
                "dsr": "dsr@example.com",
                "db_set": MagicMock(),
            }
        )
        settlement = frappe._dict({"name": "SET-TEST-001", "insert": MagicMock()})

        with patch(
            "reckon_distribution.settlement.get_tenant_doc", return_value=challan
        ), patch("reckon_distribution.settlement._require_manager_or_dsr"), patch(
            "reckon_distribution.settlement._validate_challan_status"
        ), patch("reckon_distribution.settlement.frappe.db.get_value", return_value=None), patch(
            "reckon_distribution.settlement.frappe.get_doc", return_value=settlement
        ) as get_doc:
            result = create_day_settlement(challan.name)

        self.assertEqual(result, settlement.name)
        settlement.insert.assert_called_once_with()
        self.assertEqual(get_doc.call_args.args[0]["challan"], challan.name)
        challan.db_set.assert_called_once_with(
            "day_settlement", settlement.name, update_modified=False
        )
