"""Service regression tests runnable without a Frappe database."""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


class CompanyPermissionTests(unittest.TestCase):
    def setUp(self):
        self.frappe = ModuleType("frappe")
        self.frappe._ = lambda text: text
        self.frappe.whitelist = lambda: lambda fn: fn
        self.frappe.PermissionError = PermissionError
        self.frappe.throw = Mock(side_effect=PermissionError)
        self.frappe.clear_cache = Mock()
        self.frappe.delete_doc = Mock()
        self.frappe.get_doc = Mock()
        security = ModuleType("reckon_distribution.tenant_security")
        security.require_tenant = Mock()
        security.user_can_bypass_tenant = Mock(return_value=False)
        self.security = security
        path = Path(__file__).parents[1] / "reckon_distribution" / "warehouse.py"
        spec = importlib.util.spec_from_file_location("permission_service_under_test", path)
        self.service = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": self.frappe,
                                     "reckon_distribution.tenant_security": security}):
            spec.loader.exec_module(self.service)
        self.assignment = SimpleNamespace(company="Horizon")
        self.permission = SimpleNamespace(
            name="permission-1", for_value="Horizon", apply_to_all_doctypes=1,
            is_default=1, hide_descendants=1,
        )

    def test_missing_permission_created_and_verified(self):
        self.frappe.get_all = Mock(side_effect=[[self.assignment], [], [self.permission]])
        self.service.sync_user_company_permission("team@example.com", "Horizon")
        self.frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
        self.frappe.clear_cache.assert_called_once_with(user="team@example.com")

    def test_repeat_does_not_delete_or_recreate_correct_permission(self):
        self.frappe.get_all = Mock(side_effect=[
            [self.assignment], [self.permission], [self.permission],
        ])
        self.service.sync_user_company_permission("team@example.com", "Horizon")
        self.frappe.delete_doc.assert_not_called()
        self.frappe.get_doc.assert_not_called()

    def test_wrong_or_missing_assignment_cannot_report_success(self):
        for assignments in ([], [SimpleNamespace(company="Other")]):
            self.frappe.get_all = Mock(return_value=assignments)
            with self.assertRaises(PermissionError):
                self.service.sync_user_company_permission("team@example.com", "Horizon")

    def test_missing_permission_after_insert_cannot_report_success(self):
        self.frappe.get_all = Mock(side_effect=[[self.assignment], [], []])
        with self.assertRaises(PermissionError):
            self.service.sync_user_company_permission("team@example.com", "Horizon")

    def test_deactivation_removes_company_permission(self):
        self.frappe.get_all = Mock(side_effect=[[], [self.permission], []])
        self.service.sync_user_company_permission("team@example.com")
        self.frappe.delete_doc.assert_called_once_with(
            "User Permission", "permission-1", ignore_permissions=True, force=True,
        )

    def test_multiple_assignments_rejected_before_permission_changes(self):
        self.frappe.get_all = Mock(return_value=[self.assignment, SimpleNamespace(company="Other")])
        with self.assertRaises(PermissionError):
            self.service.sync_user_company_permission("team@example.com")
        self.frappe.delete_doc.assert_not_called()


class MasterOwnershipTests(unittest.TestCase):
    def setUp(self):
        CompanyPermissionTests.setUp(self)
        self.security.validate_tenant_owned_doc = Mock()
        self.security.require_tenant.return_value = SimpleNamespace(company="Horizon")
        self.frappe.session = SimpleNamespace(user="admin@horizon.example")
        self.frappe.db = Mock()
        path = Path(__file__).parents[1] / "reckon_distribution" / "master_data.py"
        spec = importlib.util.spec_from_file_location("master_service_under_test", path)
        self.master = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": self.frappe,
                                     "reckon_distribution.tenant_security": self.security}):
            spec.loader.exec_module(self.master)

    def test_spoofed_company_cannot_claim_existing_master(self):
        doc = Mock(doctype="Item", name="other-item")
        doc.is_new.return_value = False
        doc.get.return_value = "Horizon"
        for stored_owner in ("Other", None):
            self.frappe.db.get_value.return_value = stored_owner
            with self.assertRaises(PermissionError):
                self.master.validate_shared_master_change(doc)
            self.assertFalse(self.master.has_shared_master_permission(doc, ptype="write"))

    def test_new_master_rejects_other_company(self):
        doc = Mock(doctype="Item")
        doc.is_new.return_value = True
        doc.get.return_value = "Other"
        self.assertFalse(self.master.has_shared_master_permission(doc, ptype="create"))
        with self.assertRaises(PermissionError):
            self.master.validate_shared_master_change(doc)

    def test_search_cannot_impersonate_another_user(self):
        with self.assertRaises(PermissionError):
            self.master.search_company_master("Item", user="other@example.com")
        self.security.require_tenant.assert_not_called()


if __name__ == "__main__":
    unittest.main()
