from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution import hooks
from reckon_distribution.compat import FrappeVersion, _major
from reckon_distribution.constants import (
    DISTRIBUTION_SIDEBAR,
    DISTRIBUTION_WORKSPACE,
    HRMS_APP_NAME,
    OPERATIONAL_ROLES,
)


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

    def test_dsr_challan_is_the_native_doctype(self):
        self.assertEqual(frappe.get_meta("DSR Challan").name, "DSR Challan")

    def test_dsr_challan_item_controller_loads(self):
        self.assertEqual(
            frappe.get_controller("DSR Challan Item").__name__, "DSRChallanItem"
        )
        self.assertTrue(frappe.db.exists("DocType", "DSR Challan Item"))

    def test_generated_stock_entry_links_to_dsr_challan(self):
        field = frappe.get_meta("Stock Entry").get_field("rd_van_loading_challan")
        self.assertIsNotNone(field)
        self.assertEqual(field.options, "DSR Challan")

    def test_dsr_challan_is_permitted_for_distribution_roles(self):
        permissions = {
            row.role: row
            for row in frappe.get_meta("DSR Challan").permissions
            if row.role in {"Reckon Distribution Admin", "Reckon Distribution Manager", "Reckon Distribution User"}
        }
        self.assertTrue(permissions["Reckon Distribution Admin"].read)
        self.assertTrue(permissions["Reckon Distribution Manager"].read)
        self.assertTrue(permissions["Reckon Distribution User"].read)
        self.assertTrue(permissions["Reckon Distribution User"].create)
        self.assertTrue(permissions["Reckon Distribution User"].submit)
        self.assertTrue(permissions["Reckon Distribution Admin"].print)
        self.assertTrue(permissions["Reckon Distribution Manager"].print)
        self.assertTrue(permissions["Reckon Distribution User"].print)

    def test_distribution_workspace_contains_dsr_challan_shortcut(self):
        workspace = frappe.get_doc("Workspace", DISTRIBUTION_WORKSPACE)
        self.assertTrue(any(item.link_to == "DSR Challan" for item in workspace.shortcuts))
        self.assertTrue(any(item.link_to == "DSR Challan" for item in workspace.links))

    def test_distribution_sidebar_contains_dsr_challan(self):
        sidebar_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "sidebar"
            / "distribution"
            / "distribution.json"
        )
        sidebar = json.loads(sidebar_path.read_text())
        self.assertTrue(
            any(
                item.get("link_type") == "DocType" and item.get("link_to") == "DSR Challan"
                for item in sidebar["items"]
            )
        )

    def test_distribution_sidebar_home_uses_the_distribution_page(self):
        sidebar_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "sidebar"
            / "distribution"
            / "distribution.json"
        )
        sidebar = json.loads(sidebar_path.read_text())
        home = next(item for item in sidebar["items"] if item.get("label") == "Distribution Home")
        self.assertEqual(home["link_type"], "Page")
        self.assertEqual(home["link_to"], "distribution")

    def test_distribution_sidebar_contains_procurement_documents(self):
        sidebar_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "sidebar"
            / "distribution"
            / "distribution.json"
        )
        sidebar = json.loads(sidebar_path.read_text())
        links = {item.get("link_to") for item in sidebar["items"]}
        self.assertTrue(
            {
                "Purchase Order",
                "Purchase Receipt",
                "Purchase Invoice",
                "Payment Entry",
            }.issubset(links)
        )

    def test_office_expense_documents_are_in_the_sidebar(self):
        sidebar_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "sidebar"
            / "distribution"
            / "distribution.json"
        )
        sidebar = json.loads(sidebar_path.read_text())
        links = {item.get("link_to") for item in sidebar["items"]}
        self.assertTrue({"Office Expense", "Office Expense Settings"}.issubset(links))

    def test_office_expense_permissions_are_limited_to_admin_and_manager(self):
        expense_permissions = {
            row.role: row
            for row in frappe.get_meta("Office Expense").permissions
            if row.role
            in {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
                "Reckon Distribution User",
            }
        }
        self.assertTrue(expense_permissions["Reckon Distribution Admin"].create)
        self.assertTrue(expense_permissions["Reckon Distribution Admin"].submit)
        self.assertTrue(expense_permissions["Reckon Distribution Manager"].create)
        self.assertTrue(expense_permissions["Reckon Distribution Manager"].submit)
        self.assertNotIn("Reckon Distribution User", expense_permissions)

        setup_permissions = {
            row.role: row
            for row in frappe.get_meta("Office Expense Settings").permissions
            if row.role in {"Reckon Distribution Admin", "Reckon Distribution Manager"}
        }
        self.assertTrue(setup_permissions["Reckon Distribution Admin"].write)
        self.assertTrue(setup_permissions["Reckon Distribution Manager"].read)
        self.assertFalse(setup_permissions["Reckon Distribution Manager"].write)

    def test_office_expense_posts_through_a_pay_payment_entry(self):
        expense = json.loads(
            (
                Path(__file__).parents[1]
                / "distribution"
                / "doctype"
                / "office_expense"
                / "office_expense.json"
            ).read_text()
        )
        payment_entry = next(
            field for field in expense["fields"] if field["fieldname"] == "payment_entry"
        )
        self.assertEqual(payment_entry["options"], "Payment Entry")
        self.assertIn("override_doctype_class", Path(hooks.__file__).read_text())
        source = (Path(__file__).parents[1] / "office_expense.py").read_text()
        self.assertIn('"payment_type": "Pay"', source)
        self.assertNotIn("create_office_expense_journal_entry", source)

    def test_office_expense_uses_scoped_link_fields(self):
        doctype_root = Path(__file__).parents[1] / "distribution" / "doctype"
        expense = json.loads((doctype_root / "office_expense" / "office_expense.json").read_text())
        item = json.loads((doctype_root / "office_expense_item" / "office_expense_item.json").read_text())
        payment_method = next(field for field in expense["fields"] if field["fieldname"] == "payment_method")
        category = next(field for field in item["fields"] if field["fieldname"] == "expense_category")
        self.assertEqual((payment_method["fieldtype"], payment_method["options"]), ("Link", "Mode of Payment"))
        self.assertEqual((category["fieldtype"], category["options"]), ("Link", "Account"))
        source = (Path(__file__).parents[1] / "office_expense.py").read_text()
        self.assertIn("get_office_expense_payment_methods", source)
        self.assertIn("get_office_expense_categories", source)

    def test_distribution_dashboard_uses_safe_aggregate_syntax(self):
        source = (Path(__file__).parents[1] / "dashboard.py").read_text()
        self.assertIn('frappe.db.get_value(doctype, filters, {"SUM": fieldname})', source)
        self.assertNotIn('f"sum(`{fieldname}`)"', source)

    def test_distribution_sidebar_groups_core_work_and_reports(self):
        sidebar_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "sidebar"
            / "distribution"
            / "distribution.json"
        )
        sidebar = json.loads(sidebar_path.read_text())
        links = {item.get("link_to") for item in sidebar["items"]}
        labels = {item.get("label") for item in sidebar["items"]}
        self.assertTrue(
            {
                "field-sales",
                "dsr-delivery",
                "DSR Challan",
                "Stock Ledger",
                "Stock Balance",
                "Sales Register",
                "Purchase Register",
                "Accounts Payable",
            }.issubset(links)
        )
        self.assertTrue(
            {"Sales & Delivery", "Purchase", "Reports", "Setup & Access"}.issubset(labels)
        )
        self.assertNotIn("SR Order", links)
        self.assertNotIn("Outlet Visit", links)
        self.assertNotIn("Delivery Note", links)
        self.assertNotIn("DSR Collection Receipt", links)
        self.assertNotIn("Stock Entry", links)
        self.assertNotIn("Warehouse", links)
        self.assertNotIn("distribution-reports", links)

    def test_procurement_permissions_are_limited_to_management_roles(self):
        for doctype in ("Purchase Order", "Purchase Receipt", "Purchase Invoice", "Payment Entry"):
            self.assertTrue(frappe.db.exists("DocType", doctype), doctype)
            permissions = {
                row.role: row
                for row in frappe.get_meta(doctype).permissions
                if row.role in {
                    "Reckon Distribution Admin",
                    "Reckon Distribution Manager",
                    "Reckon Distribution User",
                }
            }
            self.assertTrue(permissions["Reckon Distribution Admin"].create, doctype)
            self.assertTrue(permissions["Reckon Distribution Manager"].create, doctype)
            self.assertFalse(permissions["Reckon Distribution User"].create, doctype)

    def test_procurement_support_doctypes_are_readable_by_management_roles(self):
        for doctype in ("Company", "Buying Settings"):
            permissions = {
                row.role: row
                for row in frappe.get_meta(doctype).permissions
                if row.role in {"Reckon Distribution Admin", "Reckon Distribution Manager"}
            }
            self.assertTrue(permissions["Reckon Distribution Admin"].read, doctype)
            self.assertTrue(permissions["Reckon Distribution Manager"].read, doctype)

    def test_procurement_forms_hide_advanced_fields(self):
        expected = {
            "Purchase Order": "supplier_name",
            "Purchase Receipt": "supplier_name",
            "Purchase Invoice": "update_stock",
            "Payment Entry": "party_name",
        }
        for doctype, fieldname in expected.items():
            self.assertTrue(
                frappe.db.exists(
                    "Property Setter",
                    {
                        "doc_type": doctype,
                        "field_name": fieldname,
                        "property": "hidden",
                        "value": "1",
                    },
                ),
                f"{doctype}.{fieldname}",
            )

    def test_distribution_workspace_sidebar_contains_dsr_challan(self):
        if not frappe.db.exists("DocType", "Workspace Sidebar"):
            self.skipTest("Workspace Sidebar is unavailable in this Frappe version")
        sidebar = frappe.get_doc("Workspace Sidebar", DISTRIBUTION_SIDEBAR)
        self.assertTrue(
            any(
                item.link_type == "DocType" and item.link_to == "DSR Challan"
                for item in sidebar.items
            )
        )

    def test_distribution_workspace_sidebar_home_uses_the_distribution_page(self):
        if not frappe.db.exists("DocType", "Workspace Sidebar"):
            self.skipTest("Workspace Sidebar is unavailable in this Frappe version")
        sidebar = frappe.get_doc("Workspace Sidebar", DISTRIBUTION_SIDEBAR)
        home = next(item for item in sidebar.items if item.label == "Distribution Home")
        self.assertEqual(home.link_type, "Page")
        self.assertEqual(home.link_to, "distribution")

    def test_distribution_workspace_sidebar_uses_native_procurement_doctypes(self):
        if not frappe.db.exists("DocType", "Workspace Sidebar"):
            self.skipTest("Workspace Sidebar is unavailable in this Frappe version")
        sidebar = frappe.get_doc("Workspace Sidebar", DISTRIBUTION_SIDEBAR)
        links = {item.link_to: item.link_type for item in sidebar.items}
        for doctype in ("Purchase Order", "Purchase Receipt", "Purchase Invoice", "Payment Entry"):
            if frappe.db.exists("DocType", doctype):
                self.assertEqual(links.get(doctype), "DocType")

    def test_distribution_workspace_sidebar_includes_core_operational_destinations(self):
        if not frappe.db.exists("DocType", "Workspace Sidebar"):
            self.skipTest("Workspace Sidebar is unavailable in this Frappe version")
        sidebar = frappe.get_doc("Workspace Sidebar", DISTRIBUTION_SIDEBAR)
        links = {item.link_to: item.link_type for item in sidebar.items}
        if frappe.db.exists("DocType", "DSR Challan"):
            self.assertEqual(links.get("DSR Challan"), "DocType")
        for report_name in (
            "Stock Ledger",
            "Stock Balance",
            "Sales Register",
            "Purchase Register",
            "Accounts Payable",
        ):
            if frappe.db.exists("Report", report_name):
                self.assertEqual(links.get(report_name), "Report")
        self.assertNotIn("distribution-reports", links)

    def test_distribution_roles_can_read_stock_ledger_entries(self):
        if not frappe.db.exists("DocType", "Stock Ledger Entry"):
            self.skipTest("Stock Ledger Entry is unavailable in this ERPNext version")
        permissions = {
            row.role: row
            for row in frappe.get_meta("Stock Ledger Entry").permissions
            if row.role
            in {"Reckon Distribution Admin", "Reckon Distribution Manager", "Reckon Distribution User"}
        }
        for role in permissions.values():
            self.assertTrue(role.read)
            self.assertTrue(role.report)

    def test_distribution_roles_can_read_native_doctype_metadata(self):
        permission = frappe.db.exists(
            "DocPerm",
            {"parent": "DocType", "role": "Reckon Distribution User", "permlevel": 0},
        )
        self.assertTrue(permission)
        self.assertTrue(frappe.db.get_value("DocPerm", permission, "read"))

    def test_distribution_allows_native_print_page(self):
        from reckon_distribution.desk_guard import (
            ALLOWED_DESK_PREFIXES,
            ALLOWED_DISTRIBUTION_DOCTYPES,
            ALLOWED_DISTRIBUTION_PAGES,
            DISTRIBUTION_MANAGEMENT_QUERY_REPORTS,
            DISTRIBUTION_QUERY_REPORTS,
        )

        self.assertIn("print", ALLOWED_DISTRIBUTION_PAGES)
        self.assertIn("/app/print", ALLOWED_DESK_PREFIXES)
        self.assertTrue(
            {"Letter Head", "Print Format"}.issubset(ALLOWED_DISTRIBUTION_DOCTYPES)
        )
        self.assertIn("query-report", ALLOWED_DISTRIBUTION_PAGES)
        self.assertIn("Stock Ledger", DISTRIBUTION_QUERY_REPORTS)
        self.assertIn("Stock Balance", DISTRIBUTION_QUERY_REPORTS)
        self.assertTrue(
            {"Sales Register", "Purchase Register"}.issubset(
                DISTRIBUTION_MANAGEMENT_QUERY_REPORTS
            )
        )
        self.assertIn("Accounts Payable", DISTRIBUTION_MANAGEMENT_QUERY_REPORTS)

    def test_distribution_report_roles_match_operational_scope(self):
        expected_roles = {
            "Stock Ledger": {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
                "Reckon Distribution User",
            },
            "Stock Balance": {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
                "Reckon Distribution User",
            },
            "Sales Register": {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
            },
            "Purchase Register": {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
            },
            "Accounts Payable": {
                "Reckon Distribution Admin",
                "Reckon Distribution Manager",
            },
        }
        for report_name, roles in expected_roles.items():
            if not frappe.db.exists("Report", report_name):
                self.skipTest(f"{report_name} is unavailable in this ERPNext version")
            assigned_roles = {row.role for row in frappe.get_doc("Report", report_name).roles}
            self.assertTrue(roles.issubset(assigned_roles), report_name)

    def test_distribution_roles_can_read_native_form_dependencies(self):
        role_names = {
            "Reckon Distribution Admin",
            "Reckon Distribution Manager",
            "Reckon Distribution User",
        }
        for doctype in ("Letter Head", "Print Format", "Mode of Payment"):
            permissions = {
                row.role: row
                for row in frappe.get_meta(doctype).permissions
                if row.role in role_names
            }
            for role_name in role_names:
                self.assertTrue(permissions[role_name].read, f"{doctype}: {role_name}")

    def test_distribution_user_has_effective_doctype_metadata_permission(self):
        from reckon_distribution.install import ensure_standard_doc_type_read_permission

        ensure_standard_doc_type_read_permission("Reckon Distribution User")
        with patch("frappe.get_roles", return_value=["Reckon Distribution User"]):
            self.assertTrue(
                frappe.has_permission(
                    "DocType", ptype="read", user="field@example.com"
                )
            )

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

    def test_tenant_profile_home_page_is_distribution_workspace(self):
        from reckon_distribution.desk_guard import get_user_home_page

        for role in ("Company Admin", "Company Manager", "DSR", "SR"):
            with self.subTest(role=role), patch("frappe.get_roles", return_value=[role]):
                self.assertEqual(get_user_home_page("field@example.com"), "desk/distribution")

    def test_root_and_desk_requests_redirect_tenant_profiles_to_distribution(self):
        from werkzeug.wrappers import Response

        from reckon_distribution.desk_guard import (
            redirect_distribution_desk_response,
            restrict_distribution_desk_request,
        )

        for path in ("/", "/desk/"):
            with self.subTest(path=path), patch(
                "reckon_distribution.desk_guard._ensure_current_distribution_role"
            ), patch(
                "reckon_distribution.desk_guard._ensure_current_user_metadata_access"
            ), patch(
                "reckon_distribution.desk_guard._is_distribution_only_user", return_value=True
            ), patch(
                "reckon_distribution.warehouse.ensure_current_user_company_permission"
            ), patch("reckon_distribution.desk_guard._request_path", return_value=path):
                frappe.flags.pop("distribution_redirect", None)
                restrict_distribution_desk_request()
                self.assertEqual(frappe.flags.distribution_redirect, "/desk/distribution")
                response = Response("desk")
                redirect_distribution_desk_response(response, frappe._dict(path=path))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/desk/distribution")
                self.assertEqual(response.get_data(), b"")
                frappe.flags.pop("distribution_redirect", None)

    def test_system_manager_home_page_is_native(self):
        from reckon_distribution.desk_guard import get_user_home_page

        with patch("frappe.get_roles", return_value=["System Manager"]):
            self.assertIsNone(get_user_home_page("admin@example.com"))

    def test_distribution_tenant_with_system_manager_enters_distribution_workspace(self):
        from reckon_distribution.desk_guard import get_user_home_page

        with patch(
            "frappe.get_roles", return_value=["System Manager", "Reckon Distribution Admin"]
        ):
            self.assertEqual(get_user_home_page("admin@example.com"), "desk/distribution")

    def test_assignment_profile_redirects_before_role_sync(self):
        from reckon_distribution.desk_guard import get_user_home_page

        with patch("frappe.get_roles", return_value=[]), patch(
            "reckon_distribution.desk_guard.frappe.db.exists", return_value=True
        ), patch("reckon_distribution.desk_guard.frappe.db.get_value", return_value="DSR"):
            self.assertEqual(get_user_home_page("field@example.com"), "desk/distribution")

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
            "dsr_challan",
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
