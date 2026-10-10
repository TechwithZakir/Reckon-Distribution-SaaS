from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

MANAGER_ROLES = {"Reckon Distribution Admin", "Reckon Distribution Manager"}
VERIFIED_METHODS = {"Cash", "Cheque"}
SUPPORTED_METHODS = VERIFIED_METHODS | {"Bank", "MFS"}


def validate_collection_receipt(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    require_tenant(company=doc.company)
    validate_master_scope(doc.company, "Customer", doc.customer)

    if flt(doc.amount) <= 0:
        frappe.throw(_("Collection amount must be greater than zero."))
    if doc.payment_method not in SUPPORTED_METHODS:
        frappe.throw(_("Unsupported collection method."))
    if doc.payment_method in {"Bank", "MFS"} and not doc.reference_no:
        frappe.throw(_("A bank or MFS reference is required."))
    if doc.payment_method in {"Bank", "MFS"} and doc.status == "Draft":
        doc.status = "Pending Verification"

    route = get_tenant_doc("Distribution Route", doc.route)
    if route.company != doc.company or route.assigned_user != doc.dsr:
        frappe.throw(_("The DSR is not assigned to this Company route."))
    if not _has_active_company_assignment(doc.dsr, doc.company) and not user_can_bypass_tenant():
        frappe.throw(_("The DSR is not assigned to this Company."))

    if doc.status not in {"Draft", "Pending Verification", "Confirmed", "Cancelled"}:
        frappe.throw(_("Unknown collection status."))
    _validate_idempotency(doc)


def _has_active_company_assignment(user: str, company: str) -> bool:
    """Accept the assignment row or its synchronized Company User Permission."""
    if frappe.db.exists(
        "Tenant User Assignment",
        {"user": user, "company": company, "active": 1},
    ):
        return True
    return bool(
        frappe.db.exists(
            "User Permission",
            {"user": user, "allow": "Company", "for_value": company},
        )
    )


@frappe.whitelist()
def record_collection(payload: str | dict) -> str:
    data = frappe.parse_json(payload) if isinstance(payload, str) else payload
    tenant = require_tenant(company=data.get("company"))
    key = data.get("idempotency_key")
    if not key:
        frappe.throw(_("A collection idempotency key is required."))
    existing = frappe.db.get_value("DSR Collection Receipt", {"company": tenant.company, "idempotency_key": key}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "DSR Collection Receipt",
            "company": tenant.company,
            "customer": data.get("customer"),
            "route": data.get("route"),
            "dsr": frappe.session.user,
            "collection_date": data.get("collection_date") or nowdate(),
            "amount": data.get("amount"),
            "payment_method": data.get("payment_method"),
            "reference_no": data.get("reference_no"),
            "receiving_account": data.get("receiving_account"),
            "note": data.get("note"),
            "idempotency_key": key,
            "gps_latitude": data.get("gps_latitude"),
            "gps_longitude": data.get("gps_longitude"),
            "gps_accuracy": data.get("gps_accuracy"),
            "captured_on": data.get("captured_on"),
        }
    )
    doc.insert()
    if doc.payment_method in VERIFIED_METHODS:
        return confirm_collection(doc.name)
    return doc.name


@frappe.whitelist()
def confirm_collection(receipt: str) -> str:
    doc = get_tenant_doc("DSR Collection Receipt", receipt)
    _require_collector_or_manager(doc)
    if doc.status == "Confirmed":
        return doc.payment_entry
    if doc.status == "Cancelled":
        frappe.throw(_("A cancelled collection cannot be confirmed."))
    if doc.payment_method not in VERIFIED_METHODS:
        frappe.throw(_("Bank and MFS collections require manager verification."))
    return _post_collection(doc)


@frappe.whitelist()
def verify_collection(receipt: str) -> str:
    doc = get_tenant_doc("DSR Collection Receipt", receipt)
    _require_manager()
    if doc.status == "Confirmed":
        return doc.payment_entry
    if doc.status == "Cancelled":
        frappe.throw(_("A cancelled collection cannot be verified."))
    return _post_collection(doc)


@frappe.whitelist()
def cancel_collection(receipt: str) -> str:
    doc = get_tenant_doc("DSR Collection Receipt", receipt)
    _require_manager()
    if doc.status == "Cancelled":
        return doc.name
    if doc.payment_entry:
        payment = frappe.get_doc("Payment Entry", doc.payment_entry)
        if payment.docstatus == 1:
            payment.cancel()
    doc.status = "Cancelled"
    doc.save()
    return doc.name


def _post_collection(doc) -> str:
    if doc.payment_entry:
        doc.status = "Confirmed"
        doc.save()
        return doc.payment_entry

    account = doc.receiving_account
    account_company = frappe.db.get_value("Account", account, "company")
    if account_company != doc.company:
        frappe.throw(_("The receiving account must belong to the collection Company."))

    from erpnext.accounts.party import get_party_account

    receivable = get_party_account("Customer", doc.customer, doc.company)
    posting_date = doc.collection_date or nowdate()
    payment = frappe.get_doc(
        {
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "company": doc.company,
            "posting_date": posting_date,
            "party_type": "Customer",
            "party": doc.customer,
            "paid_from": receivable,
            "paid_to": account,
            "paid_amount": doc.amount,
            "received_amount": doc.amount,
            "reference_no": doc.reference_no,
            "reference_date": posting_date,
            "remarks": doc.note,
            "rd_collection_receipt": doc.name,
        }
    )
    payment.insert()
    payment.submit()
    doc.payment_entry = payment.name
    doc.status = "Confirmed"
    doc.save()
    return payment.name


def _validate_idempotency(doc) -> None:
    if not doc.idempotency_key:
        frappe.throw(_("A collection idempotency key is required."))
    existing = frappe.db.get_value(
        "DSR Collection Receipt",
        {"company": doc.company, "idempotency_key": doc.idempotency_key, "name": ["!=", doc.name]},
        ["name", "status"],
        as_dict=True,
    )
    if existing and existing.status != "Cancelled":
        frappe.throw(_("This collection was already recorded as {0}.").format(existing.name))


def _require_collector_or_manager(doc) -> None:
    if user_can_bypass_tenant() or MANAGER_ROLES.intersection(frappe.get_roles()):
        return
    if frappe.session.user != doc.dsr:
        frappe.throw(_("Only the assigned DSR or a manager can confirm this collection."), frappe.PermissionError)


def _require_manager() -> None:
    if user_can_bypass_tenant() or MANAGER_ROLES.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Manager approval is required."), frappe.PermissionError)
