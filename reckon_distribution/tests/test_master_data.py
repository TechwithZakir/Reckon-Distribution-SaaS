from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.master_data import (
    COMPANY_OWNED_MASTER_TYPES,
    get_company_owned_master_registry,
    get_shared_master_query,
    has_shared_master_permission,
    normalize_item_code,
    search_company_master,
    validate_master_scope,
)
from reckon_distribution.seed import run_distribution_seed
from reckon_distribution.tenant_security import validate_tenant_owned_doc


class TestDistributionMasterData(FrappeTestCase):
    def test_company_owned_master_registry_is_explicit(self):
        self.assertEqual(
            set(get_company_owned_master_registry()),
            set(COMPANY_OWNED_MASTER_TYPES),
        )
        self.assertEqual(
            {spec["company_field"] for spec in get_company_owned_master_registry().values()},
            {"rd_company"},
        )

    def test_new_shared_master_uses_frappe_ptype_hook_argument(self):
        item = frappe._dict({"doctype": "Item", "name": "new-item-test"})
        item.is_new = lambda: True
        with patch("reckon_distribution.master_data.user_can_bypass_tenant", return_value=False), patch(
            "reckon_distribution.master_data.require_tenant", return_value=frappe._dict(company=self.company_a)
        ):
            self.assertTrue(has_shared_master_permission(item, user=self.user_a, ptype="create"))

    def test_tenant_item_code_follows_item_name(self):
        item = frappe._dict({"doctype": "Item", "item_name": "Rupchada Tel", "item_code": "OLD-CODE"})
        with patch("reckon_distribution.master_data.user_can_bypass_tenant", return_value=False), patch(
            "reckon_distribution.master_data.frappe.db.has_column", return_value=False
        ):
            normalize_item_code(item)
        self.assertEqual(item.item_code, "Rupchada Tel")

    def test_native_master_query_uses_company_owner_field(self):
        with patch("reckon_distribution.master_data.user_can_bypass_tenant", return_value=False), patch(
            "reckon_distribution.master_data.require_tenant",
            return_value=frappe._dict(company=self.company_a),
        ), patch("reckon_distribution.master_data.frappe.db.has_column", return_value=True):
            condition = get_shared_master_query(user=self.user_a, doctype="Item")
        self.assertIn("rd_company", condition)
        self.assertIn(frappe.db.escape(self.company_a), condition)

    def setUp(self):
        self.user_a = "master-data-a@example.com"
        self.user_b = "master-data-b@example.com"
        self.company_a = "_Test Tenant Company A"
        self.company_b = "_Test Tenant Company B"
        self.route_a = "_Test Master Route A"
        self.route_b = "_Test Master Route B"
        self._cleanup()
        self._ensure_companies()
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

    def _ensure_companies(self):
        for company, abbr in [(self.company_a, "TCA"), (self.company_b, "TCB")]:
            if frappe.db.exists("Company", company):
                continue
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": company,
                    "abbr": abbr,
                    "default_currency": "BDT",
                    "country": "Bangladesh",
                }
            ).insert(ignore_permissions=True)

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

    def test_settings_cannot_use_another_company_uom_profile(self):
        run_distribution_seed(self.company_b, "test-1")
        settings = frappe.get_doc(
            {
                "doctype": "Distribution Settings",
                "company": self.company_a,
                "supplier_goods_policy": "Supplier Provided Goods Only",
                "default_uom_profile": self.company_b,
            }
        )

        with self.assertRaises(frappe.ValidationError):
            settings.validate()

    def test_settings_accepts_company_warehouse_without_master_scope(self):
        warehouse = frappe.db.get_value("Warehouse", {"company": self.company_a}, "name")
        if not warehouse:
            self.skipTest("Test site has no warehouse for the tenant company")
        settings = frappe.get_doc(
            {
                "doctype": "Distribution Settings",
                "company": self.company_a,
                "supplier_goods_policy": "Supplier Provided Goods Only",
                "default_warehouse": warehouse,
            }
        )
        settings.validate()

    def test_native_company_masters_do_not_require_distribution_scope_rows(self):
        with patch(
            "reckon_distribution.master_data.require_tenant",
            return_value=frappe._dict(company=self.company_a),
        ), patch("reckon_distribution.master_data.frappe.db.exists", return_value=True), patch(
            "reckon_distribution.master_data.frappe.db.get_value", return_value=self.company_a
        ):
            validate_master_scope(self.company_a, "Warehouse", "Stores - TCA", user=self.user_a)
            validate_master_scope(self.company_a, "Account", "Cash - TCA", user=self.user_a)

    def test_native_company_master_cannot_cross_company_boundaries(self):
        with patch(
            "reckon_distribution.master_data.require_tenant",
            return_value=frappe._dict(company=self.company_a),
        ), patch("reckon_distribution.master_data.frappe.db.exists", return_value=True), patch(
            "reckon_distribution.master_data.frappe.db.get_value", return_value=self.company_b
        ):
            with self.assertRaises(frappe.ValidationError):
                validate_master_scope(self.company_a, "Warehouse", "Stores - TCB", user=self.user_a)

    def test_route_is_immutable_and_company_scoped(self):
        route_a = self._route(self.route_a, self.company_a)
        self._route(self.route_b, self.company_b)

        with self.assertRaises(frappe.ValidationError):
            route_a.company = self.company_b
            validate_tenant_owned_doc(route_a, user=self.user_a)

    def test_master_scope_lookup_requires_explicit_company_scope(self):
        self._scope(self.company_a)
        self._scope(self.company_b)

        rows_a = search_company_master("Item Group", user=self.user_a)
        rows_b = search_company_master("Item Group", user=self.user_b)
        self.assertEqual({row.company for row in rows_a}, {self.company_a})
        self.assertEqual({row.company for row in rows_b}, {self.company_b})

        with self.assertRaises(frappe.ValidationError):
            self._scope(self.company_a)

        validate_master_scope(self.company_a, "Item Group", "All Item Groups", user=self.user_a)

    def test_native_masters_are_not_shared_by_scope_rows(self):
        with patch("reckon_distribution.master_data.require_tenant", return_value=frappe._dict(company=self.company_a)), patch(
            "reckon_distribution.master_data.frappe.db.has_column", return_value=True
        ), patch(
            "reckon_distribution.master_data.frappe.get_all",
            return_value=[frappe._dict(master_name="ITEM-A")],
        ):
            rows = search_company_master("Item", user=self.user_a)
        self.assertEqual(rows[0].company, self.company_a)
        self.assertEqual(rows[0].master_type, "Item")

    def _scope(self, company: str):
        return self._scope_for(company, "Item Group", "All Item Groups")

    def _scope_for(self, company: str, master_type: str, master_name: str):
        return frappe.get_doc(
            {
                "doctype": "Distribution Master Scope",
                "company": company,
                "master_type": master_type,
                "master_name": master_name,
                "access_scope": "Read",
                "active": 1,
            }
        ).insert(ignore_permissions=True)
