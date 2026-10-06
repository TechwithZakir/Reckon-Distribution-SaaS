from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.tenant_security import (
    CrossCompanyAccessError,
    TenantResolutionError,
    assert_file_belongs_to_tenant,
    get_tenant_doc,
    get_tenant_owned_query,
    guard_api_company,
    guarded_background_job_company,
    guarded_export_rows,
    guarded_link_search,
    has_tenant_owned_permission,
    validate_tenant_owned_doc,
)


class TestTenantAdversarialAccess(FrappeTestCase):
    def setUp(self):
        self.user_a = "tenant-a@example.com"
        self.user_b = "tenant-b@example.com"
        self.company_a = "_Test Tenant Company A"
        self.company_b = "_Test Tenant Company B"
        self.record_a = "Tenant Security Record A"
        self.record_b = "Tenant Security Record B"
        self._cleanup()
        self._assignment(self.user_a, self.company_a)
        self._assignment(self.user_b, self.company_b)
        self._record(self.record_a, self.company_a)
        self._record(self.record_b, self.company_b)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for doctype, names in {
            "Tenant Security Test Record": [self.record_a, self.record_b],
            "Tenant User Assignment": [],
        }.items():
            if doctype == "Tenant User Assignment":
                names = frappe.get_all(
                    doctype,
                    filters={"user": ["in", [self.user_a, self.user_b]]},
                    pluck="name",
                )
            for name in names:
                if frappe.db.exists(doctype, name):
                    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

    def _assignment(self, user: str, company: str):
        return frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": user,
                "company": company,
                "role_profile": "DSR",
                "active": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def _record(self, title: str, company: str):
        return frappe.get_doc(
            {
                "doctype": "Tenant Security Test Record",
                "title": title,
                "company": company,
                "payload": title,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def test_company_a_cannot_direct_load_company_b_record(self):
        with self.assertRaises(CrossCompanyAccessError):
            get_tenant_doc("Tenant Security Test Record", self.record_b, user=self.user_a)

    def test_company_a_can_direct_load_own_record(self):
        doc = get_tenant_doc("Tenant Security Test Record", self.record_a, user=self.user_a)

        self.assertEqual(doc.company, self.company_a)

    def test_permission_query_filters_list_and_report_to_company_a(self):
        condition = get_tenant_owned_query(user=self.user_a, doctype="Tenant Security Test Record")

        self.assertIn(frappe.db.escape(self.company_a), condition)
        self.assertNotIn(self.company_b, condition)

    def test_has_permission_denies_cross_company_mutation(self):
        doc_b = frappe.get_doc("Tenant Security Test Record", self.record_b)

        self.assertFalse(
            has_tenant_owned_permission(doc_b, user=self.user_a, permission_type="write")
        )

    def test_company_a_cannot_save_company_b_record(self):
        doc_b = frappe.get_doc("Tenant Security Test Record", self.record_b)

        with self.assertRaises(TenantResolutionError):
            validate_tenant_owned_doc(doc_b, user=self.user_a)

    def test_api_guard_rejects_cross_company_payload(self):
        with self.assertRaises(TenantResolutionError):
            guard_api_company(company=self.company_b, user=self.user_a)

    def test_link_search_returns_only_assigned_company_records(self):
        rows = guarded_link_search(
            "Tenant Security Test Record",
            txt="Tenant Security Record",
            searchfield="title",
            user=self.user_a,
            fields=["name", "company"],
        )

        self.assertEqual({row.company for row in rows}, {self.company_a})
        self.assertEqual({row.name for row in rows}, {self.record_a})

    def test_export_rows_returns_only_assigned_company_records(self):
        rows = guarded_export_rows("Tenant Security Test Record", user=self.user_a)

        self.assertEqual({row.company for row in rows}, {self.company_a})
        self.assertEqual({row.name for row in rows}, {self.record_a})

    def test_background_job_guard_rejects_cross_company_payload(self):
        with self.assertRaises(TenantResolutionError):
            guarded_background_job_company(self.company_b, user=self.user_a)

    def test_file_access_guard_rejects_cross_company_attachment_target(self):
        with self.assertRaises(CrossCompanyAccessError):
            assert_file_belongs_to_tenant(
                "Tenant Security Test Record",
                self.record_b,
                user=self.user_a,
            )

    def test_company_is_immutable_on_tenant_owned_records(self):
        doc = frappe.get_doc("Tenant Security Test Record", self.record_a)
        doc.company = self.company_b

        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
