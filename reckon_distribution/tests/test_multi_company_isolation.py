"""End-to-end tenant isolation tests for a Frappe/ERPNext test site.

These tests deliberately use two companies and exercise both supported user
creation paths.  They are intended for ``bench run-tests``; the repository's
standalone unit tests do not provide a Frappe database.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.company_context import bind_form_company
from reckon_distribution.master_data import (
    get_shared_master_query,
    has_shared_master_permission,
    normalize_item_code,
    search_company_master,
    validate_shared_master_change,
)
from reckon_distribution.saas import create_registration
from reckon_distribution.team_access import create_team_access
from reckon_distribution.tenant_security import CrossCompanyAccessError
from reckon_distribution.warehouse import sync_user_company_permission


class TestMultiCompanyIsolation(FrappeTestCase):
    """Verify company assignment, master ownership, and cross-company denial."""

    def setUp(self):
        super().setUp()
        token = frappe.generate_hash(length=8).lower()
        self.company_a = f"_RD Isolation A {token}"
        self.company_b = f"_RD Isolation B {token}"
        self.user_a = f"rd-isolation-a-{token}@example.com"
        self.user_b = f"rd-isolation-b-{token}@example.com"
        self.team_user = f"rd-isolation-team-{token}@example.com"
        self.master_names: list[tuple[str, str]] = []
        self.assignment_names: list[str] = []
        self.permission_names: list[str] = []
        self.created_warehouse_types: list[str] = []
        self.created_reference_masters: list[tuple[str, str]] = []
        self.user_names = [self.user_a, self.user_b, self.team_user]
        self._ensure_warehouse_type("Transit")
        self.item_group = self._ensure_reference_master(
            "Item Group", "All Item Groups", {"item_group_name": "All Item Groups", "is_group": 1}
        )
        self.stock_uom = self._ensure_reference_master("UOM", "Nos", {"uom_name": "Nos"})
        self.customer_group = self._ensure_reference_master(
            "Customer Group", "All Customer Groups", {"customer_group_name": "All Customer Groups", "is_group": 1}
        )
        self.supplier_group = self._ensure_reference_master(
            "Supplier Group", "All Supplier Groups", {"supplier_group_name": "All Supplier Groups", "is_group": 1}
        )
        self.territory = self._ensure_reference_master(
            "Territory", "All Territories", {"territory_name": "All Territories", "is_group": 1}
        )
        self._ensure_company(self.company_a, f"RDA{token[:3].upper()}")
        self._ensure_company(self.company_b, f"RDB{token[:3].upper()}")
        self._ensure_user(self.user_a, "Isolation A")
        self._ensure_user(self.user_b, "Isolation B")
        self._assign(self.user_a, self.company_a, "Company Admin")
        self._assign(self.user_b, self.company_b, "Master Data Manager")

    def tearDown(self):
        frappe.set_user("Administrator")
        permission_names = set(self.permission_names)
        permission_names.update(
            frappe.get_all("User Permission", filters={"user": ["in", self.user_names]}, pluck="name")
        )
        for name in permission_names:
            self._delete("User Permission", name)
        assignment_names = set(self.assignment_names)
        assignment_names.update(
            frappe.get_all("Tenant User Assignment", filters={"user": ["in", self.user_names]}, pluck="name")
        )
        for name in assignment_names:
            self._delete("Tenant User Assignment", name)
        for user in self.user_names:
            self._delete("User", user)
        for doctype, name in reversed(self.master_names):
            self._delete(doctype, name)
        for company in (self.company_a, self.company_b):
            self._delete("Company", company)
        for warehouse_type in self.created_warehouse_types:
            self._delete("Warehouse Type", warehouse_type)
        for doctype, name in self.created_reference_masters:
            self._delete(doctype, name)
        super().tearDown()

    def test_saas_onboarding_creates_one_company_permission(self):
        plan = f"_RD Isolation Plan {frappe.generate_hash(length=8)}"
        company = f"_RD SaaS Isolation {frappe.generate_hash(length=8)}"
        email = f"rd-saas-{frappe.generate_hash(length=8)}@example.com"
        plan_doc = frappe.get_doc(
            {
                "doctype": "SaaS Plan",
                "plan_name": plan,
                "plan_version": "test",
                "enabled": 1,
                "currency": "BDT",
                "price": 1,
                "billing_cycle": "Monthly",
            }
        ).insert(ignore_permissions=True)
        try:
            registration = create_registration(
                business_name=company,
                owner_email=email,
                owner_name="SaaS Isolation Admin",
                plan=plan,
            )
            permissions = frappe.get_all(
                "User Permission",
                filters={"user": email, "allow": "Company"},
                fields=["for_value", "apply_to_all_doctypes", "is_default"],
            )
            self.assertEqual(registration.company, company)
            self.assertEqual(len(permissions), 1)
            self.assertEqual(permissions[0].for_value, company)
            self.assertTrue(permissions[0].apply_to_all_doctypes)
            self.assertTrue(permissions[0].is_default)
        finally:
            for doctype in [
                "SaaS Payment",
                "SaaS Subscription",
                "SaaS Registration",
                "Tenant Provisioning Job",
                "Tenant User Assignment",
            ]:
                for name in frappe.get_all(doctype, pluck="name"):
                    doc = frappe.get_doc(doctype, name)
                    if getattr(doc, "company", None) == company or getattr(doc, "user", None) == email:
                        self._delete(doctype, name)
            for name in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
                self._delete("User Permission", name)
            self._delete("User", email)
            self._delete("Company", company)
            self._delete("SaaS Plan", plan_doc.name)

    def test_company_team_access_creates_user_assignment_and_permission(self):
        with self._as_user(self.user_a):
            assignment = create_team_access(
                {
                    "company": self.company_a,
                    "full_name": "Isolation Team User",
                    "email": self.team_user,
                    "password": "Isolation-Password-123!",
                    "password_confirm": "Isolation-Password-123!",
                    "role_profile": "DSR",
                }
            )

        permission = frappe.db.get_value(
            "User Permission",
            {"user": self.team_user, "allow": "Company"},
            ["for_value", "apply_to_all_doctypes", "is_default"],
            as_dict=True,
        )
        self.assertTrue(frappe.db.exists("Tenant User Assignment", assignment))
        self.assertEqual(permission.for_value, self.company_a)
        self.assertTrue(permission.apply_to_all_doctypes)
        self.assertTrue(permission.is_default)

    def test_company_a_lists_only_its_native_masters(self):
        records = self._create_native_masters()
        for doctype in ("Item", "Customer", "Supplier", "Price List", "Item Price"):
            with self._as_user(self.user_a):
                rows = search_company_master(doctype, user=self.user_a)
                condition = get_shared_master_query(user=self.user_a, doctype=doctype)
            own_name = records[(doctype, "a")]
            other_name = records[(doctype, "b")]
            visible = {row.master_name for row in rows}
            self.assertIn(own_name, visible, f"{doctype} is not visible to its owner")
            self.assertNotIn(other_name, visible, f"{doctype} crossed the company boundary")
            self.assertIn(self.company_a, condition)
            self.assertNotIn(self.company_b, condition)

    def test_cross_company_open_edit_and_link_are_denied(self):
        records = self._create_native_masters()
        for doctype in ("Item", "Customer", "Supplier", "Price List"):
            other = frappe.get_doc(doctype, records[(doctype, "b")])
            with self._as_user(self.user_a):
                self.assertFalse(
                    frappe.has_permission(doctype, ptype="read", doc=other, user=self.user_a)
                )
                self.assertFalse(
                    frappe.has_permission(doctype, ptype="delete", doc=other, user=self.user_a)
                )
                self.assertFalse(
                    has_shared_master_permission(other, user=self.user_a, ptype="write"),
                    f"{doctype} write permission crossed the boundary",
                )
                with self.assertRaises((frappe.PermissionError, CrossCompanyAccessError)):
                    validate_shared_master_change(other)

        item_price = frappe.get_doc("Item Price", records[("Item Price", "b")])
        with self._as_user(self.user_a):
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
                validate_shared_master_change(item_price)

    def test_new_forms_bind_company_and_item_code_is_name_based(self):
        with self._as_user(self.user_a):
            customer = frappe.new_doc("Customer")
            customer.customer_name = "New Retailer"
            bind_form_company(customer)
            self.assertEqual(customer.rd_company, self.company_a)

            item = frappe.new_doc("Item")
            item.item_name = f"Same Name {frappe.generate_hash(length=6)}"
            normalize_item_code(item)
            self.assertEqual(item.item_code, item.item_name)

    def test_assignment_change_removes_old_permission_and_materializes_new_one(self):
        assignment = frappe.db.get_value(
            "Tenant User Assignment", {"user": self.user_a, "active": 1}, "name"
        )
        doc = frappe.get_doc("Tenant User Assignment", assignment)
        doc.active = 0
        doc.save(ignore_permissions=True)
        replacement = frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": self.user_a,
                "company": self.company_b,
                "role_profile": "Company Admin",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        self.assignment_names.append(replacement.name)
        sync_user_company_permission(self.user_a, expected_company=self.company_b)

        permissions = frappe.get_all(
            "User Permission",
            filters={"user": self.user_a, "allow": "Company"},
            pluck="for_value",
        )
        self.assertEqual(permissions, [self.company_b])

    def test_two_active_company_assignments_are_rejected(self):
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": "Tenant User Assignment",
                    "user": self.user_a,
                    "company": self.company_b,
                    "role_profile": "Company Admin",
                    "active": 1,
                    "is_default": 0,
                }
            ).insert(ignore_permissions=True, ignore_links=True)

    def _create_native_masters(self) -> dict[tuple[str, str], str]:
        token = frappe.generate_hash(length=8)
        values = {}
        for key, company in (("a", self.company_a), ("b", self.company_b)):
            item = frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": f"RD-{token}-{key}",
                    "item_name": f"Isolation Item {token} {key}",
                    "item_group": self.item_group,
                    "stock_uom": self.stock_uom,
                    "is_stock_item": 0,
                    "is_sales_item": 1,
                    "is_purchase_item": 1,
                    "rd_company": company,
                }
            ).insert(ignore_permissions=True)
            values[("Item", key)] = item.name
            customer = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": f"Isolation Retailer {token} {key}",
                    "customer_group": self.customer_group,
                    "territory": self.territory,
                    "customer_type": "Company",
                    "rd_company": company,
                }
            ).insert(ignore_permissions=True)
            values[("Customer", key)] = customer.name
            supplier = frappe.get_doc(
                {
                    "doctype": "Supplier",
                    "supplier_name": f"Isolation Supplier {token} {key}",
                    "supplier_group": self.supplier_group,
                    "supplier_type": "Company",
                    "rd_company": company,
                }
            ).insert(ignore_permissions=True)
            values[("Supplier", key)] = supplier.name
            price_list = frappe.get_doc(
                {
                    "doctype": "Price List",
                    "price_list_name": f"Isolation Price {token} {key}",
                    "buying": 0,
                    "selling": 1,
                    "enabled": 1,
                    "currency": "BDT",
                    "rd_company": company,
                }
            ).insert(ignore_permissions=True)
            values[("Price List", key)] = price_list.name
            item_price = frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": item.name,
                    "price_list": price_list.name,
                    "price_list_rate": 100,
                    "selling": 1,
                    "currency": "BDT",
                    "rd_company": company,
                }
            ).insert(ignore_permissions=True)
            values[("Item Price", key)] = item_price.name
            self.master_names.extend(
                [(doctype, values[(doctype, key)]) for doctype in ("Item", "Customer", "Supplier", "Price List", "Item Price")]
            )
        return values

    def _ensure_company(self, name: str, abbr: str) -> None:
        if not frappe.db.exists("Company", name):
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": name,
                    "abbr": abbr,
                    "default_currency": "BDT",
                    "country": "Bangladesh",
                }
            ).insert(ignore_permissions=True)

    def _ensure_warehouse_type(self, name: str) -> None:
        if frappe.db.exists("Warehouse Type", name):
            return
        frappe.get_doc({"doctype": "Warehouse Type", "name": name}).insert(
            ignore_permissions=True
        )
        self.created_warehouse_types.append(name)

    def _ensure_reference_master(self, doctype: str, preferred: str, values: dict) -> str:
        existing = frappe.get_all(doctype, pluck="name", limit=1)
        if existing:
            return existing[0]
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
        self.created_reference_masters.append((doctype, doc.name))
        return doc.name

    def _ensure_user(self, email: str, full_name: str) -> None:
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": full_name,
                    "user_type": "System User",
                    "send_welcome_email": 0,
                    "enabled": 1,
                }
            ).insert(ignore_permissions=True)

    def _assign(self, user: str, company: str, role_profile: str) -> None:
        role = {
            "Company Admin": "Reckon Distribution Admin",
            "Master Data Manager": "Reckon Master Data Manager",
        }[role_profile]
        frappe.get_doc("User", user).add_roles(role)
        doc = frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": user,
                "company": company,
                "role_profile": role_profile,
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        self.assignment_names.append(doc.name)
        permission = frappe.db.get_value(
            "User Permission", {"user": user, "allow": "Company", "for_value": company}, "name"
        )
        if permission:
            self.permission_names.append(permission)

    @contextmanager
    def _as_user(self, user: str):
        previous = frappe.session.user
        frappe.set_user(user)
        try:
            yield
        finally:
            frappe.set_user(previous)

    @staticmethod
    def _delete(doctype: str, name: str | None) -> None:
        if name and frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)


if __name__ == "__main__":
    import unittest

    unittest.main()
