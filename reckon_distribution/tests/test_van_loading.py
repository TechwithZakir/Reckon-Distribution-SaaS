from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.van_loading import (
    _apply_challan_pricing,
    _has_active_company_assignment,
    acknowledge_van_loading,
    amend_van_loading_challan,
    approve_van_loading_challan,
    cancel_van_loading_challan,
    create_van_loading_stock_entry,
    validate_van_loading_acknowledgement,
    validate_van_loading_stock_entry,
)


class TestVanLoadingControls(FrappeTestCase):
    def test_challan_pricing_calculates_saleable_bill_and_excludes_free_goods(self):
        challan = frappe._dict(
            {
                "company": "_Test Tenant Company A",
                "items": [
                    frappe._dict({"qty": 10, "uom": "Nos", "stock_category": "Saleable"}),
                    frappe._dict({"qty": 5, "uom": "Nos", "stock_category": "Supplier Free"}),
                ],
            }
        )
        with patch(
            "reckon_distribution.van_loading._get_challan_price_list",
            return_value="_Test Sales Price List",
        ), patch(
            "reckon_distribution.van_loading._get_challan_unit_price",
            return_value=12.5,
        ) as get_price:
            challan.items[0].item_code = "_Test Item"
            _apply_challan_pricing(challan)

        self.assertEqual(challan.price_list, "_Test Sales Price List")
        self.assertEqual(challan.items[0].unit_price, 12.5)
        self.assertEqual(challan.items[0].total_price, 125)
        self.assertEqual(challan.items[1].unit_price, 0)
        self.assertEqual(challan.items[1].total_price, 0)
        self.assertEqual(challan.total_bill_amount, 125)
        get_price.assert_called_once()

    def test_challan_pricing_keeps_a_manual_unit_price(self):
        challan = frappe._dict(
            {
                "company": "_Test Tenant Company A",
                "items": [
                    frappe._dict(
                        {
                            "item_code": "_Test Item",
                            "qty": 2,
                            "uom": "Nos",
                            "unit_price": 9,
                            "stock_category": "Saleable",
                        }
                    )
                ],
            }
        )
        with patch(
            "reckon_distribution.van_loading._get_challan_price_list",
            return_value=None,
        ), patch(
            "reckon_distribution.van_loading._get_challan_unit_price",
            return_value=0,
        ) as get_price:
            _apply_challan_pricing(challan)

        self.assertEqual(challan.items[0].unit_price, 9)
        self.assertEqual(challan.items[0].total_price, 18)
        get_price.assert_not_called()

    def test_dsr_company_check_uses_active_tenant_assignment(self):
        with patch("reckon_distribution.van_loading.frappe.db.exists", return_value=True) as exists:
            self.assertTrue(_has_active_company_assignment("dsr@example.com", "_Test Tenant Company A"))
        exists.assert_called_once_with(
            "Tenant User Assignment",
            {"user": "dsr@example.com", "company": "_Test Tenant Company A", "active": 1},
        )

    def test_dsr_company_check_accepts_materialized_company_permission(self):
        with patch(
            "reckon_distribution.van_loading.frappe.db.exists",
            side_effect=[False, True],
        ) as exists:
            self.assertTrue(_has_active_company_assignment("dsr@example.com", "_Test Tenant Company A"))
        self.assertEqual(exists.call_count, 2)
        self.assertEqual(
            exists.call_args_list[1].args,
            ("User Permission", {"user": "dsr@example.com", "allow": "Company", "for_value": "_Test Tenant Company A"}),
        )

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

    def test_linked_stock_entry_must_match_challan_warehouses(self):
        challan = self._challan()
        challan.distributor_warehouse = "Distributor - TCA"
        challan.van_warehouse = "Van - TCA"
        stock_entry = frappe._dict(
            {
                "name": "STE-TEST-001",
                "company": challan.company,
                "rd_van_loading_challan": challan.name,
                "items": [
                    frappe._dict(
                        {
                            "s_warehouse": challan.distributor_warehouse,
                            "t_warehouse": "Wrong - TCA",
                        }
                    )
                ],
            }
        )

        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=challan):
            with self.assertRaises(frappe.ValidationError):
                validate_van_loading_stock_entry(stock_entry)

    def test_approval_creates_one_submitted_stock_entry(self):
        challan = self._challan(status="Pending Approval")
        challan.update(
            {
                "posting_date": "2026-10-07",
                "distributor_warehouse": "Distributor - TCA",
                "van_warehouse": "Van - TCA",
                "uom": "Nos",
                "conversion_factor": 1,
                "save": lambda: None,
            }
        )
        stock_entry = frappe._dict(
            {"name": "STE-NEW-001", "insert": lambda: None, "submit": lambda: None}
        )
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=challan), patch(
            "reckon_distribution.van_loading._require_manager"
        ), patch("reckon_distribution.van_loading._validate_available_stock"), patch(
            "reckon_distribution.van_loading.frappe.db.get_value", return_value=None
        ), patch(
            "reckon_distribution.van_loading.now_datetime", return_value="2026-10-07 12:00:00"
        ), patch("reckon_distribution.van_loading.frappe.get_doc", return_value=stock_entry) as get_doc:
            result = approve_van_loading_challan(challan.name)

        self.assertEqual(result, "STE-NEW-001")
        self.assertEqual(challan.stock_entry, "STE-NEW-001")
        get_doc.assert_called_once()
        self.assertEqual(get_doc.call_args.args[0]["doctype"], "Stock Entry")

    def test_native_submission_creates_stock_entry_and_marks_challan_submitted(self):
        challan = self._challan(status="Draft")
        challan.update(
            {
                "posting_date": "2026-10-07",
                "distributor_warehouse": "Distributor - TCA",
                "van_warehouse": "Van - TCA",
                "db_set": lambda field, value: setattr(challan, field, value),
            }
        )
        stock_entry = frappe._dict(
            {"name": "STE-NATIVE-001", "insert": lambda: None, "submit": lambda: None}
        )
        with patch("reckon_distribution.van_loading._validate_available_stock"), patch(
            "reckon_distribution.van_loading.frappe.get_doc", return_value=stock_entry
        ):
            result = create_van_loading_stock_entry(challan)

        self.assertEqual(result, "STE-NATIVE-001")
        self.assertEqual(challan.status, "Submitted")
        self.assertEqual(challan.stock_entry, "STE-NATIVE-001")

    def test_cancel_is_idempotent_and_cancels_submitted_stock_entry(self):
        challan = self._challan(status="Approved")
        challan.save = lambda: None
        stock_entry = frappe._dict({"docstatus": 1, "cancel": lambda: setattr(stock_entry, "docstatus", 2)})
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=challan), patch(
            "reckon_distribution.van_loading._require_manager"
        ), patch("reckon_distribution.van_loading.frappe.get_doc", return_value=stock_entry):
            self.assertEqual(cancel_van_loading_challan(challan.name), challan.name)
            self.assertEqual(challan.status, "Cancelled")
            self.assertEqual(stock_entry.docstatus, 2)

        cancelled = self._challan(status="Cancelled")
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=cancelled), patch(
            "reckon_distribution.van_loading._require_manager"
        ):
            self.assertEqual(cancel_van_loading_challan(cancelled.name), cancelled.name)

    def test_amendment_only_starts_from_cancelled_challan(self):
        cancelled = self._challan(status="Cancelled")
        amended = frappe._dict({"name": "VLC-TEST-002", "status": "Draft", "insert": lambda: None})
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=cancelled), patch(
            "reckon_distribution.van_loading._require_manager"
        ), patch("reckon_distribution.van_loading.frappe.copy_doc", return_value=amended):
            result = amend_van_loading_challan(cancelled.name)

        self.assertEqual(result, amended.name)
        self.assertEqual(amended.status, "Draft")

        approved = self._challan(status="Approved")
        with patch("reckon_distribution.van_loading.get_tenant_doc", return_value=approved), patch(
            "reckon_distribution.van_loading._require_manager"
        ):
            with self.assertRaises(frappe.ValidationError):
                amend_van_loading_challan(approved.name)
