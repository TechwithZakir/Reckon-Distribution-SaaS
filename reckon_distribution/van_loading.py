from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

MANAGER_ROLES = {"Reckon Distribution Admin", "Reckon Distribution Manager"}
CHALLAN_ACTIVE_STATUSES = {"Draft", "Pending Approval", "Approved", "Acknowledged"}


class VanLoadingError(frappe.ValidationError):
    pass


def validate_van_loading_challan(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    _validate_challan_references(doc)
    if doc.status not in CHALLAN_ACTIVE_STATUSES | {"Rejected", "Cancelled"}:
        frappe.throw(_("Unknown Van Loading Challan status: {0}").format(doc.status))
    if doc.status in {"Approved", "Acknowledged", "Cancelled"} and doc.is_new():
        frappe.throw(_("A new Van Loading Challan must start as Draft."))

    for row in doc.get("items") or []:
        if flt(row.qty) <= 0:
            frappe.throw(_("Row {0}: loading quantity must be greater than zero.").format(row.idx))
        if row.stock_category not in {"Saleable", "Supplier Free"}:
            frappe.throw(_("Row {0}: invalid stock category.").format(row.idx))
        validate_master_scope(doc.company, "Item", row.item_code)
        if row.get("batch_no"):
            _validate_batch(row.item_code, row.batch_no)

    _validate_status_transition(doc)


def validate_van_loading_acknowledgement(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    challan = get_tenant_doc("Van Loading Challan", doc.challan)
    if challan.status not in {"Approved", "Acknowledged"}:
        frappe.throw(_("Only an approved Van Loading Challan can be acknowledged."))
    if doc.dsr != challan.dsr:
        frappe.throw(_("Acknowledgement DSR must match the assigned DSR."))
    if not user_can_bypass_tenant() and frappe.session.user != doc.dsr:
        frappe.throw(_("Only the assigned DSR can acknowledge this loading."))

    for row in doc.get("items") or []:
        source_row = next(
            (item for item in challan.get("items") or [] if item.name == row.challan_item),
            None,
        )
        if not source_row:
            frappe.throw(_("Row {0}: Challan Item is not part of the linked challan.").format(row.idx))
        row.item_code = source_row.item_code
        row.loaded_qty = source_row.qty
        loaded_qty = flt(row.loaded_qty)
        accepted_qty = flt(row.accepted_qty)
        rejected_qty = flt(row.rejected_qty)
        if accepted_qty < 0 or rejected_qty < 0:
            frappe.throw(_("Row {0}: accepted and rejected quantities cannot be negative.").format(row.idx))
        if abs(accepted_qty + rejected_qty - loaded_qty) > 0.000001:
            frappe.throw(
                _("Row {0}: accepted plus rejected quantity must equal loaded quantity.").format(row.idx)
            )
        if rejected_qty and not row.get("rejection_reason"):
            frappe.throw(_("Row {0}: rejection reason is required.").format(row.idx))


def on_van_loading_acknowledgement_submit(doc, method=None) -> None:
    challan = get_tenant_doc("Van Loading Challan", doc.challan)
    if challan.status == "Acknowledged":
        return
    challan.db_set("acknowledgement", doc.name)
    challan.db_set(
        "status",
        "Acknowledged" if any(flt(row.accepted_qty) for row in doc.get("items") or []) else "Rejected",
    )
    challan.db_set("acknowledged_by", frappe.session.user)
    challan.db_set("acknowledged_on", now_datetime())


@frappe.whitelist()
def request_van_loading_approval(challan: str) -> str:
    doc = get_tenant_doc("Van Loading Challan", challan)
    _require_manager()
    if doc.status == "Pending Approval":
        return doc.name
    if doc.status != "Draft":
        frappe.throw(_("Only a Draft challan can be sent for approval."))
    doc.status = "Pending Approval"
    doc.save()
    return doc.name


@frappe.whitelist()
def approve_van_loading_challan(challan: str) -> str:
    doc = get_tenant_doc("Van Loading Challan", challan)
    _require_manager()
    if doc.stock_entry and doc.status in {"Approved", "Acknowledged"}:
        return doc.stock_entry
    if doc.status != "Pending Approval":
        frappe.throw(_("Only a Pending Approval challan can be approved."))

    _validate_available_stock(doc)
    existing = frappe.db.get_value(
        "Stock Entry",
        {"rd_van_loading_challan": doc.name, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        doc.stock_entry = existing
        doc.status = "Approved"
        doc.approved_by = frappe.session.user
        doc.approved_on = now_datetime()
        doc.save()
        return existing

    doc.status = "Approved"
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    doc.save()

    stock_entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "company": doc.company,
            "posting_date": doc.posting_date or nowdate(),
            "from_warehouse": doc.distributor_warehouse,
            "to_warehouse": doc.van_warehouse,
            "rd_van_loading_challan": doc.name,
            "items": [
                {
                    "item_code": row.item_code,
                    "qty": row.qty,
                    "uom": row.uom,
                    "conversion_factor": row.conversion_factor or 1,
                    "s_warehouse": doc.distributor_warehouse,
                    "t_warehouse": doc.van_warehouse,
                    "batch_no": row.batch_no,
                }
                for row in doc.get("items") or []
            ],
        }
    )
    stock_entry.insert()
    stock_entry.submit()

    doc.stock_entry = stock_entry.name
    doc.save()
    return stock_entry.name


@frappe.whitelist()
def acknowledge_van_loading(challan: str, items: str) -> str:
    doc = get_tenant_doc("Van Loading Challan", challan)
    if not user_can_bypass_tenant() and frappe.session.user != doc.dsr:
        frappe.throw(_("Only the assigned DSR can acknowledge this loading."))
    rows = frappe.parse_json(items) if isinstance(items, str) else items
    acknowledgement = frappe.get_doc(
        {
            "doctype": "Van Loading Acknowledgement",
            "company": doc.company,
            "challan": doc.name,
            "dsr": doc.dsr,
            "items": rows,
        }
    )
    acknowledgement.insert()
    acknowledgement.submit()
    return acknowledgement.name


@frappe.whitelist()
def cancel_van_loading_challan(challan: str) -> str:
    doc = get_tenant_doc("Van Loading Challan", challan)
    _require_manager()
    if doc.status == "Cancelled":
        return doc.name
    if doc.status == "Acknowledged":
        frappe.throw(_("Acknowledged loading cannot be cancelled."))
    if doc.stock_entry:
        stock_entry = frappe.get_doc("Stock Entry", doc.stock_entry)
        if stock_entry.docstatus == 1:
            stock_entry.cancel()
    doc.status = "Cancelled"
    doc.save()
    return doc.name


@frappe.whitelist()
def amend_van_loading_challan(challan: str) -> str:
    original = get_tenant_doc("Van Loading Challan", challan)
    _require_manager()
    if original.status != "Cancelled":
        frappe.throw(_("Only a Cancelled challan can be amended."))
    amended = frappe.copy_doc(original)
    amended.name = None
    amended.amended_from = original.name
    amended.status = "Draft"
    amended.stock_entry = None
    amended.acknowledgement = None
    amended.approved_by = None
    amended.approved_on = None
    amended.acknowledged_by = None
    amended.acknowledged_on = None
    amended.insert()
    return amended.name


def _require_manager() -> None:
    if user_can_bypass_tenant() or MANAGER_ROLES.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Manager approval is required."), frappe.PermissionError)


def _validate_challan_references(doc) -> None:
    tenant = require_tenant(company=doc.company)
    if tenant.company != doc.company:
        frappe.throw(_("Company does not match the active tenant."))
    for warehouse in [doc.distributor_warehouse, doc.van_warehouse]:
        warehouse_company, is_group = frappe.db.get_value(
            "Warehouse", warehouse, ["company", "is_group"]
        ) or (None, None)
        if warehouse_company != doc.company:
            frappe.throw(_("Warehouse {0} is not assigned to Company {1}.").format(warehouse, doc.company))
        if is_group:
            frappe.throw(_("Warehouse {0} must be a leaf warehouse.").format(warehouse))

    route = get_tenant_doc("Distribution Route", doc.route)
    if route.company != doc.company:
        frappe.throw(_("Route does not belong to the challan Company."))
    if route.assigned_user != doc.dsr:
        frappe.throw(_("The DSR is not assigned to this route."))
    if not _has_active_company_assignment(doc.dsr, doc.company) and not user_can_bypass_tenant():
        frappe.throw(_("The DSR is not assigned to this Company."))


def _has_active_company_assignment(user: str, company: str) -> bool:
    """Accept either materialized tenant assignment or Company User Permission."""
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


def _validate_available_stock(doc) -> None:
    from erpnext.stock.utils import get_stock_balance

    requested = {}
    for row in doc.get("items") or []:
        key = (row.item_code, doc.distributor_warehouse)
        requested[key] = requested.get(key, 0) + flt(row.qty) * flt(row.conversion_factor or 1)

    for (item_code, warehouse), requested_qty in requested.items():
        available = get_stock_balance(
            item_code,
            warehouse,
            doc.posting_date or nowdate(),
        )
        if requested_qty > flt(available) + 0.000001:
            frappe.throw(
                _("Insufficient stock for {0} in {1}.").format(
                    item_code, warehouse
                ),
                VanLoadingError,
            )


def _validate_status_transition(doc) -> None:
    if doc.is_new():
        if doc.status not in {"Draft", "Pending Approval"}:
            frappe.throw(_("A new Van Loading Challan must start as Draft."))
        return

    previous = frappe.db.get_value("Van Loading Challan", doc.name, "status")
    allowed = {
        "Draft": {"Draft", "Pending Approval"},
        "Pending Approval": {"Pending Approval", "Approved", "Rejected"},
        "Approved": {"Approved", "Acknowledged", "Cancelled"},
        "Acknowledged": {"Acknowledged"},
        "Rejected": {"Rejected", "Draft"},
        "Cancelled": {"Cancelled"},
    }
    if previous and doc.status not in allowed.get(previous, {previous}):
        frappe.throw(
            _("Van Loading Challan cannot move from {0} to {1} directly.").format(
                previous, doc.status
            )
        )


def _validate_batch(item_code: str, batch_no: str) -> None:
    batch_item = frappe.db.get_value("Batch", batch_no, "item")
    if not batch_item:
        frappe.throw(_("Batch {0} does not exist.").format(batch_no))
    if batch_item != item_code:
        frappe.throw(_("Batch {0} does not belong to Item {1}.").format(batch_no, item_code))


def validate_van_loading_stock_entry(doc, method=None) -> None:
    challan_name = doc.get("rd_van_loading_challan")
    if not challan_name:
        return

    challan = get_tenant_doc("Van Loading Challan", challan_name)
    if challan.status not in {"Approved", "Acknowledged"}:
        frappe.throw(_("Linked Van Loading Challan must be approved before Stock Entry creation."))
    if challan.company != doc.company:
        frappe.throw(_("Stock Entry Company must match the Van Loading Challan Company."))
    if challan.stock_entry and challan.stock_entry != doc.name:
        frappe.throw(_("The Van Loading Challan already has a different Stock Entry."))

    for row in doc.get("items") or []:
        if row.s_warehouse != challan.distributor_warehouse:
            frappe.throw(_("Stock Entry source warehouse does not match the challan."))
        if row.t_warehouse != challan.van_warehouse:
            frappe.throw(_("Stock Entry target warehouse does not match the challan."))
