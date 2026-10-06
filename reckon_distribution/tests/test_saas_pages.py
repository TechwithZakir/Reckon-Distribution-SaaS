from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.saas import (
    get_user_home_page,
    retry_tenant_seed_job,
    verify_payment_manual,
)
from reckon_distribution.saas_security import has_vendor_only_permission
from reckon_distribution.www import reckonerp_signup


class TestSaaSPagesAndActions(FrappeTestCase):
    def setUp(self):
        self.plan = "_Test Page Plan"
        self.company = "_Test Page Tenant"
        self.email = "page-tenant@example.com"
        self._cleanup()
        frappe.get_doc(
            {
                "doctype": "SaaS Plan",
                "plan_name": self.plan,
                "plan_version": "v1",
                "enabled": 1,
                "currency": "BDT",
                "price": 1000,
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for doctype in [
            "SaaS Payment",
            "SaaS Subscription",
            "SaaS Registration",
            "Tenant Provisioning Job",
            "Tenant User Assignment",
            "SaaS Plan",
        ]:
            for name in frappe.get_all(doctype, pluck="name"):
                if name == self.plan or name.startswith(("PAY-", "SUB-", "REG-", "TPJ-", "TUA-")):
                    doc = frappe.get_doc(doctype, name)
                    if getattr(doc, "company", None) in {self.company, None} or getattr(
                        doc, "user", None
                    ) == self.email:
                        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        if frappe.db.exists("User", self.email):
            frappe.delete_doc("User", self.email, ignore_permissions=True, force=True)
        if frappe.db.exists("Company", self.company):
            frappe.delete_doc("Company", self.company, ignore_permissions=True, force=True)

    def test_signup_page_lists_enabled_plans(self):
        context = frappe._dict()

        reckonerp_signup.get_context(context)

        self.assertEqual(context.title, "Reckon ERP Signup")
        self.assertIn(self.plan, {plan.name for plan in context.plans})

    def test_unpaid_tenant_home_page_is_subscription_page(self):
        from reckon_distribution.saas import create_registration

        create_registration(
            business_name=self.company,
            owner_email=self.email,
            owner_name="Page Tenant",
            plan=self.plan,
        )

        self.assertEqual(get_user_home_page(self.email), "reckonerp-subscription")

    def test_vendor_home_page_is_saas_admin(self):
        with patch("frappe.get_roles", return_value=["Reckon Vendor Superuser"]):
            self.assertEqual(get_user_home_page("vendor@example.com"), "reckon-saas-admin")

    def test_manual_payment_verify_requires_vendor(self):
        with patch("reckon_distribution.saas.is_vendor_user", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                verify_payment_manual("PAY-00001")

    def test_seed_retry_requires_vendor(self):
        with patch("reckon_distribution.saas.is_vendor_user", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                retry_tenant_seed_job(self.company)

    def test_vendor_only_permission_allows_vendor(self):
        plan = frappe.get_doc("SaaS Plan", self.plan)

        with patch("frappe.get_roles", return_value=["Reckon Vendor Superuser"]):
            self.assertTrue(has_vendor_only_permission(plan, user="vendor@example.com"))
