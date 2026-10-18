"""The per-request Desk guard must not write or clear caches (runs without a database)."""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).parents[1] / "reckon_distribution"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeskGuardReadOnlyTests(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda text: text
        frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        frappe.PermissionError = PermissionError
        frappe.DoesNotExistError = LookupError
        frappe.throw = Mock(side_effect=PermissionError)
        frappe.clear_cache = Mock()
        frappe.get_doc = Mock()
        frappe.get_roles = Mock(return_value=["Reckon Distribution User"])
        frappe.session = SimpleNamespace(user="dsr@tenant.example")
        frappe.flags = SimpleNamespace()
        frappe.local = SimpleNamespace(form_dict={}, request=SimpleNamespace(path="/app/distribution"))
        frappe.db = Mock()
        self.frappe = frappe

        gate = ModuleType("reckon_saas_platform.saas_gate")
        gate.is_user_gated = Mock(return_value=False)
        self.gate = gate
        warehouse = ModuleType("reckon_distribution.warehouse")
        warehouse.assert_single_company_assignment = Mock(return_value="Horizon")
        self.warehouse = warehouse
        install = ModuleType("reckon_distribution.install")
        install.ensure_standard_doc_type_read_permission = Mock(return_value=False)
        self.install = install

        with patch.dict(sys.modules, {"frappe": frappe}):
            constants = _load(APP / "constants.py", "reckon_distribution.constants")
        self.modules = {
            "frappe": frappe,
            "reckon_saas_platform": ModuleType("reckon_saas_platform"),
            "reckon_saas_platform.saas_gate": gate,
            "reckon_distribution.constants": constants,
            "reckon_distribution.warehouse": warehouse,
            "reckon_distribution.install": install,
        }
        with patch.dict(sys.modules, self.modules):
            self.guard = _load(APP / "desk_guard.py", "desk_guard_under_test")

    def _restrict(self, path):
        self.frappe.local.request.path = path
        with patch.dict(sys.modules, self.modules):
            self.guard.restrict_distribution_desk_request()

    def test_request_guard_does_not_write_or_clear_cache(self):
        for path in ("/app/distribution", "/desk/home", "/api/method/frappe.client.get_list", "/app"):
            self._restrict(path)

        self.frappe.clear_cache.assert_not_called()
        self.frappe.get_doc.assert_not_called()
        self.frappe.db.sql.assert_not_called()
        self.frappe.db.set_value.assert_not_called()
        self.install.ensure_standard_doc_type_read_permission.assert_not_called()
        self.assertEqual(self.warehouse.assert_single_company_assignment.call_count, 4)

    def test_gate_blocked_request_skips_workspace_routing(self):
        self.frappe.flags.saas_gate_blocked = True
        self._restrict("/app")
        self.warehouse.assert_single_company_assignment.assert_not_called()
        self.assertFalse(getattr(self.frappe.flags, "distribution_redirect", None))

    def test_workspace_redirect_does_not_override_gate_redirect(self):
        self.frappe.flags.distribution_redirect = "/desk/distribution"
        self.frappe.flags.saas_gate_redirect = "/reckonerp-subscription"
        response = Mock(headers={"Location": "/reckonerp-subscription"})
        self.guard.redirect_distribution_desk_response(response, None)
        self.assertEqual(response.headers["Location"], "/reckonerp-subscription")

    def test_home_page_follows_subscription_gate(self):
        self.gate.is_user_gated.return_value = True
        self.assertEqual(self.guard.get_user_home_page("dsr@tenant.example"), "reckonerp-subscription")
        self.gate.is_user_gated.return_value = False
        self.assertEqual(self.guard.get_user_home_page("dsr@tenant.example"), "desk/distribution")

    def test_assignment_sync_grants_role_and_metadata_once(self):
        self.frappe.get_roles.return_value = []
        self.frappe.db.exists.return_value = True
        self.install.ensure_standard_doc_type_read_permission.return_value = True
        assignment = {"user": "dsr@tenant.example", "active": 1, "role_profile": "DSR"}
        doc = SimpleNamespace(get=assignment.get)

        with patch.dict(sys.modules, self.modules):
            self.guard.sync_tenant_user_access(doc)

        granted = {call.args[0] for call in self.install.ensure_standard_doc_type_read_permission.call_args_list}
        self.assertEqual(granted, {"DSR", "Reckon Distribution User"})
        self.frappe.clear_cache.assert_called_once_with(doctype="DocType")
        self.frappe.get_doc.return_value.add_roles.assert_called_once_with("Reckon Distribution User")

    def test_assignment_sync_skips_inactive_and_unchanged(self):
        doc = SimpleNamespace(get={"user": "x@tenant.example", "active": 0}.get)
        with patch.dict(sys.modules, self.modules):
            self.guard.sync_tenant_user_access(doc)
        self.install.ensure_standard_doc_type_read_permission.assert_not_called()

        self.frappe.get_roles.return_value = ["Reckon Distribution User"]
        doc = SimpleNamespace(get={"user": "x@tenant.example", "active": 1, "role_profile": "SR"}.get)
        with patch.dict(sys.modules, self.modules):
            self.guard.sync_tenant_user_access(doc)
        self.frappe.clear_cache.assert_not_called()
        self.frappe.get_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
