from __future__ import annotations

import unittest

from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate, nowdate

from reckon_distribution.demo_data import (
    DEMO_RECORD_COUNT,
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


if __name__ == "__main__":
    unittest.main()
