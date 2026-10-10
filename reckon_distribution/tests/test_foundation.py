from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution import hooks
from reckon_distribution.compat import FrappeVersion, _major
from reckon_distribution.constants import DISTRIBUTION_WORKSPACE, HRMS_APP_NAME, OPERATIONAL_ROLES


class TestFoundation(FrappeTestCase):
    def test_required_app_does_not_include_hrms(self):
        self.assertIn("erpnext", hooks.required_apps)
        self.assertNotIn(HRMS_APP_NAME, hooks.required_apps)

    def test_roles_exist_without_forced_home_page(self):
        for role in OPERATIONAL_ROLES:
            self.assertTrue(frappe.db.exists("Role", role.name), role.name)
            self.assertFalse(frappe.db.get_value("Role", role.name, "home_page"))

    def test_workspace_exists_and_is_role_scoped(self):
        self.assertTrue(frappe.db.exists("Workspace", DISTRIBUTION_WORKSPACE))
        workspace = frappe.get_doc("Workspace", DISTRIBUTION_WORKSPACE)
        self.assertEqual(workspace.title, "Distribution Workspace")
        workspace_roles = {row.role for row in workspace.roles}
        for role in OPERATIONAL_ROLES:
            self.assertIn(role.name, workspace_roles)

    def test_app_permission_allows_only_distribution_roles(self):
        from reckon_distribution.api import check_app_permission

        with patch("reckon_distribution.api.frappe.session", frappe._dict(user="field@example.com")):
            with patch("frappe.get_roles", return_value=["Reckon Distribution User"]):
                self.assertTrue(check_app_permission())
            with patch("frappe.get_roles", return_value=["Accounts User"]):
                self.assertFalse(check_app_permission())

    def test_no_login_home_page_override(self):
        self.assertEqual(
            hooks.get_website_user_home_page,
            "reckon_distribution.desk_guard.get_user_home_page",
        )
        self.assertFalse(hasattr(hooks, "role_home_page"))

    def test_distribution_user_home_page_is_distribution_workspace(self):
        from reckon_distribution.desk_guard import get_user_home_page

        with patch("frappe.get_roles", return_value=["Reckon Distribution User"]):
            self.assertEqual(get_user_home_page("field@example.com"), "desk/distribution")

    def test_system_manager_home_page_is_native(self):
        from reckon_distribution.desk_guard import get_user_home_page

        with patch("frappe.get_roles", return_value=["System Manager", "Reckon Distribution User"]):
            self.assertIsNone(get_user_home_page("admin@example.com"))

    def test_distribution_user_cannot_load_other_desk_page(self):
        from reckon_distribution.desk_guard import getpage

        with patch("frappe.get_roles", return_value=["Reckon Distribution User"]):
            with patch("frappe.session", frappe._dict(user="field@example.com")):
                with self.assertRaises(frappe.DoesNotExistError):
                    getpage("selling")

    def test_system_manager_can_load_desktop_page_by_name_argument(self):
        from reckon_distribution.desk_guard import getpage

        with patch("frappe.get_roles", return_value=["System Manager"]):
            with patch("frappe.session", frappe._dict(user="admin@example.com")):
                with patch("frappe.desk.desk_page.getpage", return_value={"name": "desktop"}) as getpage_mock:
                    self.assertEqual(getpage(name="desktop"), {"name": "desktop"})
                    getpage_mock.assert_called_once_with("desktop")

    def test_distribution_desk_page_exists_for_restricted_users(self):
        page_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "page"
            / "distribution"
            / "distribution.json"
        )

        self.assertTrue(page_path.exists())

    def test_distribution_generic_api_rejects_unrelated_doctype(self):
        from reckon_distribution.desk_guard import _guard_distribution_api_request

        with patch("frappe.local.form_dict", frappe._dict(doctype="Sales Invoice")):
            with self.assertRaises(frappe.PermissionError):
                _guard_distribution_api_request("/api/method/frappe.client.get_list")

    def test_distribution_generic_api_allows_scoped_native_master(self):
        from reckon_distribution.desk_guard import _guard_distribution_api_request

        with patch("frappe.local.form_dict", frappe._dict(doctype="Item")):
            _guard_distribution_api_request("/api/method/frappe.desk.reportview.get")

    def test_distribution_generic_api_allows_user_saved_list_filters(self):
        from reckon_distribution.desk_guard import _guard_distribution_api_request

        with patch("frappe.local.form_dict", frappe._dict(doctype="List Filter")):
            _guard_distribution_api_request("/api/method/frappe.desk.reportview.get_list")

    def test_distribution_generic_api_allows_language_link_titles(self):
        from reckon_distribution.desk_guard import _guard_distribution_api_request

        with patch("frappe.local.form_dict", frappe._dict(doctype="Language")):
            _guard_distribution_api_request("/api/method/frappe.desk.search.get_link_title")

    def test_internal_distribution_records_are_not_navigation_pages(self):
        from reckon_distribution.desk_guard import ALLOWED_DISTRIBUTION_PAGES

        self.assertNotIn("distribution-master-scope", ALLOWED_DISTRIBUTION_PAGES)
        self.assertNotIn("company-uom-profile", ALLOWED_DISTRIBUTION_PAGES)
        self.assertNotIn("user", ALLOWED_DISTRIBUTION_PAGES)
        self.assertIn("dsr-delivery", ALLOWED_DISTRIBUTION_PAGES)

    def test_distribution_master_setup_page_exists(self):
        page_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "page"
            / "distribution_master_setup"
            / "distribution_master_setup.json"
        )

        self.assertTrue(page_path.exists())

    def test_dsr_delivery_page_is_not_an_alias_to_field_sales(self):
        page_path = Path(__file__).parents[1] / "distribution" / "page" / "dsr_delivery" / "dsr_delivery.js"
        source = page_path.read_text()
        self.assertNotIn('frappe.set_route("field-sales")', source)
        self.assertIn('frappe.pages["dsr-delivery"]', source)

    def test_distribution_workspace_hides_public_shell_and_stock_ledger_tile(self):
        distribution_js = (
            Path(__file__).parents[1] / "distribution" / "page" / "distribution" / "distribution.js"
        ).read_text()
        van_loading_js = (
            Path(__file__).parents[1] / "distribution" / "page" / "van_loading" / "van_loading.js"
        ).read_text()
        self.assertNotIn('__("Web Shell")', distribution_js)
        self.assertNotIn('tile("Stock custody"', van_loading_js)

    def test_distribution_native_forms_have_explicit_dense_layout(self):
        doctype_root = Path(__file__).parents[1] / "distribution" / "doctype"
        user_forms = {
            "distribution_route",
            "distribution_settings",
            "dsr_collection_receipt",
            "dsr_day_settlement",
            "dsr_due_assignment",
            "outlet_visit",
            "retailer_route_assignment",
            "return_inspection",
            "sr_order",
            "van_loading_acknowledgement",
            "van_loading_challan",
        }
        for directory in user_forms:
            metadata = json.loads(
                (doctype_root / directory / f"{directory}.json").read_text()
            )
            field_types = {field["fieldtype"] for field in metadata["fields"]}
            self.assertIn("Column Break", field_types, directory)
            self.assertIn("field_order", metadata)

    def test_dsr_day_settlement_uses_two_column_sections(self):
        path = (
            Path(__file__).parents[1]
            / "distribution"
            / "doctype"
            / "dsr_day_settlement"
            / "dsr_day_settlement.json"
        )
        metadata = json.loads(path.read_text())
        order = metadata["field_order"]
        self.assertLess(order.index("settlement_date"), order.index("column_break_1"))
        self.assertLess(order.index("status"), order.index("section_break_cash"))
        self.assertLess(order.index("approved_expenses"), order.index("column_break_2"))
        self.assertLess(order.index("counted_cash"), order.index("section_break_variance"))
        self.assertLess(order.index("cash_variance"), order.index("column_break_3"))

    def test_distribution_module_uses_app_workspace_route(self):
        from reckon_distribution.saas_module import get_module_definition

        self.assertEqual(get_module_definition()["workspace"], "app/distribution")

    def test_distribution_does_not_register_global_desk_assets(self):
        hooks = (Path(__file__).parents[1] / "hooks.py").read_text()
        self.assertNotIn("app_include_css", hooks)
        self.assertNotIn("app_include_js", hooks)

    def test_distribution_settings_is_company_scoped_two_column_form(self):
        path = Path(__file__).parents[1] / "distribution" / "doctype" / "distribution_settings" / "distribution_settings.json"
        metadata = json.loads(path.read_text())
        self.assertEqual(metadata["issingle"], 0)
        self.assertEqual(
            [field["fieldname"] for field in metadata["fields"] if field["fieldtype"] == "Column Break"],
            ["column_break_1"],
        )
        self.assertEqual(metadata["autoname"], "field:company")

    def test_distribution_exposes_warehouse_setup(self):
        guard = (Path(__file__).parents[1] / "desk_guard.py").read_text()
        install = (Path(__file__).parents[1] / "install.py").read_text()
        self.assertIn('"warehouse"', guard)
        self.assertIn("Distribution Warehouses", install)
        self.assertNotIn('"rd_layout_column_2", "fieldtype": "Column Break"', install)

    def test_distribution_restricts_company_lookup_for_tenant_users(self):
        warehouse = (Path(__file__).parents[1] / "warehouse.py").read_text()
        hooks = (Path(__file__).parents[1] / "hooks.py").read_text()
        self.assertIn("get_company_query", warehouse)
        self.assertIn("get_children", warehouse)
        self.assertIn('"Company": "reckon_distribution.warehouse.get_company_query"', hooks)
        self.assertIn("User Permission", warehouse)
        self.assertIn("apply_to_all_doctypes", warehouse)


class TestCompatibilityHelpers(unittest.TestCase):
    def test_major_version_parser(self):
        self.assertEqual(_major("15.65.2"), 15)
        self.assertEqual(_major("16.0.0-dev"), 16)
        self.assertEqual(_major("bad-version"), 0)

    def test_version_properties_are_explicit(self):
        self.assertTrue(FrappeVersion(15, "15.0.0").supports_v15)
        self.assertTrue(FrappeVersion(16, "16.0.0").supports_v16)
        self.assertFalse(FrappeVersion(17, "17.0.0").supports_v15)
