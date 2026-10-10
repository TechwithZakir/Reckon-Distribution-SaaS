from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from reckon_distribution.route_assignment import validate_route_assignment


class TestRouteAssignment(FrappeTestCase):
    def _doc(self):
        return frappe._dict(
            {
                "name": "RRA-TEST-001",
                "company": "Horizon",
                "customer": "Retailer-001",
                "route": "Route-001",
                "assigned_user": "aa@gmail.com",
                "effective_from": "2026-10-01",
                "effective_to": "2026-10-31",
                "active": 1,
            }
        )

    def test_active_assignment_allows_company_admin_assignee(self):
        doc = self._doc()
        route = frappe._dict(
            {"company": doc.company, "active": 1, "assigned_user": doc.assigned_user}
        )

        def exists(doctype, filters=None):
            if doctype == "Tenant User Assignment":
                return True
            return False

        with patch("reckon_distribution.route_assignment.validate_tenant_owned_doc"), patch(
            "reckon_distribution.route_assignment.require_tenant"
        ), patch("reckon_distribution.route_assignment.validate_master_scope"), patch(
            "reckon_distribution.route_assignment.get_tenant_doc", return_value=route
        ), patch(
            "reckon_distribution.route_assignment.frappe.db.exists", side_effect=exists
        ), patch(
            "reckon_distribution.route_assignment.user_can_bypass_tenant", return_value=False
        ):
            validate_route_assignment(doc)
