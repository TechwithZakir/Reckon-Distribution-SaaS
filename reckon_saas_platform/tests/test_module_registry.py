from unittest.mock import patch

from frappe.tests import IntegrationTestCase as FrappeTestCase

from reckon_saas_platform.module_registry import get_landing_workspace, get_saas_modules


class TestSaaSModuleRegistry(FrappeTestCase):
    def test_discovers_distribution_module_definition(self):
        modules = get_saas_modules()

        self.assertTrue(any(module.key == "distribution" for module in modules))

    def test_landing_workspace_uses_registered_module(self):
        self.assertEqual(get_landing_workspace("distribution"), "distribution")

    def test_hook_string_is_resolved_to_definition(self):
        with patch(
            "frappe.get_hooks",
            return_value=["reckon_distribution.saas_module.get_module_definition"],
        ):
            modules = get_saas_modules()

        self.assertEqual(modules[0].key, "distribution")
        self.assertIn("supplier_provided_goods", modules[0].subscription_features)
