from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant

MANAGEMENT_ROLES = {
    "Reckon Distribution Admin",
    "Reckon Distribution Manager",
    "Company Admin",
    "Company Manager",
}


def _report_is_available(name: str) -> bool:
    return bool(frappe.db.exists("Report", name))


def _is_management_user() -> bool:
    return user_can_bypass_tenant() or bool(MANAGEMENT_ROLES.intersection(frappe.get_roles()))


def _date_range(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    start = getdate(from_date) if from_date else getdate(add_days(nowdate(), -29))
    end = getdate(to_date) if to_date else getdate(nowdate())
    if start > end:
        frappe.throw(_("From date cannot be after to date."))
    return str(start), str(end)


def _count(doctype: str, filters: dict) -> int:
    return frappe.db.count(doctype, filters=filters)


def _sum(doctype: str, fieldname: str, filters: dict) -> float:
    value = frappe.db.get_value(doctype, filters, f"sum(`{fieldname}`)")
    return flt(value)


@frappe.whitelist()
def get_distribution_dashboard(
    from_date: str | None = None, to_date: str | None = None
) -> dict:
    """Return a company-isolated home-dashboard summary for the active tenant."""
    tenant = require_tenant()
    start, end = _date_range(from_date, to_date)
    management = _is_management_user()

    delivery_filters = {
        "company": tenant.company,
        "docstatus": 1,
        "posting_date": ["between", [start, end]],
    }
    collection_filters = {
        "company": tenant.company,
        "status": "Confirmed",
        "collection_date": ["between", [start, end]],
    }
    order_filters = {
        "company": tenant.company,
        "order_date": ["between", [start, end]],
    }

    metrics = [
        {
            "label": _("Delivered value"),
            "value": _sum("Delivery Note", "grand_total", delivery_filters),
            "format": "currency",
            "detail": _("{0} submitted delivery notes", [
                _count("Delivery Note", delivery_filters)
            ]),
        },
        {
            "label": _("Collections"),
            "value": _sum("DSR Collection Receipt", "amount", collection_filters),
            "format": "currency",
            "detail": _("{0} confirmed receipts", [
                _count("DSR Collection Receipt", collection_filters)
            ]),
        },
        {
            "label": _("Sales orders"),
            "value": _count("SR Order", order_filters),
            "format": "number",
            "detail": _("Created during this period"),
        },
        {
            "label": _("Outlet visits"),
            "value": _count(
                "Outlet Visit",
                {"company": tenant.company, "visited_on": ["between", [start, end]]},
            ),
            "format": "number",
            "detail": _("Recorded during this period"),
        },
    ]
    if management:
        receipt_filters = {
            "company": tenant.company,
            "docstatus": 1,
            "posting_date": ["between", [start, end]],
        }
        invoice_filters = {
            "company": tenant.company,
            "docstatus": 1,
            "posting_date": ["between", [start, end]],
        }
        metrics.extend(
            [
                {
                    "label": _("Goods received"),
                    "value": _sum("Purchase Receipt", "grand_total", receipt_filters),
                    "format": "currency",
                    "detail": _("{0} submitted receipts", [
                        _count("Purchase Receipt", receipt_filters)
                    ]),
                },
                {
                    "label": _("Supplier due"),
                    "value": _sum("Purchase Invoice", "outstanding_amount", invoice_filters),
                    "format": "currency",
                    "detail": _("Open amount on invoices in this period"),
                },
            ]
        )

    recent_activity = _recent_activity(tenant.company, start, end)
    return {
        "company": tenant.company,
        "from_date": start,
        "to_date": end,
        "management": management,
        "metrics": metrics,
        "recent_activity": recent_activity,
    }


def _recent_activity(company: str, start: str, end: str) -> list[dict]:
    activity = []
    for row in frappe.get_all(
        "Delivery Note",
        filters={"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]},
        fields=["name", "customer", "posting_date", "grand_total", "modified"],
        order_by="modified desc",
        limit_page_length=8,
    ):
        activity.append(
            {
                "doctype": "Delivery Note",
                "name": row.name,
                "label": _("Delivery to {0}", [row.customer]),
                "date": str(row.posting_date),
                "amount": flt(row.grand_total),
                "format": "currency",
                "modified": str(row.modified),
            }
        )
    for row in frappe.get_all(
        "DSR Collection Receipt",
        filters={"company": company, "status": "Confirmed", "collection_date": ["between", [start, end]]},
        fields=["name", "customer", "collection_date", "amount", "modified"],
        order_by="modified desc",
        limit_page_length=8,
    ):
        activity.append(
            {
                "doctype": "DSR Collection Receipt",
                "name": row.name,
                "label": _("Collection from {0}", [row.customer]),
                "date": str(row.collection_date),
                "amount": flt(row.amount),
                "format": "currency",
                "modified": str(row.modified),
            }
        )
    return sorted(activity, key=lambda row: row["modified"], reverse=True)[:10]


@frappe.whitelist()
def get_distribution_report_catalog() -> list[dict]:
    """Expose only the reports intended for the Distribution shell."""
    require_tenant()
    reports = [
        {
            "label": _("Stock Ledger"),
            "description": _("Movement history by item and warehouse."),
            "route": "stock-ledger-entry",
            "route_type": "list",
        },
        {
            "label": _("Stock Balance"),
            "description": _("Current quantity by warehouse and item."),
            "route": "Stock Balance",
            "route_type": "report",
        },
    ]
    if _is_management_user():
        reports.extend(
            [
                {
                    "label": _("Sales Register"),
                    "description": _("Submitted customer invoices and values."),
                    "route": "Sales Register",
                    "route_type": "report",
                },
                {
                    "label": _("Purchase Register"),
                    "description": _("Supplier invoices and received value."),
                    "route": "Purchase Register",
                    "route_type": "report",
                },
                {
                    "label": _("Accounts Payable"),
                    "description": _("Supplier dues from submitted invoices."),
                    "route": "Accounts Payable",
                    "route_type": "report",
                },
            ]
        )
    return [report for report in reports if report["route_type"] == "list" or _report_is_available(report["route"])]
