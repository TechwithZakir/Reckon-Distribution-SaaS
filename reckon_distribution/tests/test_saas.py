from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from reckon_distribution.saas import (
    SubscriptionGateError,
    assert_operational_access,
    create_registration,
    ensure_tenant_seed_job,
    run_tenant_seed_job,
    verify_payment,
)
from reckon_distribution.saas_security import (
    get_vendor_only_query,
    has_vendor_only_permission,
)


class TestSaaSRegistrationAndGate(FrappeTestCase):
    def setUp(self):
        self.plan = "_Test Distribution Plan"
        self.company = "_Test SaaS Tenant"
        self.email = "tenant-admin@example.com"
        self._cleanup()
        frappe.get_doc(
            {
                "doctype": "SaaS Plan",
                "plan_name": self.plan,
                "plan_version": "v1",
                "enabled": 1,
                "currency": "BDT",
                "price": 1200,
                "billing_cycle": "Monthly",
                "trial_days": 0,
                "grace_days": 3,
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
                if (
                    name == self.plan
                    or name.startswith(("PAY-", "SUB-", "REG-", "TPJ-", "TUA-"))
                ):
                    doc = frappe.get_doc(doctype, name)
                    if getattr(doc, "company", None) in {self.company, None} or getattr(
                        doc, "user", None
                    ) == self.email:
                        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

        if frappe.db.exists("User", self.email):
            frappe.delete_doc("User", self.email, ignore_permissions=True, force=True)
        if frappe.db.exists("Company", self.company):
            frappe.delete_doc("Company", self.company, ignore_permissions=True, force=True)

    def _registration(self):
        return create_registration(
            business_name=self.company,
            owner_email=self.email,
            owner_name="Tenant Admin",
            plan=self.plan,
        )

    def test_public_signup_creates_pending_company_admin_subscription_payment_and_seed_job(self):
        registration = self._registration()

        self.assertEqual(registration.company, self.company)
        self.assertTrue(frappe.db.exists("Company", self.company))
        self.assertTrue(frappe.db.exists("User", self.email))
        self.assertTrue(frappe.db.exists("SaaS Subscription", registration.subscription))
        self.assertTrue(frappe.db.exists("SaaS Payment", registration.payment))
        self.assertTrue(frappe.db.exists("Tenant Provisioning Job", registration.provisioning_job))
        self.assertTrue(
            frappe.db.exists(
                "Tenant User Assignment",
                {"user": self.email, "company": self.company, "active": 1},
            )
        )
        permission = frappe.db.get_value(
            "User Permission",
            {"user": self.email, "allow": "Company", "for_value": self.company},
            ["apply_to_all_doctypes", "is_default"],
            as_dict=True,
        )
        self.assertTrue(permission)
        self.assertTrue(permission.apply_to_all_doctypes)
        self.assertTrue(permission.is_default)

    def test_opening_distribution_repairs_missing_company_permission(self):
        self._registration()
        from reckon_distribution.warehouse import ensure_current_user_company_permission

        for name in frappe.get_all(
            "User Permission", filters={"user": self.email, "allow": "Company"}, pluck="name"
        ):
            frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)

        ensure_current_user_company_permission(self.email)
        self.assertTrue(
            frappe.db.exists(
                "User Permission",
                {"user": self.email, "allow": "Company", "for_value": self.company},
            )
        )

    def test_seed_job_is_idempotent_once_per_company_and_version(self):
        frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": self.company,
                "abbr": "TST",
                "default_currency": "BDT",
                "country": "Bangladesh",
            }
        ).insert(ignore_permissions=True)
        first = ensure_tenant_seed_job(self.company)
        second = ensure_tenant_seed_job(self.company)

        self.assertEqual(first.name, second.name)

    def test_operational_gate_blocks_pending_subscription_even_after_seed(self):
        registration = self._registration()
        run_tenant_seed_job(self.company)

        with self.assertRaises(SubscriptionGateError):
            assert_operational_access(registration.company)

    def test_verified_payment_and_completed_seed_allow_access(self):
        registration = self._registration()
        run_tenant_seed_job(self.company)
        verify_payment(registration.payment, reference="manual-confirmed")

        assert_operational_access(self.company)

    def test_due_expired_and_suspended_are_blocked(self):
        registration = self._registration()
        run_tenant_seed_job(self.company)
        subscription = verify_payment(registration.payment)

        for status in ["Due", "Expired", "Suspended"]:
            subscription.status = status
            subscription.save(ignore_permissions=True)
            with self.assertRaises(SubscriptionGateError):
                assert_operational_access(self.company)

    def test_grace_allows_until_grace_date(self):
        registration = self._registration()
        run_tenant_seed_job(self.company)
        subscription = verify_payment(registration.payment)
        subscription.status = "Grace"
        subscription.grace_until = add_days(nowdate(), 1)
        subscription.save(ignore_permissions=True)

        assert_operational_access(self.company)

    def test_subscription_preserves_plan_price_and_version(self):
        registration = self._registration()
        subscription = frappe.get_doc("SaaS Subscription", registration.subscription)
        subscription.price = 999

        with self.assertRaises(frappe.ValidationError):
            subscription.save(ignore_permissions=True)

    def test_vendor_only_records_hidden_from_non_vendor_query(self):
        self.assertEqual(get_vendor_only_query(user=self.email), "1 = 0")

    def test_vendor_only_permission_denies_tenant_user(self):
        plan = frappe.get_doc("SaaS Plan", self.plan)

        self.assertFalse(has_vendor_only_permission(plan, user=self.email))
