from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.tenant_security import (
    TenantResolutionError,
    get_tenant_user_assignment_query,
    has_tenant_user_assignment_permission,
    resolve_tenant,
)


class TestTenantSecurity(FrappeTestCase):
    def setUp(self):
        self.user = "tenant-user@example.com"
        self.company_a = "_Test Tenant Company A"
        self.company_b = "_Test Tenant Company B"
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for docname in frappe.get_all(
            "Tenant User Assignment",
            filters={"user": self.user},
            pluck="name",
        ):
            frappe.delete_doc(
                "Tenant User Assignment",
                docname,
                ignore_permissions=True,
                force=True,
            )

    def _assignment(self, company: str, is_default: int = 1):
        return frappe.get_doc(
            {
                "doctype": "Tenant User Assignment",
                "user": self.user,
                "company": company,
                "role_profile": "DSR",
                "active": 1,
                "is_default": is_default,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def test_resolves_single_active_company(self):
        self._assignment(self.company_a)

        tenant = resolve_tenant(user=self.user)

        self.assertEqual(tenant.user, self.user)
        self.assertEqual(tenant.company, self.company_a)

    def test_denies_user_without_company_assignment(self):
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(user=self.user)

    def test_denies_ambiguous_company_assignment_without_explicit_company(self):
        self._assignment(self.company_a, is_default=1)
        self._assignment(self.company_b, is_default=0)

        with self.assertRaises(TenantResolutionError):
            resolve_tenant(user=self.user)

    def test_allows_explicit_assigned_company_when_user_has_multiple(self):
        self._assignment(self.company_a, is_default=1)
        self._assignment(self.company_b, is_default=0)

        tenant = resolve_tenant(user=self.user, company=self.company_b)

        self.assertEqual(tenant.company, self.company_b)

    def test_rejects_unassigned_explicit_company(self):
        self._assignment(self.company_a)

        with self.assertRaises(TenantResolutionError):
            resolve_tenant(user=self.user, company=self.company_b)

    def test_company_is_immutable_after_insert(self):
        assignment = self._assignment(self.company_a)
        assignment.company = self.company_b

        with self.assertRaises(frappe.ValidationError):
            assignment.save(ignore_permissions=True)

    def test_permission_query_scopes_non_admin_to_own_assignment(self):
        condition = get_tenant_user_assignment_query(user=self.user)

        self.assertIn("`tabTenant User Assignment`.`user`", condition)
        self.assertIn(frappe.db.escape(self.user), condition)

    def test_has_permission_allows_reading_own_assignment_only(self):
        assignment = self._assignment(self.company_a)

        self.assertTrue(
            has_tenant_user_assignment_permission(
                assignment,
                user=self.user,
                permission_type="read",
            )
        )
        self.assertFalse(
            has_tenant_user_assignment_permission(
                assignment,
                user="other@example.com",
                permission_type="read",
            )
        )
        self.assertFalse(
            has_tenant_user_assignment_permission(
                assignment,
                user=self.user,
                permission_type="write",
            )
        )
