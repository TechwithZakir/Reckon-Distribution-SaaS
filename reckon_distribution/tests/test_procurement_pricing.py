from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.company_context import prepare_direct_rate_purchase_document


class TestDirectRateProcurement(FrappeTestCase):
    def test_purchase_documents_do_not_keep_the_global_buying_price_list(self):
        for doctype in ("Purchase Order", "Purchase Receipt", "Purchase Invoice"):
            document = frappe._dict(
                {
                    "doctype": doctype,
                    "docstatus": 0,
                    "buying_price_list": "Standard Buying",
                    "price_list_currency": "BDT",
                    "plc_conversion_rate": 0,
                    "ignore_pricing_rule": 0,
                }
            )

            prepare_direct_rate_purchase_document(document)

            self.assertIsNone(document.buying_price_list)
            self.assertIsNone(document.price_list_currency)
            self.assertEqual(document.plc_conversion_rate, 1)
            self.assertEqual(document.ignore_pricing_rule, 1)

    def test_submitted_purchase_document_keeps_its_historical_pricing_fields(self):
        document = frappe._dict(
            {
                "doctype": "Purchase Receipt",
                "docstatus": 1,
                "buying_price_list": "Standard Buying",
                "price_list_currency": "BDT",
                "plc_conversion_rate": 1,
                "ignore_pricing_rule": 0,
            }
        )

        prepare_direct_rate_purchase_document(document)

        self.assertEqual(document.buying_price_list, "Standard Buying")
        self.assertEqual(document.ignore_pricing_rule, 0)
