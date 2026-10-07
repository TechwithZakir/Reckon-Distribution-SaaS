from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.settlement import validate_day_settlement


class TestDSRDaySettlement(FrappeTestCase):
    def _doc(self, variance_reason=None):
        return frappe._dict(
            {
                "name": "SET-TEST-001",
                "company": "_Test Tenant Company A",
                "route": "_Test Route A",
                "dsr": "dsr@example.com",
                "status": "Draft",
                "opening_cash": 100,
                "confirmed_cash_collections": 50,
                "approved_expenses": 10,
                "approved_refunds": 0,
                "cash_handover": 100,
                "counted_cash": 40,
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
        ), patch("reckon_distribution.settlement.get_tenant_doc", return_value=route):
            validate_day_settlement(doc)

        self.assertEqual(doc.stock_items[0].expected_closing_qty, 7)
        self.assertEqual(doc.stock_items[0].variance_qty, 0)
        self.assertEqual(doc.expected_cash, 40)
        self.assertEqual(doc.cash_variance, 0)

    def test_variance_requires_explanation(self):
        doc = self._doc()
        doc.counted_cash = 35
        route = frappe._dict({"company": doc.company, "assigned_user": doc.dsr})
        with patch("reckon_distribution.settlement.validate_tenant_owned_doc"), patch(
            "reckon_distribution.settlement.require_tenant"
        ), patch("reckon_distribution.settlement.get_tenant_doc", return_value=route):
            with self.assertRaises(frappe.ValidationError):
                validate_day_settlement(doc)
