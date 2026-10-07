from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.due_assignment import validate_due_assignment


class TestDSRDueAssignment(FrappeTestCase):
    def _assignment(self, status="Approved"):
        return frappe._dict(
            {
                "name": "DDA-TEST-001",
                "company": "_Test Tenant Company A",
                "customer": "_Test Customer A",
                "route": "_Test Route A",
                "dsr": "dsr@example.com",
                "effective_from": "2026-10-01",
                "effective_to": "2026-10-31",
                "status": status,
            }
        )

    def test_approved_assignment_is_company_and_route_scoped(self):
        assignment = self._assignment()
        route = frappe._dict({"company": assignment.company, "assigned_user": assignment.dsr})
        with patch("reckon_distribution.due_assignment.validate_tenant_owned_doc"), patch(
            "reckon_distribution.due_assignment.require_tenant"
        ), patch("reckon_distribution.due_assignment.validate_master_scope"), patch(
            "reckon_distribution.due_assignment.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.due_assignment.get_user_companies", return_value=[assignment.company]), patch(
            "reckon_distribution.due_assignment._validate_no_overlap"
        ):
            validate_due_assignment(assignment)

    def test_assignment_rejects_overlapping_dates(self):
        assignment = self._assignment()
        route = frappe._dict({"company": assignment.company, "assigned_user": assignment.dsr})
        with patch("reckon_distribution.due_assignment.validate_tenant_owned_doc"), patch(
            "reckon_distribution.due_assignment.require_tenant"
        ), patch("reckon_distribution.due_assignment.validate_master_scope"), patch(
            "reckon_distribution.due_assignment.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.due_assignment.get_user_companies", return_value=[assignment.company]), patch(
            "reckon_distribution.due_assignment.frappe.db.exists", return_value=True
        ):
            with self.assertRaises(frappe.ValidationError):
                validate_due_assignment(assignment)

    def test_assignment_rejects_cross_company_route(self):
        assignment = self._assignment()
        route = frappe._dict({"company": "_Test Tenant Company B", "assigned_user": assignment.dsr})
        with patch("reckon_distribution.due_assignment.validate_tenant_owned_doc"), patch(
            "reckon_distribution.due_assignment.require_tenant"
        ), patch("reckon_distribution.due_assignment.validate_master_scope"), patch(
            "reckon_distribution.due_assignment.get_tenant_doc", return_value=route
        ), patch("reckon_distribution.due_assignment.get_user_companies", return_value=[assignment.company]):
            with self.assertRaises(frappe.ValidationError):
                validate_due_assignment(assignment)
