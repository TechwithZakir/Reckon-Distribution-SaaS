from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)


def validate_day_settlement(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    require_tenant(company=doc.company)
    if doc.status not in {"Draft", "Pending Approval", "Approved", "Rejected"}:
        frappe.throw(_("Unknown settlement status."))
    _validate_route_dsr(doc)
    for row in doc.get("stock_items") or []:
        expected = flt(row.opening_qty) + flt(row.loaded_qty) - flt(row.paid_delivery_qty) - flt(row.free_delivery_qty) + flt(row.accepted_return_qty)
        row.expected_closing_qty = expected
        row.variance_qty = flt(row.closing_qty) - expected
        if abs(row.variance_qty) > 0.000001 and not row.variance_reason:
            frappe.throw(_("Stock variance requires an explanation for {0}.").format(row.item_code))

    expected_cash = flt(doc.opening_cash) + flt(doc.confirmed_cash_collections) - flt(doc.approved_expenses) - flt(doc.approved_refunds) - flt(doc.cash_handover)
    doc.expected_cash = expected_cash
    doc.cash_variance = flt(doc.counted_cash) - expected_cash
    if abs(doc.cash_variance) > 0.000001 and not doc.cash_variance_reason:
        frappe.throw(_("Cash variance requires an explanation."))


@frappe.whitelist()
def submit_day_settlement(settlement: str) -> str:
    doc = get_tenant_doc("DSR Day Settlement", settlement)
    _require_manager_or_dsr(doc)
    if doc.status != "Draft":
        frappe.throw(_("Only a Draft settlement can be submitted."))
    doc.status = "Pending Approval"
    doc.save()
    return doc.name


@frappe.whitelist()
def approve_day_settlement(settlement: str) -> str:
    doc = get_tenant_doc("DSR Day Settlement", settlement)
    _require_manager()
    if doc.status == "Approved":
        return doc.name
    if doc.status != "Pending Approval":
        frappe.throw(_("Only a Pending Approval settlement can be approved."))
    doc.status = "Approved"
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    doc.save()
    return doc.name


def _validate_route_dsr(doc) -> None:
    route = get_tenant_doc("Distribution Route", doc.route)
    if route.company != doc.company or route.assigned_user != doc.dsr:
        frappe.throw(_("Settlement route and DSR do not match."))


def _require_manager_or_dsr(doc) -> None:
    if user_can_bypass_tenant() or frappe.session.user == doc.dsr or _is_manager():
        return
    frappe.throw(_("Only the assigned DSR or a manager can submit this settlement."), frappe.PermissionError)


def _require_manager() -> None:
    if user_can_bypass_tenant() or _is_manager():
        return
    frappe.throw(_("Manager approval is required."), frappe.PermissionError)


def _is_manager() -> bool:
    return bool({"Reckon Distribution Admin", "Reckon Distribution Manager", "System Manager"}.intersection(frappe.get_roles()))
