from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.van_loading import (
    acknowledge_van_loading,
    approve_van_loading_challan,
    validate_van_loading_acknowledgement,
)


class TestVanLoadingControls(FrappeTestCase):
    def _challan(self, status="Approved"):
        return frappe._dict(
            {
                "name": "VLC-TEST-001",
                "company": "_Test Tenant Company A",
                "status": status,
                "dsr": "dsr@example.com",
                "stock_entry": "STE-TEST-001" if status == "Approved" else None,
                "items": [
                    frappe._dict(
                        {
                            "name": "VLC-ITEM-001",
                            "item_code": "_Test Item",
                            "qty": 10,
                        }
                    )
                ],
            }
        )

    def test_acknowledgement_reconciles_partial_acceptance_and_rejection(self):
        challan = self._challan()
        acknowledgement = frappe._dict(
            {
                "company": challan.company,
                "challan": challan.name,
                "dsr": challan.dsr,
                "items": [
                    frappe._dict(
                        {
                            "idx": 1,
                            "challan_item": "VLC-ITEM-001",
                            "loaded_qty": 999,
                            "accepted_qty": 7,
                            "rejected_qty": 3,
                            "rejection_reason": "Damaged cartons",
                        }
                    )
                ],
            }
        )

        with patch("reckon_distribution.van_loading.validate_tenant_owned_doc"), patch(
            "reckon_distribution.van_loading.get_tenant_doc", return_value=challan
        ), patch("reckon_distribution.van_loading.user_can_bypass_tenant", return_value=True):
            validate_van_loading_acknowledgement(acknowledgement)

        self.assertEqual(acknowledgement.get("items")[0].loaded_qty, 10)

    def test_acknowledgement_requires_rejection_reason(self):
        challan = self._challan()
        acknowledgement = frappe._dict(
            {
                "company": challan.company,
                "challan": challan.name,
                "dsr": challan.dsr,
                "items": [
                    frappe._dict(
                        {
                            "idx": 1,
                            "challan_item": "VLC-ITEM-001",
                            "accepted_qty": 8,
                            "rejected_qty": 2,
                        }
                    )
                ],
            }
        )

        with patch("reckon_distribution.van_loading.validate_tenant_owned_doc"), patch(
            "reckon_distribution.van_loading.get_tenant_doc", return_value=challan
        ), patch("reckon_distribution.van_loading.user_can_bypass_tenant", return_value=True):
            with self.assertRaises(frappe.ValidationError):
                validate_van_loading_acknowledgement(acknowledgement)

    def test_repeated_approval_returns_existing_stock_entry(self):
        challan = self._challan()
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=challan), patch(
            "reckon_distribution.van_loading._require_manager"
        ):
            self.assertEqual(approve_van_loading_challan(challan.name), "STE-TEST-001")

    def test_acknowledgement_api_is_present_for_dsr_workflow(self):
        self.assertTrue(callable(acknowledge_van_loading))
