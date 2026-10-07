from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.master_data import search_company_master, validate_master_scope
from reckon_distribution.seed import run_distribution_seed
from reckon_distribution.tenant_security import CrossCompanyAccessError, validate_tenant_owned_doc


class TestDistributionMasterData(FrappeTestCase):
    def setUp(self):
        self.user_a = "master-data-a@example.com"
        self.user_b = "master-data-b@example.com"
        self.company_a = "_Test Tenant Company A"
        self.company_b = "_Test Tenant Company B"
        self.route_a = "_Test Master Route A"
        self.route_b = "_Test Master Route B"
        self._cleanup()
        self._assignment(self.user_a, self.company_a)
        self._assignment(self.user_b, self.company_b)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for name in [self.route_a, self.route_b]:
            if frappe.db.exists("Distribution Route", name):
                frappe.delete_doc("Distribution Route", name, ignore_permissions=True, force=True)
        for name in frappe.get_all(
            "Distribution Master Scope",
            filters={"company": ["in", [self.company_a, self.company_b]]},
            pluck="name",
        ):
            frappe.delete_doc("Distribution Master Scope", name, ignore_permissions=True, force=True)
        for company in [self.company_a, self.company_b]:
            for doctype in ["Distribution Settings", "Company UOM Profile"]:
                if frappe.db.exists(doctype, company):
                    frappe.delete_doc(doctype, company, ignore_permissions=True, force=True)
        for user in [self.user_a, self.user_b]:
            for name in frappe.get_all("Tenant User Assignment", filters={"user": user}, pluck="name"):
                frappe.delete_doc("Tenant User Assignment", name, ignore_permissions=True, force=True)

    def _assignment(self, user: str, company: str):
        frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": user,
                "company": company,
                "role_profile": "Master Data Manager",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def _route(self, name: str, company: str):
        return frappe.get_doc(
            {
                "doctype": "Distribution Route",
                "name": name,
                "company": company,
                "route_code": name[-1],
                "route_name": name,
                "active": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def test_seed_creates_generic_defaults_once_and_preserves_tenant_records(self):
        first = run_distribution_seed(self.company_a, "test-1")
        second = run_distribution_seed(self.company_a, "test-2")

        self.assertEqual(first["status"], "complete")
        self.assertEqual(second["created"], [])
        self.assertEqual(
            frappe.db.get_value("Distribution Settings", self.company_a, "supplier_goods_policy"),
            "Supplier Provided Goods Only",
        )

    def test_route_is_immutable_and_company_scoped(self):
        route_a = self._route(self.route_a, self.company_a)
        self._route(self.route_b, self.company_b)

        with self.assertRaises(CrossCompanyAccessError):
            route_a.company = self.company_b
            validate_tenant_owned_doc(route_a, user=self.user_a)

    def test_master_scope_lookup_requires_explicit_company_scope(self):
        frappe.get_doc(
            {
                "doctype": "Distribution Master Scope",
                "company": self.company_a,
                "master_type": "Item Group",
                "master_name": "All Item Groups",
                "access_scope": "Read",
                "active": 1,
            }
        ).insert(ignore_permissions=True)

        rows = search_company_master("Item Group", user=self.user_a)
        self.assertEqual({row.master_name for row in rows}, {"All Item Groups"})
        with self.assertRaises(frappe.PermissionError):
            validate_master_scope(self.company_b, "Item Group", "All Item Groups", user=self.user_b)
