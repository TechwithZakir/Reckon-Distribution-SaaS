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

ACTIVE_CHALLAN_STATUSES = {"Submitted", "Approved", "Acknowledged"}
SETTLEMENT_STATUSES = {"Draft", "Pending Approval", "Approved", "Rejected"}


def validate_day_settlement(doc, method=None) -> None:
    """Reconcile one DSR route-close against the submitted Daily Challan."""
    validate_tenant_owned_doc(doc)
    if doc.status not in SETTLEMENT_STATUSES:
        frappe.throw(_("Unknown settlement status."))

    _sync_settlement_from_challan(doc)
    require_tenant(company=doc.company)
    _validate_route_dsr(doc)
    _validate_unique_challan_settlement(doc)
    _calculate_cash_reconciliation(doc)
    _calculate_stock_reconciliation(doc)

    # A draft is intentionally allowed before physical cash and stock are
    # counted. The explanation becomes mandatory when it moves to approval.
    if doc.status != "Draft":
        if abs(flt(doc.cash_variance)) > 0.000001 and not doc.cash_variance_reason:
            frappe.throw(_("Cash variance requires an explanation."))
        for row in doc.get("stock_items") or []:
            if abs(flt(row.variance_qty)) > 0.000001 and not row.variance_reason:
                frappe.throw(
                    _("Stock variance requires an explanation for {0}.").format(row.item_code)
                )

@frappe.whitelist()
def create_day_settlement(challan: str) -> str:
    """Create or reopen the single route-close record for a Daily Challan."""
    daily_challan = get_tenant_doc("DSR Challan", challan)
    _require_manager_or_dsr(daily_challan)
    _validate_challan_status(daily_challan)

    existing = frappe.db.get_value(
        "DSR Day Settlement",
        {"challan": daily_challan.name, "status": ["!=", "Rejected"]},
        "name",
    )
    if existing:
        if daily_challan.get("day_settlement") != existing:
            daily_challan.db_set("day_settlement", existing, update_modified=False)
        return existing

    doc = frappe.get_doc(
        {
            "doctype": "DSR Day Settlement",
            "company": daily_challan.company,
            "challan": daily_challan.name,
            "settlement_date": daily_challan.posting_date,
            "route": daily_challan.route,
            "dsr": daily_challan.dsr,
            "status": "Draft",
        }
    )
    doc.insert()
    daily_challan.db_set("day_settlement", doc.name, update_modified=False)
    return doc.name


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


def _sync_settlement_from_challan(doc):
    if not doc.get("challan"):
        frappe.throw(_("A submitted Daily Challan is required for settlement."))
    challan = get_tenant_doc("DSR Challan", doc.challan)
    _validate_challan_status(challan)
    if doc.get("company") and doc.company != challan.company:
        frappe.throw(_("Settlement Company must match the Daily Challan."))

    doc.company = challan.company
    doc.settlement_date = challan.posting_date
    doc.route = challan.route
    doc.dsr = challan.dsr
    doc.opening_cash = _opening_cash(doc)
    doc.confirmed_cash_collections = _confirmed_cash_collections(doc)
    _sync_stock_items(doc, challan)
    return challan


def _validate_challan_status(challan) -> None:
    if challan.docstatus != 1 or challan.status not in ACTIVE_CHALLAN_STATUSES:
        frappe.throw(_("Settlement requires a submitted Daily Challan."))


def _validate_unique_challan_settlement(doc) -> None:
    filters = {"challan": doc.challan, "status": ["!=", "Rejected"]}
    if doc.name:
        filters["name"] = ["!=", doc.name]
    existing = frappe.db.exists("DSR Day Settlement", filters)
    if existing:
        frappe.throw(_("Daily Challan {0} already has settlement {1}.").format(doc.challan, existing))


def _opening_cash(doc) -> float:
    previous = frappe.get_all(
        "DSR Day Settlement",
        filters={
            "company": doc.company,
            "route": doc.route,
            "dsr": doc.dsr,
            "status": "Approved",
            "settlement_date": ["<", doc.settlement_date],
        },
        fields=["expected_cash", "cash_handover"],
        order_by="settlement_date desc, modified desc",
        limit_page_length=1,
    )
    if not previous:
        return 0.0
    return flt(previous[0].expected_cash) - flt(previous[0].cash_handover)


def _confirmed_cash_collections(doc) -> float:
    value = frappe.db.sql(
        """
        select coalesce(sum(amount), 0)
        from `tabDSR Collection Receipt`
        where company = %s and route = %s and dsr = %s and collection_date = %s
          and status = 'Confirmed' and payment_method = 'Cash'
        """,
        [doc.company, doc.route, doc.dsr, doc.settlement_date],
    )[0][0]
    return flt(value)


def _sync_stock_items(doc, challan) -> None:
    source = _challan_stock_source(challan)
    existing = {row.item_code: row for row in doc.get("stock_items") or [] if row.item_code}
    for row in list(doc.get("stock_items") or []):
        if row.item_code not in source:
            doc.remove(row)

    for item_code, values in source.items():
        row = existing.get(item_code)
        if not row:
            row = doc.append("stock_items", {})
        row.item_code = item_code
        row.uom = values["uom"]
        row.opening_qty = 0
        row.loaded_qty = values["loaded_qty"]
        row.paid_delivery_qty = values["delivered_qty"]
        row.free_delivery_qty = 0
        row.accepted_return_qty = values["returned_qty"]


def _challan_stock_source(challan) -> dict[str, dict]:
    source: dict[str, dict] = {}
    for row in challan.get("items") or []:
        item_code = row.item_code
        values = source.setdefault(
            item_code,
            {
                "uom": _stock_uom(item_code),
                "loaded_qty": 0.0,
                "delivered_qty": 0.0,
                "returned_qty": 0.0,
            },
        )
        values["loaded_qty"] += flt(row.qty) * flt(row.conversion_factor or 1)

    delivery_rows = _challan_delivery_rows(challan)
    for row in delivery_rows:
        if row.item_code in source:
            source[row.item_code]["delivered_qty"] += flt(row.stock_qty or row.qty)

    delivery_names = [row.delivery_note for row in delivery_rows]
    if delivery_names:
        returns = frappe.get_all(
            "Return Inspection",
            filters={
                "delivery_note": ["in", delivery_names],
                "warehouse": challan.van_warehouse,
                "status": "Approved",
            },
            fields=["item_code", "qty", "uom"],
        )
        for row in returns:
            if row.item_code in source:
                source[row.item_code]["returned_qty"] += _stock_quantity(
                    row.item_code, row.qty, row.uom
                )
    return source


def _challan_delivery_rows(challan) -> list:
    base_conditions = """
        dn.company = %s and dn.docstatus = 1 and dn.rd_route = %s and dn.rd_dsr = %s
        and dn.set_warehouse = %s
    """
    parameters = [challan.company, challan.route, challan.dsr, challan.van_warehouse]
    if frappe.db.has_column("Delivery Note", "rd_dsr_challan"):
        base_conditions += """
            and (dn.rd_dsr_challan = %s or (ifnull(dn.rd_dsr_challan, '') = '' and dn.posting_date = %s))
        """
        parameters.extend([challan.name, challan.posting_date])
    else:
        base_conditions += " and dn.posting_date = %s"
        parameters.append(challan.posting_date)
    return frappe.db.sql(
        f"""
        select dn.name as delivery_note, item.item_code, item.qty, item.stock_qty
        from `tabDelivery Note` dn
        inner join `tabDelivery Note Item` item on item.parent = dn.name
        where {base_conditions}
        """,
        parameters,
        as_dict=True,
    )


def _stock_uom(item_code: str) -> str:
    return frappe.db.get_value("Item", item_code, "stock_uom")


def _stock_quantity(item_code: str, qty, uom: str | None) -> float:
    stock_uom = _stock_uom(item_code)
    if not uom or uom == stock_uom:
        return flt(qty)
    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "uom": uom},
        "conversion_factor",
    )
    return flt(qty) * flt(conversion_factor or 1)


def _calculate_cash_reconciliation(doc) -> None:
    expected_cash = (
        flt(doc.opening_cash)
        + flt(doc.confirmed_cash_collections)
        - flt(doc.approved_expenses)
        - flt(doc.approved_refunds)
    )
    doc.expected_cash = expected_cash
    doc.counted_cash = flt(doc.cash_handover)
    doc.cash_variance = flt(doc.cash_handover) - expected_cash


def _calculate_stock_reconciliation(doc) -> None:
    for row in doc.get("stock_items") or []:
        expected = (
            flt(row.opening_qty)
            + flt(row.loaded_qty)
            - flt(row.paid_delivery_qty)
            - flt(row.free_delivery_qty)
            + flt(row.accepted_return_qty)
        )
        row.expected_closing_qty = expected
        row.variance_qty = flt(row.closing_qty) - expected


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
    return bool(
        {"Reckon Distribution Admin", "Reckon Distribution Manager", "System Manager"}.intersection(
            frappe.get_roles()
        )
    )
