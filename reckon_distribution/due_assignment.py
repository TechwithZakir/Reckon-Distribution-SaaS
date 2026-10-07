from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    get_user_companies,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

MANAGER_ROLES = {"Reckon Distribution Admin", "Reckon Distribution Manager"}


def validate_due_assignment(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    require_tenant(company=doc.company)
    validate_master_scope(doc.company, "Customer", doc.customer)

    route = get_tenant_doc("Distribution Route", doc.route)
    if route.company != doc.company or route.assigned_user != doc.dsr:
        frappe.throw(_("The DSR is not assigned to this Company route."))
    if doc.dsr not in get_user_companies(doc.dsr) and not user_can_bypass_tenant():
        frappe.throw(_("The DSR is not assigned to this Company."))
    if getdate(doc.effective_from) > getdate(doc.effective_to):
        frappe.throw(_("Assignment end date cannot be before its start date."))
    if doc.status not in {"Draft", "Approved", "Cancelled"}:
        frappe.throw(_("Unknown due assignment status."))
    if doc.status == "Approved":
        _validate_no_overlap(doc)


@frappe.whitelist()
def approve_due_assignment(assignment: str) -> str:
    doc = get_tenant_doc("DSR Due Assignment", assignment)
    _require_manager()
    if doc.status == "Approved":
        return doc.name
    if doc.status == "Cancelled":
        frappe.throw(_("A cancelled due assignment cannot be approved."))
    doc.status = "Approved"
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    validate_due_assignment(doc)
    doc.save()
    return doc.name


@frappe.whitelist()
def cancel_due_assignment(assignment: str) -> str:
    doc = get_tenant_doc("DSR Due Assignment", assignment)
    _require_manager()
    if doc.status == "Cancelled":
        return doc.name
    doc.status = "Cancelled"
    doc.save()
    return doc.name


def _validate_no_overlap(doc) -> None:
    filters = {
        "company": doc.company,
        "customer": doc.customer,
        "status": "Approved",
        "name": ["!=", doc.name],
        "effective_from": ["<=", doc.effective_to],
        "effective_to": [">=", doc.effective_from],
    }
    if frappe.db.exists("DSR Due Assignment", filters):
        frappe.throw(_("This retailer already has an overlapping approved due assignment."))


def _require_manager() -> None:
    if user_can_bypass_tenant() or MANAGER_ROLES.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Manager approval is required."), frappe.PermissionError)
