from __future__ import annotations

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

    def test_roles_exist_with_distribution_home_page(self):
        for role in OPERATIONAL_ROLES:
            self.assertTrue(frappe.db.exists("Role", role.name), role.name)
            self.assertEqual(frappe.db.get_value("Role", role.name, "home_page"), "app/distribution")

    def test_workspace_exists_and_is_role_scoped(self):
        self.assertTrue(frappe.db.exists("Workspace", DISTRIBUTION_WORKSPACE))
        workspace = frappe.get_doc("Workspace", DISTRIBUTION_WORKSPACE)
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

    def test_role_home_page_hook_routes_operational_users_to_distribution(self):
        self.assertEqual(hooks.role_home_page["Reckon Distribution User"], "app/distribution")
        self.assertEqual(hooks.role_home_page["Reckon Distribution Manager"], "app/distribution")
        self.assertEqual(hooks.role_home_page["Reckon Distribution Admin"], "app/distribution")

    def test_no_desk_page_conflicts_with_distribution_workspace_route(self):
        page_path = (
            Path(__file__).parents[1]
            / "distribution"
            / "page"
            / "distribution"
            / "distribution.json"
        )

        self.assertFalse(page_path.exists())


class TestCompatibilityHelpers(unittest.TestCase):
    def test_major_version_parser(self):
        self.assertEqual(_major("15.65.2"), 15)
        self.assertEqual(_major("16.0.0-dev"), 16)
        self.assertEqual(_major("bad-version"), 0)

    def test_version_properties_are_explicit(self):
        self.assertTrue(FrappeVersion(15, "15.0.0").supports_v15)
        self.assertTrue(FrappeVersion(16, "16.0.0").supports_v16)
        self.assertFalse(FrappeVersion(17, "17.0.0").supports_v15)
