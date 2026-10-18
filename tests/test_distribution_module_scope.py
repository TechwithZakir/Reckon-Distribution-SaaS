"""Distribution must leave other SaaS modules' tenants alone (runs without a database)."""
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import test_desk_guard_read_only as base


class DistributionModuleScopeTests(unittest.TestCase):
    def setUp(self):
        # Reuse the stubbed frappe/desk_guard setup without re-collecting those tests.
        base.DeskGuardReadOnlyTests.setUp(self)
        saas = ModuleType("reckon_saas_platform.saas")
        saas.get_user_module_keys = Mock(return_value=[])
        saas.get_company_module_keys = Mock(return_value=[])
        self.saas = saas
        self.modules["reckon_saas_platform.saas"] = saas
        # A tenant profile with no Distribution role reaches the assignment fallback.
        self.frappe.get_roles.return_value = []
        self.frappe.db.exists.return_value = True
        self.frappe.db.get_value.return_value = "Company Admin"

    def _only(self):
        with patch.dict(sys.modules, self.modules):
            return self.guard._is_distribution_only_user("owner@tenant.example")

    def test_legacy_tenant_without_modules_is_distribution(self):
        self.assertTrue(self._only())

    def test_distribution_subscriber_is_distribution(self):
        self.saas.get_user_module_keys.return_value = ["distribution"]
        self.assertTrue(self._only())

    def test_other_module_tenant_is_not_claimed(self):
        self.saas.get_user_module_keys.return_value = ["accounts"]
        self.assertFalse(self._only())

    def test_multi_module_tenant_is_left_to_the_union_guard(self):
        self.saas.get_user_module_keys.return_value = ["accounts", "distribution"]
        self.assertFalse(self._only())

    def test_role_sync_skips_other_module_companies(self):
        self.saas.get_company_module_keys.return_value = ["accounts"]
        doc = SimpleNamespace(get={"user": "u@t.example", "active": 1, "role_profile": "Company Admin",
                                   "company": "Acme"}.get)
        with patch.dict(sys.modules, self.modules):
            self.guard.sync_tenant_user_access(doc)
        self.install.ensure_standard_doc_type_read_permission.assert_not_called()
        self.frappe.get_doc.assert_not_called()

    def test_role_sync_runs_for_distribution_companies(self):
        self.saas.get_company_module_keys.return_value = ["distribution"]
        doc = SimpleNamespace(get={"user": "u@t.example", "active": 1, "role_profile": "DSR",
                                   "company": "Acme"}.get)
        with patch.dict(sys.modules, self.modules):
            self.guard.sync_tenant_user_access(doc)
        self.frappe.get_doc.return_value.add_roles.assert_called_once_with("Reckon Distribution User")


if __name__ == "__main__":
    unittest.main()
