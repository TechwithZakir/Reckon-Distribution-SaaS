"""Bench integration tests for the P0 go-live blockers.

Covers: signup cannot attach a guest to an existing tenant, the request-level
subscription gate, the read-only Desk guard, platform roles for tenant users,
and the failure handling of the tenant seed job. Run on a dedicated test site
through ``scripts/test_multi_company.sh``.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from reckon_distribution.saas import (
    SignupConflictError,
    SignupValidationError,
    SubscriptionGateError,
    confirm_registration_email,
    create_registration,
    ensure_tenant_seed_job,
    has_operational_access,
    provision_registration,
    public_signup,
    run_tenant_seed_job,
    verify_payment,
)
from reckon_distribution.tenant_security import get_tenant_owned_query, user_can_bypass_tenant

SEED_FAILURE_UOM = "_P0 Seed Rollback UOM"


def failing_seed_handler(company: str, seed_version: str) -> None:
    """Writes a record, then fails, so the test can prove the write is rolled back."""
    if not frappe.db.exists("UOM", SEED_FAILURE_UOM):
        frappe.get_doc({"doctype": "UOM", "uom_name": SEED_FAILURE_UOM}).insert(
            ignore_permissions=True
        )
    raise RuntimeError("seed handler exploded")


SEED_CALLS: list[str] = []


def passing_seed_handler(company: str, seed_version: str) -> None:
    SEED_CALLS.append(company)


def rejecting_captcha(token=None, ip=None) -> bool:
    return False


class P0TestCase(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.token = frappe.generate_hash(length=8).lower()
        self.plan = f"_P0 Plan {self.token}"
        self.companies: list[str] = []
        self.users: list[str] = []
        frappe.get_doc(
            {
                "doctype": "SaaS Plan",
                "plan_name": self.plan,
                "plan_version": "p0",
                "enabled": 1,
                "currency": "BDT",
                "price": 1000,
                "billing_cycle": "Monthly",
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        for flag in ("saas_gate_blocked", "saas_gate_redirect", "distribution_redirect"):
            frappe.flags.pop(flag, None)
        users = set(self.users)
        companies = set(self.companies)
        for name in frappe.get_all(
            "SaaS Registration",
            filters={"plan": self.plan},
            fields=["name", "company", "owner_email"],
        ):
            users.add(name.owner_email)
            if name.company:
                companies.add(name.company)
        for doctype in ("SaaS Payment", "SaaS Subscription", "Tenant Provisioning Job"):
            for name in frappe.get_all(doctype, filters={"company": ["in", list(companies) or [""]]}, pluck="name"):
                self._delete(doctype, name)
        for name in frappe.get_all("SaaS Registration", filters={"plan": self.plan}, pluck="name"):
            self._delete("SaaS Registration", name)
        for name in frappe.get_all(
            "Tenant User Assignment", filters={"user": ["in", list(users) or [""]]}, pluck="name"
        ):
            self._delete("Tenant User Assignment", name)
        for name in frappe.get_all(
            "User Permission", filters={"user": ["in", list(users) or [""]]}, pluck="name"
        ):
            self._delete("User Permission", name)
        for user in users:
            self._delete("User", user)
        for company in companies:
            self._delete("Company", company)
        self._delete("SaaS Plan", self.plan)
        self._delete("UOM", SEED_FAILURE_UOM)
        super().tearDown()

    # helpers -------------------------------------------------------------

    def _email(self, label: str) -> str:
        email = f"p0-{label}-{self.token}@example.com"
        self.users.append(email)
        return email

    def _company_name(self, label: str) -> str:
        company = f"_P0 {label} {self.token}"
        self.companies.append(company)
        return company

    def _signup(self, company: str, email: str):
        return create_registration(
            business_name=company, owner_email=email, owner_name="P0 Owner", plan=self.plan
        )

    def _verify(self, registration):
        with patch("frappe.enqueue") as enqueue:
            confirm_registration_email(registration.flags.verification_token)
        return enqueue

    def _provision(self, registration_name: str):
        with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[]):
            return provision_registration(registration_name)

    def _existing_company(self, company: str) -> None:
        abbr = f"P{frappe.generate_hash(length=4).upper()}"
        with patch("erpnext.setup.doctype.company.company.Company.on_update"):
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": company,
                    "abbr": abbr,
                    "default_currency": "BDT",
                    "country": "Bangladesh",
                }
            ).insert(ignore_permissions=True)

    def _user(self, email: str, roles: list[str] | None = None) -> None:
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "P0",
                "send_welcome_email": 0,
                "enabled": 1,
                "roles": [{"role": role} for role in roles or []],
            }
        ).insert(ignore_permissions=True)

    def _tenant(self, label: str, *, active: bool, seeded: bool = True) -> tuple[str, str]:
        """A tenant user with a company, subscription and seed job, without ERPNext setup."""
        company = self._company_name(label)
        email = self._email(label)
        self._existing_company(company)
        self._user(email, ["Reckon Distribution Admin"])
        frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": email,
                "company": company,
                "role_profile": "Company Admin",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "SaaS Subscription",
                "company": company,
                "company_admin": email,
                "plan": self.plan,
                "plan_version": "p0",
                "status": "Active" if active else "Pending",
                "price": 1000,
                "currency": "BDT",
                "start_date": nowdate(),
                "end_date": add_days(nowdate(), 30),
            }
        ).insert(ignore_permissions=True)
        job = ensure_tenant_seed_job(company)
        if seeded:
            with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[]):
                run_tenant_seed_job(company)
        else:
            self.assertEqual(job.status, "Pending")
        return company, email

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


class TestSignupCannotHijackTenant(P0TestCase):
    def test_signup_records_only_a_pending_registration(self):
        company = self._company_name("Pending")
        email = self._email("pending")

        registration = self._signup(company, email)

        self.assertEqual(registration.status, "Pending Verification")
        self.assertFalse(registration.company)
        self.assertFalse(registration.company_admin)
        self.assertFalse(frappe.db.exists("Company", company))
        self.assertFalse(frappe.db.exists("User", email))
        self.assertFalse(frappe.db.exists("Tenant User Assignment", {"user": email}))
        self.assertTrue(registration.flags.verification_token)
        stored_hash = frappe.db.get_value("SaaS Registration", registration.name, "email_verification_hash")
        self.assertNotEqual(stored_hash, registration.flags.verification_token)

    def test_signup_refuses_existing_company(self):
        company = self._company_name("Victim")
        attacker = self._email("attacker")
        self._existing_company(company)

        with self.assertRaises(SignupConflictError) as raised:
            self._signup(company, attacker)

        self.assertEqual(raised.exception.http_status_code, 409)
        self.assertFalse(frappe.db.exists("User", attacker))
        self.assertFalse(frappe.db.exists("SaaS Registration", {"owner_email": attacker}))
        self.assertFalse(
            frappe.db.exists("Tenant User Assignment", {"user": attacker, "company": company})
        )

    def test_signup_refuses_existing_user(self):
        email = self._email("existing")
        self._user(email)

        with self.assertRaises(SignupConflictError):
            self._signup(self._company_name("New"), email)

        self.assertFalse(frappe.db.exists("Tenant User Assignment", {"user": email}))

    def test_invalid_input_is_a_client_error(self):
        company = self._company_name("Invalid")
        email = self._email("invalid")
        cases = [
            {"business_name": "", "owner_email": email, "plan": self.plan},
            {"business_name": "<script>x</script>", "owner_email": email, "plan": self.plan},
            {"business_name": "x" * 141, "owner_email": email, "plan": self.plan},
            {"business_name": company, "owner_email": "not-an-email", "plan": self.plan},
            {"business_name": company, "owner_email": email, "plan": "No Such Plan"},
            {"business_name": company, "owner_email": email, "plan": self.plan, "billing_cycle": "Daily"},
            {"business_name": ["array"], "owner_email": email, "plan": self.plan},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(SignupValidationError) as raised:
                create_registration(owner_name="P0 Owner", **case)
            self.assertEqual(raised.exception.http_status_code, 400)

    def test_verification_enqueues_provisioning_and_link_is_single_use(self):
        registration = self._signup(self._company_name("Verify"), self._email("verify"))

        enqueue = self._verify(registration)

        enqueue.assert_called_once()
        args, kwargs = enqueue.call_args
        self.assertEqual(args[0], "reckon_saas_platform.saas.provision_registration")
        self.assertEqual(kwargs["registration"], registration.name)
        self.assertTrue(kwargs["deduplicate"])
        self.assertIn(registration.name, kwargs["job_id"])
        registration.reload()
        self.assertEqual(registration.status, "Provisioning")
        self.assertTrue(registration.email_verified)
        self.assertFalse(registration.company)
        with patch("frappe.enqueue"), self.assertRaises(SignupValidationError):
            confirm_registration_email(registration.flags.verification_token)

    def test_expired_verification_link_is_rejected(self):
        registration = self._signup(self._company_name("Expired"), self._email("expired"))
        registration.db_set("verification_sent_on", add_to_date(now_datetime(), hours=-49))

        with patch("frappe.enqueue") as enqueue, self.assertRaises(SignupValidationError):
            confirm_registration_email(registration.flags.verification_token)

        enqueue.assert_not_called()
        self.assertEqual(frappe.db.get_value("SaaS Registration", registration.name, "status"), "Cancelled")

    def test_provisioning_refuses_company_created_after_signup(self):
        company = self._company_name("Race")
        email = self._email("race")
        registration = self._signup(company, email)
        self._verify(registration)
        self._existing_company(company)

        result = self._provision(registration.name)

        self.assertEqual(result.status, "Failed")
        self.assertIn("already registered", result.error)
        self.assertFalse(frappe.db.exists("User", email))
        self.assertFalse(frappe.db.exists("Tenant User Assignment", {"company": company}))

    def test_failed_provisioning_leaves_nothing_and_retry_succeeds(self):
        company = self._company_name("Retry")
        email = self._email("retry")
        registration = self._signup(company, email)
        self._verify(registration)

        with patch(
            "reckon_saas_platform.saas._create_registration_subscription",
            side_effect=RuntimeError("billing down"),
        ):
            failed = self._provision(registration.name)

        self.assertEqual(failed.status, "Failed")
        self.assertIn("billing down", failed.error)
        self.assertFalse(frappe.db.exists("Company", company))
        self.assertFalse(frappe.db.exists("User", email))

        done = self._provision(registration.name)

        self.assertEqual(done.status, "Pending Payment")
        self.assertEqual(done.company, company)
        self.assertEqual(done.company_admin, email)
        self.assertTrue(
            frappe.db.exists("Tenant User Assignment", {"user": email, "company": company, "active": 1})
        )
        self.assertEqual(
            frappe.db.get_value("Tenant Provisioning Job", done.provisioning_job, "status"), "Complete"
        )

    def test_public_signup_is_rate_limited(self):
        cmd = "reckon_saas_platform.saas.public_signup"
        ip = "203.0.113.77"
        registration = SimpleNamespace(name="REG-P0")
        frappe.local.request = SimpleNamespace(method="POST", path=f"/api/method/{cmd}")
        frappe.local.request_ip = ip
        previous_cmd = frappe.local.form_dict.get("cmd")
        frappe.local.form_dict.cmd = cmd
        frappe.cache.delete_value(f"rl:{cmd}:{ip}")
        try:
            with patch.dict(frappe.conf, {"reckon_saas_signup_rate_limit": 2}), patch(
                "reckon_saas_platform.saas.create_registration", return_value=registration
            ), patch("reckon_saas_platform.saas.send_registration_verification"), patch(
                "reckon_saas_platform.saas.verify_signup_captcha"
            ):
                for _attempt in range(2):
                    public_signup("Biz", "a@example.com", "Owner", self.plan)
                with self.assertRaises(frappe.RateLimitExceededError):
                    public_signup("Biz", "a@example.com", "Owner", self.plan)
        finally:
            frappe.cache.delete_value(f"rl:{cmd}:{ip}")
            frappe.local.form_dict.cmd = previous_cmd
            del frappe.local.request
            del frappe.local.request_ip

    def test_captcha_verifier_hook_can_reject_signup(self):
        company = self._company_name("Captcha")
        email = self._email("captcha")
        verifier = "reckon_distribution.tests.test_go_live_blockers.rejecting_captcha"
        with patch("reckon_saas_platform.saas.frappe.get_hooks", return_value=[verifier]):
            with self.assertRaises(SignupValidationError):
                public_signup(company, email, "Owner", self.plan, captcha_token="bad")

        self.assertFalse(frappe.db.exists("SaaS Registration", {"owner_email": email}))

    def test_missing_captcha_verifier_refuses_when_required(self):
        with patch.dict(frappe.conf, {"reckon_saas_require_captcha": 1}), patch(
            "reckon_saas_platform.saas.frappe.get_hooks", return_value=[]
        ), self.assertRaises(SignupValidationError):
            public_signup(self._company_name("NoCaptcha"), self._email("nocaptcha"), "Owner", self.plan)


class TestTenantSeedJob(P0TestCase):
    def test_failure_marks_job_failed_rolls_back_and_retry_completes(self):
        company = self._company_name("Seed")
        self._existing_company(company)
        failing = "reckon_distribution.tests.test_go_live_blockers.failing_seed_handler"
        passing = "reckon_distribution.tests.test_go_live_blockers.passing_seed_handler"

        with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[passing, failing]):
            job = run_tenant_seed_job(company)

        self.assertEqual(job.status, "Failed")
        self.assertIn("seed handler exploded", job.error)
        self.assertEqual(frappe.db.get_value("Tenant Provisioning Job", job.name, "status"), "Failed")
        self.assertFalse(frappe.db.exists("UOM", SEED_FAILURE_UOM))

        with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[passing]):
            retried = run_tenant_seed_job(company)

        self.assertEqual(retried.name, job.name)
        self.assertEqual(retried.status, "Complete")
        self.assertFalse(retried.error)
        self.assertEqual(
            frappe.db.count("Tenant Provisioning Job", {"company": company}), 1
        )

    def test_complete_job_is_not_rerun(self):
        company = self._company_name("SeedDone")
        self._existing_company(company)
        with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[]):
            run_tenant_seed_job(company)

        passing = "reckon_distribution.tests.test_go_live_blockers.passing_seed_handler"
        SEED_CALLS.clear()
        with patch("reckon_saas_platform.saas.get_seed_handlers", return_value=[passing]):
            job = run_tenant_seed_job(company)

        self.assertEqual(job.status, "Complete")
        self.assertEqual(SEED_CALLS, [])


class TestSubscriptionGate(P0TestCase):
    def _enforce(self, path: str, cmd: str | None = None):
        from reckon_saas_platform.saas_gate import enforce_operational_access

        previous_cmd = frappe.local.form_dict.get("cmd")
        frappe.local.form_dict.cmd = cmd
        try:
            with patch("reckon_saas_platform.saas_gate._request_path", return_value=path):
                enforce_operational_access()
        finally:
            frappe.local.form_dict.cmd = previous_cmd

    def test_unpaid_tenant_is_blocked_on_api_and_redirected_on_desk(self):
        _company, email = self._tenant("Unpaid", active=False)

        with self._as_user(email):
            for path in (
                "/api/method/frappe.client.get_list",
                "/api/resource/Sales Invoice",
                "/api/v2/method/frappe.desk.reportview.get",
            ):
                with self.subTest(path=path), self.assertRaises(SubscriptionGateError):
                    self._enforce(path)
            with self.assertRaises(SubscriptionGateError):
                self._enforce("/", cmd="frappe.client.get_list")
            for path in ("/app", "/app/distribution", "/desk/distribution"):
                with self.subTest(path=path):
                    self._enforce(path)
                    self.assertEqual(frappe.flags.saas_gate_redirect, "/reckonerp-subscription")

    def test_gate_redirect_replaces_desk_response(self):
        from reckon_saas_platform.saas_gate import redirect_blocked_response
        from werkzeug.wrappers import Response

        _company, email = self._tenant("Redirect", active=False)
        with self._as_user(email):
            self._enforce("/app/distribution")
        response = Response("desk")
        redirect_blocked_response(response, frappe._dict(path="/app/distribution"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/reckonerp-subscription")
        self.assertEqual(response.get_data(), b"")

    def test_unseeded_tenant_is_blocked_even_when_paid(self):
        _company, email = self._tenant("Unseeded", active=True, seeded=False)

        with self._as_user(email), self.assertRaises(SubscriptionGateError):
            self._enforce("/api/method/frappe.client.get_list")

    def test_exempt_routes_stay_open_for_blocked_tenant(self):
        _company, email = self._tenant("Exempt", active=False)

        with self._as_user(email):
            for path in (
                "/api/method/login",
                "/api/method/logout",
                "/api/method/reckon_saas_platform.saas.get_subscription_summary",
                "/assets/reckon_distribution/css/reckon_distribution.css",
                "/reckonerp-subscription",
                "/login",
            ):
                with self.subTest(path=path):
                    self._enforce(path)
                    self.assertFalse(frappe.flags.saas_gate_redirect)
            self._enforce("/", cmd="web_logout")

    def test_active_tenant_and_platform_users_pass(self):
        _company, email = self._tenant("Active", active=True)

        with self._as_user(email):
            self._enforce("/api/method/frappe.client.get_list")
            self._enforce("/app/distribution")
            self.assertFalse(frappe.flags.saas_gate_redirect)
        self._enforce("/api/method/frappe.client.get_list")  # Administrator
        with self._as_user("Guest"):
            self._enforce("/api/method/frappe.client.get_list")

    def test_cached_access_is_invalidated_when_subscription_or_job_changes(self):
        company, email = self._tenant("Cache", active=False)
        self.assertFalse(has_operational_access(company))

        subscription = frappe.get_doc("SaaS Subscription", {"company": company})
        subscription.status = "Active"
        subscription.save(ignore_permissions=True)
        self.assertTrue(has_operational_access(company))

        job = frappe.get_doc("Tenant Provisioning Job", {"company": company})
        job.status = "Failed"
        job.save(ignore_permissions=True)
        self.assertFalse(has_operational_access(company))

        with self._as_user(email), self.assertRaises(SubscriptionGateError):
            self._enforce("/api/method/frappe.client.get_list")

    def test_verify_payment_opens_the_gate(self):
        company = self._company_name("Pay")
        email = self._email("pay")
        registration = self._signup(company, email)
        self._verify(registration)
        registration = self._provision(registration.name)
        self.assertFalse(has_operational_access(company))

        verify_payment(registration.payment, reference="p0")

        self.assertTrue(has_operational_access(company))

    def test_distribution_home_page_follows_gate(self):
        from reckon_distribution.desk_guard import get_user_home_page

        _blocked_company, blocked = self._tenant("HomeBlocked", active=False)
        _open_company, open_user = self._tenant("HomeOpen", active=True)

        self.assertEqual(get_user_home_page(blocked), "reckonerp-subscription")
        self.assertEqual(get_user_home_page(open_user), "desk/distribution")

    def test_desk_guard_defers_to_gate_redirect(self):
        from werkzeug.wrappers import Response

        from reckon_distribution.desk_guard import (
            redirect_distribution_desk_response,
            restrict_distribution_desk_request,
        )

        _company, email = self._tenant("Defer", active=False)
        with self._as_user(email):
            frappe.flags.pop("distribution_redirect", None)
            self._enforce("/app")
            with patch("reckon_distribution.desk_guard._request_path", return_value="/app"):
                restrict_distribution_desk_request()
        self.assertFalse(frappe.flags.get("distribution_redirect"))
        response = Response("desk")
        response.status_code = 302
        response.headers["Location"] = "/reckonerp-subscription"
        redirect_distribution_desk_response(response, frappe._dict(path="/app"))
        self.assertEqual(response.headers["Location"], "/reckonerp-subscription")


class TestDeskGuardIsReadOnly(P0TestCase):
    def test_request_guard_performs_no_writes_or_cache_clears(self):
        from reckon_distribution.desk_guard import restrict_distribution_desk_request

        _company, email = self._tenant("ReadOnly", active=True)
        writes_before = getattr(frappe.db, "transaction_writes", None)
        with self._as_user(email), patch("frappe.clear_cache") as clear_cache, patch(
            "reckon_distribution.install.ensure_standard_doc_type_read_permission"
        ) as metadata_repair, patch(
            "reckon_distribution.warehouse.sync_user_company_permission"
        ) as permission_repair, patch(
            "frappe.core.doctype.user.user.User.add_roles"
        ) as add_roles:
            for path in ("/app/distribution", "/api/method/frappe.client.get_list", "/desk/home"):
                with patch("reckon_distribution.desk_guard._request_path", return_value=path):
                    frappe.flags.pop("distribution_redirect", None)
                    restrict_distribution_desk_request()

        clear_cache.assert_not_called()
        metadata_repair.assert_not_called()
        permission_repair.assert_not_called()
        add_roles.assert_not_called()
        if writes_before is not None:
            self.assertEqual(frappe.db.transaction_writes, writes_before)

    def test_assignment_update_grants_role_and_doctype_metadata(self):
        company = self._company_name("Access")
        email = self._email("access")
        self._existing_company(company)
        self._user(email)
        self.assertNotIn("Reckon Distribution User", frappe.get_roles(email))

        frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": email,
                "company": company,
                "role_profile": "DSR",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True)

        self.assertIn("Reckon Distribution User", frappe.get_roles(email))
        self.assertTrue(
            frappe.db.exists(
                "DocPerm",
                {"parent": "DocType", "role": "Reckon Distribution User", "permlevel": 0, "read": 1},
            )
        )


class TestTenantUsersCannotHoldPlatformRoles(P0TestCase):
    def test_tenant_user_cannot_be_granted_system_manager_or_vendor_role(self):
        _company, email = self._tenant("NoSM", active=True)

        for role in ("System Manager", "Reckon Vendor Superuser"):
            with self.subTest(role=role), self.assertRaises(frappe.PermissionError):
                frappe.get_doc("User", email).add_roles(role)
            self.assertNotIn(role, frappe.get_roles(email))

    def test_platform_user_cannot_receive_tenant_assignment(self):
        company = self._company_name("NoAssign")
        email = self._email("noassign")
        self._existing_company(company)
        self._user(email, ["System Manager"])

        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": "Tenant User Assignment",
                    "user": email,
                    "company": company,
                    "role_profile": "Company Admin",
                    "active": 1,
                    "is_default": 1,
                }
            ).insert(ignore_permissions=True)

        self.assertFalse(frappe.db.exists("Tenant User Assignment", {"user": email}))

    def test_legacy_violation_cannot_bypass_and_is_audited(self):
        from reckon_saas_platform.tenant_security import audit_tenant_role_violations

        company, email = self._tenant("Legacy", active=True)
        # Simulate a pre-existing violation written before the validation existed.
        frappe.get_doc(
            {
                "doctype": "Has Role",
                "parent": email,
                "parenttype": "User",
                "parentfield": "roles",
                "role": "System Manager",
            }
        ).db_insert()
        frappe.clear_cache(user=email)
        self.assertIn("System Manager", frappe.get_roles(email))

        self.assertFalse(user_can_bypass_tenant(email))
        self.assertIn(frappe.db.escape(company), get_tenant_owned_query(user=email, doctype="Sales Invoice"))
        with patch("builtins.print"):
            violations = audit_tenant_role_violations()
        self.assertIn(
            {"user": email, "company": company, "roles": ["System Manager"]},
            [{key: row[key] for key in ("user", "company", "roles")} for row in violations],
        )

    def test_platform_user_without_assignment_still_bypasses(self):
        email = self._email("platform")
        self._user(email, ["System Manager"])

        self.assertTrue(user_can_bypass_tenant(email))
