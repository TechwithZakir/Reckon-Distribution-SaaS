from __future__ import annotations

import unittest

from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate, nowdate

from reckon_distribution.demo_data import (
    DEMO_RECORD_COUNT,
    ROLLBACK_ORDER,
    SEED_SCHEMA_REQUIREMENTS,
    TRANSACTION_PLAN,
    _fiscal_period,
    _sample_date,
)


class TestDistributionDemoDataPlan(FrappeTestCase):
    def test_demo_transaction_plan_contains_exactly_one_hundred_records(self):
        self.assertEqual(sum(quantity for _, quantity in TRANSACTION_PLAN), DEMO_RECORD_COUNT)

    def test_sample_dates_cover_the_current_and_prior_six_months(self):
        today = getdate(nowdate())
        start = add_months(today, -6)

        self.assertEqual(_sample_date(start, 0, 10), start)
        self.assertEqual(_sample_date(start, 9, 10), today)
        self.assertGreaterEqual(_sample_date(start, 5, 10), add_days(start, 1))

    def test_fiscal_period_preserves_the_configured_year_start(self):
        start, end = _fiscal_period("2026-04-12", 7, 1)

        self.assertEqual(str(start), "2025-07-01")
        self.assertEqual(str(end), "2026-06-30")

    def test_purchase_receipt_uses_the_erpnext_v16_delivery_reference(self):
        receipt_fields = SEED_SCHEMA_REQUIREMENTS["Purchase Receipt"]

        self.assertIn("supplier_delivery_note", receipt_fields)
        self.assertNotIn("bill_no", receipt_fields)

    def test_rollback_reverses_operational_dependents_before_source_documents(self):
        self.assertLess(ROLLBACK_ORDER.index("DSR Day Settlement"), ROLLBACK_ORDER.index("DSR Challan"))
        self.assertLess(ROLLBACK_ORDER.index("Delivery Note"), ROLLBACK_ORDER.index("DSR Challan"))
        self.assertLess(ROLLBACK_ORDER.index("Purchase Invoice"), ROLLBACK_ORDER.index("Purchase Receipt"))
        self.assertLess(ROLLBACK_ORDER.index("Purchase Receipt"), ROLLBACK_ORDER.index("Purchase Order"))

    def test_seed_requires_the_native_stock_entry_links_used_by_rollback(self):
        self.assertIn("rd_van_loading_challan", SEED_SCHEMA_REQUIREMENTS["Stock Entry"])
        self.assertIn("rd_dsr_day_settlement", SEED_SCHEMA_REQUIREMENTS["Stock Entry"])


if __name__ == "__main__":
    unittest.main()
