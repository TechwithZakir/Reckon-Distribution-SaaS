from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant

MAX_ROWS = 5000
MANAGEMENT_ROLES = {
    "Reckon Distribution Admin",
    "Reckon Distribution Manager",
    "Company Admin",
    "Company Manager",
}


def _is_management_user() -> bool:
    return user_can_bypass_tenant() or bool(MANAGEMENT_ROLES.intersection(frappe.get_roles()))


def _date_range(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    start = getdate(from_date) if from_date else getdate(add_days(nowdate(), -29))
    end = getdate(to_date) if to_date else getdate(nowdate())
    if start > end:
        frappe.throw(_("From date cannot be after to date."))
    return str(start), str(end)


def _readable(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


def _fields(doctype: str, requested: list[str]) -> list[str]:
    if not _readable(doctype):
        return []
    available = {field.fieldname for field in frappe.get_meta(doctype).fields}
    available.add("name")
    return [field for field in requested if field in available]


def _rows(
    doctype: str,
    filters: dict,
    fields: list[str],
    order_by: str = "modified desc",
    limit: int = MAX_ROWS,
) -> list[dict]:
    selected = _fields(doctype, fields)
    if not selected:
        return []
    return frappe.get_list(
        doctype,
        filters=filters,
        fields=selected,
        order_by=order_by,
        limit_page_length=limit,
        ignore_permissions=False,
    )


def _sum(doctype: str, fieldname: str, filters: dict) -> float:
    """Sum permitted rows in Python instead of invalid get_value aggregate syntax."""
    return flt(sum(flt(row.get(fieldname)) for row in _rows(doctype, filters, [fieldname])))


def _count(doctype: str, filters: dict) -> int:
    return len(_rows(doctype, filters, ["name"]))


def _total(rows: list[dict], fieldname: str) -> float:
    return flt(sum(flt(row.get(fieldname)) for row in rows))


def _months(start: str, end: str) -> list[date]:
    current = getdate(start).replace(day=1)
    last = getdate(end).replace(day=1)
    result = []
    while current <= last:
        result.append(current)
        current = current.replace(
            year=current.year + (1 if current.month == 12 else 0),
            month=1 if current.month == 12 else current.month + 1,
        )
    return result


def _month_key(value: str | date | None) -> str:
    return str(getdate(value))[:7] if value else ""


def _month_totals(rows: list[dict], date_field: str, amount_field: str) -> dict[str, float]:
    totals = defaultdict(float)
    for row in rows:
        key = _month_key(row.get(date_field))
        if key:
            totals[key] += flt(row.get(amount_field))
    return totals


def _trend(start: str, end: str, sources: dict[str, tuple[list[dict], str, str]]) -> list[dict]:
    totals = {
        name: _month_totals(rows, date_field, amount_field)
        for name, (rows, date_field, amount_field) in sources.items()
    }
    result = []
    for month in _months(start, end):
        key = month.strftime("%Y-%m")
        row = {name: round(values.get(key, 0), 2) for name, values in totals.items()}
        row.update({"month": key, "label": month.strftime("%b")})
        row["profit"] = round(row.get("sales", 0) - row.get("purchases", 0) - row.get("expenses", 0), 2)
        result.append(row)
    return result


def _status_totals(rows: list[dict]) -> list[dict]:
    counts = Counter(str(row.get("status") or "Submitted") for row in rows)
    return [{"label": label, "count": count} for label, count in counts.most_common()]


def _aging(rows: list[dict], as_of: str, amount_field: str) -> list[dict]:
    buckets = [
        {"label": "0 - 30 Days", "amount": 0.0, "count": 0},
        {"label": "31 - 60 Days", "amount": 0.0, "count": 0},
        {"label": "61 - 90 Days", "amount": 0.0, "count": 0},
        {"label": "> 90 Days", "amount": 0.0, "count": 0},
    ]
    cutoff = getdate(as_of)
    for row in rows:
        amount = flt(row.get(amount_field))
        if amount <= 0:
            continue
        due_date = getdate(row.get("due_date") or row.get("posting_date") or as_of)
        days = max(0, (cutoff - due_date).days)
        index = 0 if days <= 30 else 1 if days <= 60 else 2 if days <= 90 else 3
        buckets[index]["amount"] += amount
        buckets[index]["count"] += 1
    total = sum(item["amount"] for item in buckets)
    for item in buckets:
        item["amount"] = round(item["amount"], 2)
        item["percentage"] = round(item["amount"] / total * 100, 1) if total else 0
    return buckets


def _ranked(rows: list[dict], name_field: str, amount_field: str, limit: int = 5) -> list[dict]:
    totals = defaultdict(float)
    for row in rows:
        name = row.get(name_field) or "Unassigned"
        totals[str(name)] += flt(row.get(amount_field))
    return [
        {"name": name, "amount": round(amount, 2)}
        for name, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _performance(orders: list[dict], order_values: dict[str, float], challans: list[dict]) -> list[dict]:
    totals = defaultdict(lambda: {"role": "SR", "amount": 0.0, "count": 0})
    for order in orders:
        name = order.get("field_user") or "Unassigned SR"
        item = totals[str(name)]
        item["role"] = "SR"
        item["amount"] += order_values.get(order["name"], 0)
        item["count"] += 1
    for challan in challans:
        name = challan.get("dsr") or "Unassigned DSR"
        item = totals[str(name)]
        item["role"] = "DSR"
        item["amount"] += flt(challan.get("total_bill_amount"))
        item["count"] += 1
    return [
        {"name": name, **values}
        for name, values in sorted(totals.items(), key=lambda item: item[1]["amount"], reverse=True)[:8]
    ]


def _recent_activity(*groups: list[dict]) -> list[dict]:
    activity = []
    for rows in groups:
        activity.extend(rows)
    return sorted(activity, key=lambda row: str(row.get("modified") or row.get("date") or ""), reverse=True)[:10]


def _activity_row(row: dict, doctype: str, date_field: str, party_field: str, amount_field: str, label: str) -> dict:
    return {
        "doctype": doctype,
        "name": row.get("name"),
        "label": _(label, [row.get(party_field) or "-"]),
        "date": str(row.get(date_field) or ""),
        "amount": round(flt(row.get(amount_field)), 2),
        "format": "currency",
        "status": row.get("status") or "Submitted",
        "modified": str(row.get("modified") or row.get(date_field) or ""),
    }


@frappe.whitelist()
def get_distribution_dashboard(
    from_date: str | None = None, to_date: str | None = None
) -> dict:
    """Return a permission-aware distribution analytics dashboard for the active tenant."""
    tenant = require_tenant()
    start, end = _date_range(from_date, to_date)
    company = tenant.company
    management = _is_management_user()
    currency = frappe.db.get_value("Company", company, "default_currency") or "BDT"

    order_filters = {"company": company, "order_date": ["between", [start, end]]}
    delivery_filters = {"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]}
    receipt_filters = {"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]}
    expense_filters = {"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]}
    collection_filters = {"company": company, "status": "Confirmed", "collection_date": ["between", [start, end]]}

    orders = _rows("SR Order", order_filters, ["name", "field_user", "customer", "order_date", "status", "modified"])
    order_items = (
        _rows(
            "SR Order Item",
            {"parent": ["in", [row["name"] for row in orders]], "parenttype": "SR Order"},
            ["parent", "amount"],
        )
        if orders
        else []
    )
    order_values = defaultdict(float)
    for item in order_items:
        order_values[item.get("parent")] += flt(item.get("amount"))
    deliveries = _rows("Delivery Note", delivery_filters, ["name", "customer", "posting_date", "grand_total", "status", "modified"])
    purchases = _rows("Purchase Receipt", receipt_filters, ["name", "supplier", "posting_date", "grand_total", "status", "modified"])
    expenses = _rows("Office Expense", expense_filters, ["name", "payee", "posting_date", "total_amount", "status", "modified"])
    collections = _rows("DSR Collection Receipt", collection_filters, ["name", "customer", "collection_date", "amount", "status", "modified"])
    challans = _rows("DSR Challan", delivery_filters, ["name", "dsr", "posting_date", "total_bill_amount", "status", "modified"])
    visits = _rows("Outlet Visit", {"company": company, "visited_on": ["between", [start, end]]}, ["name", "customer", "visited_on", "visit_status", "modified"])

    sales_invoices = _rows(
        "Sales Invoice",
        {"company": company, "docstatus": 1, "posting_date": ["<=", end]},
        ["name", "customer", "posting_date", "due_date", "outstanding_amount", "modified"],
    )
    purchase_invoices = _rows(
        "Purchase Invoice",
        {"company": company, "docstatus": 1, "posting_date": ["<=", end]},
        ["name", "supplier", "posting_date", "due_date", "outstanding_amount", "modified"],
    )

    sales_total = _total(deliveries, "grand_total")
    purchase_total = _total(purchases, "grand_total")
    expense_total = _total(expenses, "total_amount")
    collection_total = _total(collections, "amount")
    operating_profit = sales_total - purchase_total - expense_total
    receivable_rows = [row for row in sales_invoices if flt(row.get("outstanding_amount")) > 0]
    payable_rows = [row for row in purchase_invoices if flt(row.get("outstanding_amount")) > 0]

    recent = _recent_activity(
        [_activity_row(row, "Delivery Note", "posting_date", "customer", "grand_total", "Delivery to {0}") for row in deliveries],
        [_activity_row(row, "DSR Collection Receipt", "collection_date", "customer", "amount", "Collection from {0}") for row in collections],
        [_activity_row(row, "Purchase Receipt", "posting_date", "supplier", "grand_total", "Purchase from {0}") for row in purchases],
        [_activity_row(row, "Office Expense", "posting_date", "payee", "total_amount", "Expense paid to {0}") for row in expenses],
    )
    trend = _trend(
        start,
        end,
        {
            "sales": (deliveries, "posting_date", "grand_total"),
            "purchases": (purchases, "posting_date", "grand_total"),
            "expenses": (expenses, "posting_date", "total_amount"),
            "collections": (collections, "collection_date", "amount"),
        },
    )

    return {
        "company": company,
        "currency": currency,
        "from_date": start,
        "to_date": end,
        "management": management,
        "kpis": {
            "sales": sales_total,
            "sales_count": len(deliveries),
            "orders": len(orders),
            "order_value": round(sum(order_values.values()), 2),
            "deliveries": len(deliveries),
            "purchases": purchase_total,
            "purchase_count": len(purchases),
            "expenses": expense_total,
            "collections": collection_total,
            "profit": round(operating_profit, 2),
            "loss": round(abs(operating_profit), 2) if operating_profit < 0 else 0,
            "receivables": round(sum(flt(row.get("outstanding_amount")) for row in receivable_rows), 2),
            "payables": round(sum(flt(row.get("outstanding_amount")) for row in payable_rows), 2),
        },
        "trend": trend,
        "performance": _performance(orders, order_values, challans),
        "top_customers": _ranked(deliveries, "customer", "grand_total"),
        "top_suppliers": _ranked(purchases, "supplier", "grand_total"),
        "delivery_status": _status_totals(deliveries),
        "order_status": _status_totals(orders),
        "purchase_status": _status_totals(purchases),
        "collection_status": _status_totals(collections),
        "receivables_aging": _aging(receivable_rows, end, "outstanding_amount"),
        "payables_aging": _aging(payable_rows, end, "outstanding_amount"),
        "recent_activity": recent,
        "visit_count": len(visits),
        "challan_count": len(challans),
    }
