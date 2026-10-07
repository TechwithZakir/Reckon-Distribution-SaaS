from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.collection import confirm_collection, validate_collection_receipt


class TestDSRCollectionReceipt(FrappeTestCase):
    def _receipt(self, method="Cash"):
        return frappe._dict(
            {
                "name": "DCR-TEST-001",
                "company": "_Test Tenant Company A",
                "customer": "_Test Customer A",
                "route": "_Test Route A",
                "dsr": "dsr@example.com",
                "amount": 200,
                "payment_method": method,
                "reference_no": "REF-001" if method in {"Bank", "MFS"} else None,
                "receiving_account": "Cash - TCA",
                "idempotency_key": "offline-device-001",
                "status": "Draft",
                "payment_entry": None,
            }
        )

    def test_bank_collection_enters_pending_verification(self):
        receipt = self._receipt("Bank")
        route = frappe._dict({"company": receipt.company, "assigned_user": receipt.dsr})
        with patch("reckon_distribution.collection.validate_tenant_owned_doc"), patch(
            "reckon_distribution.collection.require_tenant"
        ), patch("reckon_distribution.collection.validate_master_scope"), patch(
            "reckon_distribution.collection.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.collection.get_user_companies", return_value=[receipt.company]), patch(
            "reckon_distribution.collection._validate_idempotency"
        ):
            validate_collection_receipt(receipt)

        self.assertEqual(receipt.status, "Pending Verification")

    def test_cash_collection_posts_one_on_account_payment(self):
        receipt = self._receipt()
        payment = frappe._dict({"name": "ACC-PAY-001", "insert": lambda: None, "submit": lambda: None})
        receipt.save = lambda: None
        with patch("reckon_distribution.collection.get_tenant_doc", return_value=receipt), patch(
            "reckon_distribution.collection._require_collector_or_manager"
        ), patch("reckon_distribution.collection.frappe.db.get_value", return_value=receipt.company), patch(
            "erpnext.accounts.party.get_party_account", return_value="Debtors - TCA"
        ), patch("reckon_distribution.collection.frappe.get_doc", return_value=payment) as get_doc:
            result = confirm_collection(receipt.name)

        self.assertEqual(result, "ACC-PAY-001")
        self.assertEqual(receipt.status, "Confirmed")
        self.assertEqual(receipt.payment_entry, "ACC-PAY-001")
        self.assertEqual(get_doc.call_args.args[0]["payment_type"], "Receive")
        self.assertNotIn("references", get_doc.call_args.args[0])

    def test_bank_collection_cannot_bypass_manager_verification(self):
        receipt = self._receipt("Bank")
        with patch("reckon_distribution.collection.get_tenant_doc", return_value=receipt), patch(
            "reckon_distribution.collection._require_collector_or_manager"
        ):
            with self.assertRaises(frappe.ValidationError):
                confirm_collection(receipt.name)
