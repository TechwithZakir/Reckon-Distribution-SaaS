from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)


def validate_route_assignment(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    require_tenant(company=doc.company)
    validate_master_scope(doc.company, "Customer", doc.customer)
    route = get_tenant_doc("Distribution Route", doc.route)
    if route.company != doc.company or not route.active:
        frappe.throw(_("The route is not active for this Company."))
    if route.assigned_user != doc.assigned_user:
        frappe.throw(_("The outlet assignee must match the route DSR/SR."))
    if not _has_active_company_assignment(doc.assigned_user, doc.company) and not user_can_bypass_tenant():
        frappe.throw(_("The outlet assignee is not assigned to this Company."))
    if getdate(doc.effective_from) > getdate(doc.effective_to):
        frappe.throw(_("Assignment end date cannot be before its start date."))
    if doc.active and frappe.db.exists(
        "Retailer Route Assignment",
        {
            "company": doc.company,
            "customer": doc.customer,
            "active": 1,
            "name": ["!=", doc.name],
            "effective_from": ["<=", doc.effective_to],
            "effective_to": [">=", doc.effective_from],
        },
    ):
        frappe.throw(_("This retailer already has an overlapping active route assignment."))


def _has_active_company_assignment(user: str, company: str) -> bool:
    """Use the assignment record as the authoritative user-company link."""
    return bool(
        frappe.db.exists(
            "Tenant User Assignment",
            {"user": user, "company": company, "active": 1},
        )
    )
