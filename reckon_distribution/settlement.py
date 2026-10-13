from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

ACTIVE_CHALLAN_STATUSES = {"Submitted", "Approved", "Acknowledged"}
SETTLEMENT_STATUSES = {"Draft", "Submitted", "Cancelled", "Pending Approval", "Approved", "Rejected"}
EPSILON = 0.000001
STOCK_RECONCILIATION_POSTING_TIME = "22:45:00"
STOCK_RETURN_POSTING_TIME = "23:00:00"


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
    # counted. A variance must be explained before the document is finalised.
    if doc.status not in {"Draft", "Cancelled", "Rejected"}:
        if abs(flt(doc.cash_variance)) > EPSILON and not doc.cash_variance_reason:
            frappe.throw(_("Cash variance requires an explanation."))
        for row in doc.get("stock_items") or []:
            if abs(flt(row.variance_qty)) > EPSILON and not row.variance_reason:
                frappe.throw(
                    _("Stock variance requires an explanation for {0}.").format(
                        _stock_label(row)
                    )
                )

@frappe.whitelist()
def create_day_settlement(challan: str) -> str:
    """Create or reopen the single route-close record for a Daily Challan."""
    daily_challan = get_tenant_doc("DSR Challan", challan)
    _require_manager_or_dsr(daily_challan)
    _validate_challan_status(daily_challan)

    existing = frappe.db.get_value(
        "DSR Day Settlement",
        {"challan": daily_challan.name, "status": ["not in", ["Rejected", "Cancelled"]]},
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
    if doc.docstatus == 1:
        return doc.name
    if doc.docstatus == 2:
        frappe.throw(_("Cancelled settlements must be amended before they can be submitted."))
    if doc.status != "Draft":
        frappe.throw(_("Only a Draft settlement can be submitted."))
    doc.submit()
    return doc.name


@frappe.whitelist()
def approve_day_settlement(settlement: str) -> str:
    doc = get_tenant_doc("DSR Day Settlement", settlement)
    _require_manager()
    if doc.docstatus == 1:
        return doc.name
    return submit_day_settlement(doc.name)


def prepare_day_settlement_submission(doc) -> None:
    """Validate the operational count before creating ERPNext postings."""
    challan = _sync_settlement_from_challan(doc)
    _validate_route_dsr(doc)
    _validate_unique_challan_settlement(doc)
    _calculate_cash_reconciliation(doc)
    _calculate_stock_reconciliation(doc)

    if abs(flt(doc.opening_cash)) > EPSILON:
        frappe.throw(
            _(
                "This settlement has an unresolved opening cash balance. "
                "Close the earlier DSR settlement before submitting this one."
            )
        )
    if abs(flt(doc.cash_variance)) > EPSILON:
        frappe.throw(
            _("Cash Handed Over must equal Expected Cash Handover before submission.")
        )
    for row in doc.get("stock_items") or []:
        if frappe.db.get_value("Item", row.item_code, "has_serial_no"):
            frappe.throw(
                _("Serialized item {0} requires a serial-level stock reconciliation.").format(
                    row.item_code
                )
            )
        if abs(flt(row.variance_qty)) > EPSILON and not row.variance_reason:
            frappe.throw(
                _("Stock variance requires an explanation for {0}.").format(_stock_label(row))
            )

    _validate_cash_handover_sources(doc)
    doc.status = "Submitted"
    doc.approved_by = frappe.session.user
    doc.approved_on = frappe.utils.now_datetime()
    # Keep the controller lookup above so the validation clearly establishes
    # the warehouse pair used by on_submit.
    doc.flags.dsr_settlement_challan = challan


def post_day_settlement(doc) -> None:
    """Post the physical close, return stock, and hand over collected cash."""
    challan = getattr(doc.flags, "dsr_settlement_challan", None) or get_tenant_doc(
        "DSR Challan", doc.challan
    )
    _post_stock_reconciliation(doc, challan)
    _return_closing_stock(doc, challan)
    _post_cash_handover(doc)


def cancel_day_settlement_postings(doc) -> None:
    """Reverse generated records in dependency order when a settlement is cancelled."""
    _cancel_generated_document("Stock Entry", doc.stock_return_entry)
    _cancel_generated_document("Stock Reconciliation", doc.stock_reconciliation)
    for row in reversed(doc.get("cash_handover_payments") or []):
        _cancel_generated_document("Payment Entry", row.payment_entry)
    doc.status = "Cancelled"
    clear_day_settlement_link(doc)


def clear_day_settlement_link(doc) -> None:
    """Release the challan only when this settlement owns its current link."""
    if not doc.get("challan") or not frappe.db.exists("DSR Challan", doc.challan):
        return
    if frappe.db.get_value("DSR Challan", doc.challan, "day_settlement") == doc.name:
        frappe.db.set_value(
            "DSR Challan", doc.challan, "day_settlement", None, update_modified=False
        )


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
    filters = {"challan": doc.challan, "status": ["not in", ["Rejected", "Cancelled"]]}
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
            "status": ["in", ["Approved", "Submitted"]],
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
    return sum(flt(row.amount) for row in _cash_collection_sources(doc))


def _cash_collection_sources(doc) -> list:
    return frappe.db.sql(
        """
        select receiving_account, coalesce(sum(amount), 0) as amount
        from `tabDSR Collection Receipt`
        where company = %s and route = %s and dsr = %s and collection_date = %s
          and status = 'Confirmed' and payment_method = 'Cash'
        group by receiving_account
        """,
        [doc.company, doc.route, doc.dsr, doc.settlement_date],
        as_dict=True,
    )


def _sync_stock_items(doc, challan) -> None:
    source = _challan_stock_source(challan)
    existing = {
        _stock_key(row.item_code, row.batch_no): row
        for row in doc.get("stock_items") or []
        if row.item_code
    }
    for row in list(doc.get("stock_items") or []):
        if _stock_key(row.item_code, row.batch_no) not in source:
            doc.remove(row)

    for (item_code, batch_no), values in source.items():
        row = existing.get((item_code, batch_no))
        if not row:
            row = doc.append("stock_items", {})
        row.item_code = item_code
        row.batch_no = batch_no or None
        row.uom = values["uom"]
        row.opening_qty = 0
        row.loaded_qty = values["loaded_qty"]
        row.paid_delivery_qty = values["delivered_qty"]
        row.free_delivery_qty = 0
        row.accepted_return_qty = values["returned_qty"]


def _challan_stock_source(challan) -> dict[tuple[str, str], dict]:
    source: dict[tuple[str, str], dict] = {}
    for row in challan.get("items") or []:
        item_code = row.item_code
        key = _stock_key(item_code, row.get("batch_no"))
        values = source.setdefault(
            key,
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
        key = _stock_key(row.item_code, row.batch_no)
        if key in source:
            source[key]["delivered_qty"] += flt(row.stock_qty or row.qty)

    delivery_names = [row.delivery_note for row in delivery_rows]
    if delivery_names:
        returns = frappe.get_all(
            "Return Inspection",
            filters={
                "delivery_note": ["in", delivery_names],
                "warehouse": challan.van_warehouse,
                "status": "Approved",
            },
            fields=["item_code", "batch_no", "qty", "uom"],
        )
        for row in returns:
            key = _stock_key(row.item_code, row.batch_no)
            if key in source:
                source[key]["returned_qty"] += _stock_quantity(
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
        select dn.name as delivery_note, item.item_code, item.batch_no, item.qty, item.stock_qty
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


def _validate_cash_handover_sources(doc) -> None:
    sources = _cash_collection_sources(doc)
    collection_total = sum(flt(row.amount) for row in sources)
    if abs(flt(doc.cash_handover) - collection_total) > EPSILON:
        frappe.throw(
            _(
                "Cash Handed Over must match confirmed cash collections before submission."
            )
        )
    target_account = _default_cash_account(doc.company)
    for row in sources:
        _validate_cash_account(doc.company, row.receiving_account)
        if row.receiving_account != target_account:
            _validate_cash_account(doc.company, target_account)


def _default_cash_account(company: str) -> str:
    account = frappe.db.get_value(
        "Distribution Settings", {"company": company}, "default_cash_account"
    )
    if not account:
        frappe.throw(_("Configure Default Cash Account in Distribution Settings before settlement."))
    return account


def _validate_cash_account(company: str, account: str | None) -> None:
    values = frappe.db.get_value(
        "Account", account, ["company", "account_type", "is_group", "disabled"], as_dict=True
    )
    if not values or values.company != company or values.is_group or values.disabled:
        frappe.throw(_("Cash account {0} is not available for this company.").format(account))
    if values.account_type not in {"Cash", "Bank"}:
        frappe.throw(_("Account {0} must be a Cash or Bank account.").format(account))


def _post_stock_reconciliation(doc, challan) -> None:
    if doc.stock_reconciliation:
        return
    variance_rows = [
        row for row in doc.get("stock_items") or [] if abs(flt(row.variance_qty)) > EPSILON
    ]
    if not variance_rows:
        return

    items = []
    for row in variance_rows:
        item = {
            "item_code": row.item_code,
            "warehouse": challan.van_warehouse,
            "qty": flt(row.closing_qty),
            "valuation_rate": None,
        }
        if row.batch_no:
            item["batch_no"] = row.batch_no
        items.append(item)
    reconciliation = frappe.get_doc(
        {
            "doctype": "Stock Reconciliation",
            "company": doc.company,
            "posting_date": doc.settlement_date,
            "posting_time": STOCK_RECONCILIATION_POSTING_TIME,
            "set_posting_time": 1,
            "purpose": "Stock Reconciliation",
            "rd_dsr_day_settlement": doc.name,
            "items": items,
        }
    )
    reconciliation.flags.ignore_permissions = True
    reconciliation.insert(ignore_permissions=True)
    reconciliation.submit()
    doc.db_set("stock_reconciliation", reconciliation.name, update_modified=False)


def _return_closing_stock(doc, challan) -> None:
    if doc.stock_return_entry:
        return
    items = []
    for row in doc.get("stock_items") or []:
        if flt(row.closing_qty) <= EPSILON:
            continue
        item = {
            "item_code": row.item_code,
            "qty": flt(row.closing_qty),
            "uom": row.uom,
            "conversion_factor": 1,
            "s_warehouse": challan.van_warehouse,
            "t_warehouse": challan.distributor_warehouse,
        }
        if row.batch_no:
            item["batch_no"] = row.batch_no
        items.append(item)
    if not items:
        return

    stock_entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "company": doc.company,
            "posting_date": doc.settlement_date,
            "posting_time": STOCK_RETURN_POSTING_TIME,
            "set_posting_time": 1,
            "from_warehouse": challan.van_warehouse,
            "to_warehouse": challan.distributor_warehouse,
            "rd_dsr_day_settlement": doc.name,
            "items": items,
        }
    )
    stock_entry.flags.ignore_permissions = True
    stock_entry.insert(ignore_permissions=True)
    stock_entry.submit()
    doc.db_set("stock_return_entry", stock_entry.name, update_modified=False)


def _post_cash_handover(doc) -> None:
    target_account = _default_cash_account(doc.company)
    for source in _cash_collection_sources(doc):
        if not source.receiving_account or flt(source.amount) <= EPSILON:
            continue
        if source.receiving_account == target_account:
            continue
        payment_entry = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "payment_type": "Internal Transfer",
                "company": doc.company,
                "posting_date": doc.settlement_date,
                "paid_from": source.receiving_account,
                "paid_to": target_account,
                "paid_amount": flt(source.amount),
                "received_amount": flt(source.amount),
                "reference_no": doc.name,
                "reference_date": doc.settlement_date,
                "remarks": _("DSR cash handover for settlement {0}").format(doc.name),
                "rd_dsr_day_settlement": doc.name,
            }
        )
        payment_entry.flags.ignore_permissions = True
        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()
        frappe.get_doc(
            {
                "doctype": "DSR Day Settlement Payment",
                "parent": doc.name,
                "parenttype": "DSR Day Settlement",
                "parentfield": "cash_handover_payments",
                "source_account": source.receiving_account,
                "target_account": target_account,
                "amount": flt(source.amount),
                "payment_entry": payment_entry.name,
            }
        ).insert(ignore_permissions=True)


def _cancel_generated_document(doctype: str, name: str | None) -> None:
    if not name or not frappe.db.exists(doctype, name):
        return
    generated = frappe.get_doc(doctype, name)
    if generated.docstatus != 1:
        return
    generated.flags.ignore_permissions = True
    generated.cancel()


def _stock_key(item_code: str, batch_no: str | None) -> tuple[str, str]:
    return item_code, batch_no or ""


def _stock_label(row) -> str:
    return f"{row.item_code} ({row.batch_no})" if row.batch_no else row.item_code


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
