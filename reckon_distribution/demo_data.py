"""Idempotent, company-isolated sample data for Distribution acceptance testing.

Run this only against a development, QA, or training tenant.  The seed creates
real ERPNext stock and accounting postings so the Distribution pages, dashboard,
and reports can be reviewed using representative history rather than mock rows.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

from reckon_distribution.collection import cancel_collection, confirm_collection
from reckon_distribution.master_data import get_or_create_company_sales_price_list
from reckon_distribution.seed import ensure_office_expense_defaults, run_distribution_seed
from reckon_distribution.settlement import create_day_settlement

DEMO_RECORD_COUNT = 100
DEMO_USER = "Administrator"
TRANSACTION_PLAN = (
    ("purchase_orders", 10),
    ("purchase_receipts", 10),
    ("challans", 10),
    ("deliveries", 20),
    ("collections", 10),
    ("settlements", 10),
    ("office_expenses", 10),
    ("outlet_visits", 10),
    ("sr_orders", 10),
)
GENERATED_DOCUMENT_PLAN = (
    ("purchase_invoices", 10),
    ("sales_invoices", 20),
)
DELIVERY_PLAN = (
    (18, "12:00:00", "12:30:00"),
    (22, "13:00:00", "13:30:00"),
)
DEMO_CHALLAN_POSTING_TIME = "08:45:00"
DEMO_SOURCE_STOCK_TIME = "08:44:59"
DEMO_CUSTOMER_DETAILS = (
    ("Bismillah General Store", "Mirpur 10, Dhaka"),
    ("Mayer Doa Store", "Kazipara, Dhaka"),
    ("Shapla Bazar", "Shewrapara, Dhaka"),
    ("Nababi General Store", "Agargaon, Dhaka"),
    ("Uttara Provisions", "Pallabi, Dhaka"),
)
DEMO_ITEM_DETAILS = (
    ("Fresh Refined Soybean Oil 1 L", "FRESH-SOYBEAN-OIL-1L", 205),
    ("ACI Pure Iodized Salt 1 kg", "ACI-IODIZED-SALT-1KG", 65),
    ("Olympic Energy Plus Biscuit 200 g", "OLYMPIC-BISCUIT-200G", 50),
    ("PRAN Mango Bar 20 g", "PRAN-MANGO-BAR-20G", 15),
    ("Wheel Washing Powder 500 g", "WHEEL-POWDER-500G", 90),
)
ROLLBACK_ORDER = (
    "DSR Day Settlement",
    "Office Expense",
    "DSR Collection Receipt",
    "Sales Invoice",
    "Delivery Note",
    "DSR Challan",
    "Purchase Invoice",
    "Purchase Receipt",
    "Purchase Order",
    "SR Order",
    "Outlet Visit",
    "Stock Entry",
    "Stock Reconciliation",
    "Payment Entry",
)
SEED_SCHEMA_REQUIREMENTS = {
    "Purchase Order": ("company", "supplier", "transaction_date", "schedule_date", "set_warehouse", "items"),
    "Purchase Order Item": ("item_code", "qty", "uom", "warehouse", "schedule_date"),
    "Purchase Receipt": (
        "company",
        "supplier",
        "posting_date",
        "posting_time",
        "set_warehouse",
        "supplier_delivery_note",
        "items",
    ),
    "Purchase Receipt Item": (
        "item_code",
        "qty",
        "warehouse",
        "purchase_order",
        "purchase_order_item",
        "rd_paid_qty",
        "rd_free_qty",
    ),
    "Delivery Note": ("rd_route", "rd_dsr", "rd_dsr_challan", "rd_idempotency_key", "items"),
    "Delivery Note Item": ("item_code", "qty", "warehouse", "rd_stock_category"),
    "Purchase Invoice": ("rd_source_purchase_receipt",),
    "Sales Invoice": ("company", "customer", "posting_date", "posting_time", "remarks", "items"),
    "Stock Entry": ("rd_van_loading_challan", "rd_dsr_day_settlement"),
    "Stock Reconciliation": ("rd_dsr_day_settlement",),
    "Payment Entry": ("rd_collection_receipt", "rd_office_expense", "rd_dsr_day_settlement"),
}


def seed_distribution_test_data(company: str, records: int = DEMO_RECORD_COUNT, months: int = 6) -> dict:
    """Create exactly 100 linked RD Demo records across the current and prior six months.

    The records use a company-derived marker and are detected before inserting,
    which makes a repeated run safe.  Generated ERPNext stock, payment, and
    draft supplier-invoice documents are intentionally not counted in the 100
    requested operational records.
    """
    _require_system_manager()
    records = cint(records)
    months = cint(months)
    if records != DEMO_RECORD_COUNT:
        frappe.throw(_("This seed is intentionally fixed at {0} operational records.").format(DEMO_RECORD_COUNT))
    if months != 6:
        frappe.throw(_("This seed is intentionally fixed to the current and prior six months."))
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))

    token = _token(company)
    _validate_seed_preflight(company)
    existing_audit = _require_empty_or_healthy_demo_dataset(company, token)
    if existing_audit:
        return {
            "company": company,
            "marker": token,
            "requested_records": DEMO_RECORD_COUNT,
            "created": {},
            "created_total": 0,
            "integrity_audit": existing_audit,
            "rerun_safe": True,
            "note": "A healthy RD Demo dataset already exists; no duplicate records were created.",
        }
    start_date = _demo_start_date(months)
    dates = [_sample_date(start_date, index, 10) for index in range(10)]
    _ensure_fiscal_year_coverage(company, dates)
    masters = _ensure_demo_masters(company, token, start_date)
    result = Counter()
    generated = Counter()

    for index, posting_date in enumerate(dates, start=1):
        item = masters["items"][(index - 1) % len(masters["items"])]
        customer = masters["customers"][(index - 1) % len(masters["customers"])]
        marker = f"{token}-{index:02d}"

        _count(result, "purchase_orders", _purchase_order(masters, item, posting_date))
        receipt = _purchase_receipt(masters, posting_date, marker)
        _count(result, "purchase_receipts", receipt)
        _count(generated, "purchase_invoices", _purchase_invoice(receipt[0], posting_date, marker))
        _ensure_challan_stock(masters, item, posting_date, marker)
        challan = _challan(masters, item, posting_date, marker)
        _count(result, "challans", challan)

        for delivery_index, (quantity, delivery_time, invoice_time) in enumerate(DELIVERY_PLAN, start=1):
            delivery = _delivery(
                masters,
                challan,
                customer,
                item,
                posting_date,
                f"{marker}-DN-{delivery_index}",
                quantity,
                delivery_time,
            )
            _count(
                result,
                "deliveries",
                delivery,
            )
            _count(
                generated,
                "sales_invoices",
                _sales_invoice(delivery[0], posting_date, marker, delivery_index, invoice_time),
            )

        _count(result, "collections", _collection(masters, customer, posting_date, marker))
        _count(result, "settlements", _settlement(challan))
        _count(result, "office_expenses", _office_expense(masters, posting_date, marker, index))
        _count(result, "outlet_visits", _outlet_visit(masters, customer, posting_date, marker))
        _count(result, "sr_orders", _sr_order(masters, customer, item, posting_date, marker))

    expected = sum(quantity for _, quantity in TRANSACTION_PLAN)
    if expected != DEMO_RECORD_COUNT:
        frappe.throw(_("The RD Demo transaction plan must total {0} records.").format(DEMO_RECORD_COUNT))
    expected_generated = dict(GENERATED_DOCUMENT_PLAN)
    if sum(expected_generated.values()) != 30:
        frappe.throw(_("The RD Demo generated-document plan must total 30 records."))
    audit = audit_distribution_test_data(company)
    if not audit["healthy"]:
        frappe.throw(_("RD Demo integrity audit failed: {0}").format("; ".join(audit["errors"])))
    return {
        "company": company,
        "marker": token,
        "period": {"from_date": start_date, "to_date": getdate(nowdate())},
        "requested_records": DEMO_RECORD_COUNT,
        "created": dict(result),
        "created_total": sum(result.values()),
        "created_generated": dict(generated),
        "generated_documents": expected_generated,
        "integrity_audit": audit,
        "rerun_safe": True,
        "note": "Generated stock, Payment Entry, Purchase Invoice, and Sales Invoice records are not included in the 100 operational records.",
    }


def preflight_distribution_test_data(company: str) -> dict:
    """Validate that a tenant can receive the linked RD Demo dataset without writing data."""
    _require_system_manager()
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))
    _validate_seed_preflight(company)
    return {
        "company": company,
        "marker": _token(company),
        "operational_documents": dict(TRANSACTION_PLAN),
        "generated_documents": dict(GENERATED_DOCUMENT_PLAN),
        "writes": False,
        "note": "Preflight passed. The seed can be run safely after reviewing this result.",
    }


def audit_distribution_test_data(company: str) -> dict:
    """Verify the complete RD Demo lifecycle and report incomplete records precisely."""
    _require_system_manager()
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))

    plan = _seed_audit_plan(company, _token(company))
    expected = {**dict(TRANSACTION_PLAN), **dict(GENERATED_DOCUMENT_PLAN)}
    errors = []
    for key, expected_count in expected.items():
        names = plan[key]["names"]
        if len(names) != expected_count:
            errors.append(_("{0}: expected {1}, found {2}.").format(key, expected_count, len(names)))
        invalid = plan[key]["invalid"]
        if invalid:
            errors.append(_("{0}: invalid records {1}.").format(key, ", ".join(invalid)))

    return {
        "company": company,
        "marker": _token(company),
        "healthy": not errors,
        "errors": errors,
        "records": {key: len(value["names"]) for key, value in plan.items()},
        "invalid_records": {key: value["invalid"] for key, value in plan.items() if value["invalid"]},
    }


def rollback_distribution_test_data(
    company: str, dry_run: bool = True, confirm_rollback: bool = False
) -> dict:
    """Reverse and remove only this Company's RD Demo transactions.

    A preview is the default. A confirmed rollback cancels submitted documents
    first, allowing ERPNext to reverse stock and accounting entries before the
    cancelled demo records are removed. Shared setup, fiscal years, and seeded
    masters are deliberately retained.
    """
    _require_system_manager()
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))

    _validate_seed_schema()
    token = _token(company)
    plan = _rollback_plan(company, token)
    counts = {doctype: len(names) for doctype, names in plan.items() if names}
    dry_run = bool(cint(dry_run))
    confirm_rollback = bool(cint(confirm_rollback))
    if dry_run:
        return {
            "company": company,
            "marker": token,
            "writes": False,
            "records": counts,
            "names": plan,
            "note": "Preview only. Set dry_run=false and confirm_rollback=true to reverse this dataset.",
        }
    if not confirm_rollback:
        frappe.throw(
            _(
                "Refusing to change data without confirm_rollback=true. Run the default preview first."
            )
        )

    removed = {}
    for doctype in ROLLBACK_ORDER:
        names = plan.get(doctype, [])
        for name in names:
            _rollback_document(doctype, name)
        if names:
            removed[doctype] = len(names)

    return {
        "company": company,
        "marker": token,
        "writes": True,
        "removed": removed,
        "note": "RD Demo transactions were reversed and removed. Masters and fiscal years were retained.",
    }


def reset_distribution_test_data(
    company: str, dry_run: bool = True, confirm_reset: bool = False
) -> dict:
    """Remove only this Company's RD Demo transactions and demo masters.

    The default is a read-only preview. A confirmed reset reverses operational
    documents first, then removes their item prices, route assignments, tenant
    scopes, routes, warehouses, items, customers, and supplier. Company
    settings, accounts, fiscal years, and every non-demo record are retained.
    """
    _require_system_manager()
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))

    dry_run = bool(cint(dry_run))
    confirm_reset = bool(cint(confirm_reset))
    transaction_plan = _rollback_plan(company, _token(company))
    master_plan = _demo_master_plan(company, _token(company))
    if dry_run:
        return {
            "company": company,
            "marker": _token(company),
            "writes": False,
            "transactions": {doctype: len(names) for doctype, names in transaction_plan.items() if names},
            "masters": {doctype: len(names) for doctype, names in master_plan.items() if names},
            "note": "Preview only. Set dry_run=false and confirm_reset=true to remove this RD Demo dataset.",
        }
    if not confirm_reset:
        frappe.throw(_("Refusing to reset data without confirm_reset=true. Run the preview first."))

    removed_ledger_rows = _remove_demo_ledger_rows(transaction_plan, master_plan)
    removed_transactions = _hard_reset_demo_transactions(transaction_plan)
    removed_masters = _remove_demo_masters(master_plan)
    return {
        "company": company,
        "marker": _token(company),
        "writes": True,
        "transactions": removed_transactions,
        "ledger_rows": removed_ledger_rows,
        "masters": removed_masters,
        "retained_warehouses": master_plan["Warehouse"],
        "note": (
            "The RD Demo transactions and reusable masters were reset. Warehouses with stock history "
            "were retained because ERPNext does not permit their deletion."
        ),
    }


def test_distribution_demo_data_lifecycle(company: str, confirm_cleanup: bool = False) -> dict:
    """Run a full seed, audit, and rollback test against an empty RD Demo dataset.

    This is intended for a QA or training tenant. It refuses to run when a prior
    demo dataset exists and requires explicit cleanup confirmation because the
    test creates and then reverses real ERPNext stock and accounting postings.
    """
    _require_system_manager()
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist.").format(company))
    if not cint(confirm_cleanup):
        frappe.throw(_("Set confirm_cleanup=true to run the seed-and-rollback lifecycle test."))

    before = _rollback_plan(company, _token(company))
    existing = {doctype: names for doctype, names in before.items() if names}
    if existing:
        frappe.throw(
            _(
                "RD Demo records already exist. Review or roll them back before running the lifecycle test: {0}"
            ).format(", ".join(existing))
        )

    seeded = seed_distribution_test_data(company)
    audit = audit_distribution_test_data(company)
    if not audit["healthy"]:
        frappe.throw(_("RD Demo lifecycle audit failed: {0}").format("; ".join(audit["errors"])))

    rollback = rollback_distribution_test_data(company, dry_run=False, confirm_rollback=True)
    remaining = _rollback_plan(company, _token(company))
    undeleted = {doctype: names for doctype, names in remaining.items() if names}
    if undeleted:
        frappe.throw(
            _("RD Demo lifecycle rollback left records behind: {0}").format(", ".join(undeleted))
        )

    return {
        "company": company,
        "marker": _token(company),
        "passed": True,
        "seeded": seeded,
        "audit": audit,
        "rollback": rollback,
        "note": "The test dataset was fully rolled back; shared demo masters and fiscal years were retained.",
    }


def _rollback_plan(company: str, token: str) -> dict[str, list[str]]:
    """Select only records that carry the fixed, company-specific demo marker."""
    marker = f"{token}-%"
    masters = _demo_master_plan(company, token)
    suppliers = masters["Supplier"]
    routes = masters["Distribution Route"]
    purchase_receipts = _names(
        "Purchase Receipt", {"company": company, "supplier_delivery_note": ["like", f"{marker}-PR"]}
    )
    challans = _names("DSR Challan", {"company": company, "route": ["in", routes]}) if routes else []
    settlements = _names("DSR Day Settlement", {"challan": ["in", challans]}) if challans else []
    collections = _names(
        "DSR Collection Receipt", {"company": company, "idempotency_key": ["like", f"{marker}-COL"]}
    )
    expenses = _names("Office Expense", {"company": company, "reference_no": ["like", f"{marker}-EXP"]})
    stock_entries = set()
    if challans:
        stock_entries.update(_names("Stock Entry", {"rd_van_loading_challan": ["in", challans]}))
    if settlements:
        stock_entries.update(_names("Stock Entry", {"rd_dsr_day_settlement": ["in", settlements]}))
    stock_entries.update(
        _names("Stock Entry", {"company": company, "remarks": ["like", f"{marker}-STOCK%"]})
    )

    return {
        "DSR Day Settlement": settlements,
        "Office Expense": expenses,
        "DSR Collection Receipt": collections,
        "Sales Invoice": _names(
            "Sales Invoice", {"company": company, "remarks": ["like", f"{marker}-DN-%-SI"]}
        ),
        "Delivery Note": _names(
            "Delivery Note",
            {"company": company, "rd_idempotency_key": ["like", f"{marker}-DN-%"]},
        ),
        "DSR Challan": challans,
        "Purchase Invoice": _purchase_invoice_names(purchase_receipts),
        "Purchase Receipt": purchase_receipts,
        "Purchase Order": _names("Purchase Order", {"company": company, "supplier": ["in", suppliers]})
        if suppliers
        else [],
        "SR Order": _names("SR Order", {"company": company, "idempotency_key": ["like", f"{marker}-SRO"]}),
        "Outlet Visit": _names(
            "Outlet Visit", {"company": company, "idempotency_key": ["like", f"{marker}-VIS"]}
        ),
        "Stock Entry": sorted(stock_entries),
        "Stock Reconciliation": _names(
            "Stock Reconciliation", {"rd_dsr_day_settlement": ["in", settlements]}
        )
        if settlements
        else [],
        "Payment Entry": _payment_entry_names(collections, expenses, settlements),
    }


def _demo_master_plan(company: str, token: str) -> dict[str, list[str]]:
    """Return only deterministic masters owned by this Company's RD Demo dataset."""
    suffix = token[-6:]
    items = _names("Item", {"item_code": ["like", f"{token}-%"]})
    suppliers = _names(
        "Supplier",
        {
            "rd_company": company,
            "supplier_name": ["like", f"%{suffix}%"],
        },
    )
    customers = _names(
        "Customer",
        {
            "rd_company": company,
            "customer_name": ["like", f"%{suffix}%"],
        },
    )
    routes = _names(
        "Distribution Route",
        {
            "company": company,
            "route_code": ["in", [f"DEMO{token[-4:]}", f"DHK-MIRPUR10-{suffix}"]],
        },
    )
    warehouses = _names(
        "Warehouse",
        {
            "company": company,
            "warehouse_name": ["in", _demo_warehouse_names(token)],
        },
    )
    assignments = _names("Retailer Route Assignment", {"route": ["in", routes]}) if routes else []
    item_prices = _names("Item Price", {"item_code": ["in", items]}) if items else []
    bins = set()
    if items:
        bins.update(_names("Bin", {"item_code": ["in", items]}))
    if warehouses:
        bins.update(_names("Bin", {"warehouse": ["in", warehouses]}))
    scoped_masters = items + item_prices + suppliers + customers + warehouses
    scopes = (
        _names(
            "Distribution Master Scope",
            {"company": company, "master_name": ["in", scoped_masters]},
        )
        if scoped_masters
        else []
    )
    return {
        "Item Price": item_prices,
        "Retailer Route Assignment": assignments,
        "Distribution Master Scope": scopes,
        "Bin": sorted(bins),
        "Distribution Route": routes,
        "Warehouse": warehouses,
        "Item": items,
        "Customer": customers,
        "Supplier": suppliers,
    }


def _remove_demo_masters(plan: dict[str, list[str]]) -> dict[str, int]:
    """Delete demo masters after their linked transactions have been reversed."""
    removed = {}
    for doctype in (
        "Item Price",
        "Retailer Route Assignment",
        "Distribution Master Scope",
        "Bin",
        "Distribution Route",
        "Item",
        "Customer",
        "Supplier",
    ):
        names = list(plan.get(doctype, []))
        if doctype == "Warehouse":
            names.sort(
                key=lambda name: frappe.db.get_value("Warehouse", name, "lft") or 0,
                reverse=True,
            )
        for name in names:
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        if names:
            removed[doctype] = len(names)
    return removed


def _remove_demo_ledger_rows(
    transaction_plan: dict[str, list[str]], master_plan: dict[str, list[str]]
) -> dict[str, int]:
    """Remove ledger history for only the selected, deleted RD Demo vouchers.

    ERPNext normally retains cancelled ledger history. That is correct for
    business records, but it prevents a deliberately resettable demo warehouse
    from being deleted. The plan is marker-scoped and built before rollback, so
    this never targets a tenant's ordinary vouchers or warehouses.
    """
    removed = {}
    for ledger_doctype in ("Stock Ledger Entry", "GL Entry", "Payment Ledger Entry"):
        if not frappe.db.exists("DocType", ledger_doctype):
            continue
        deleted = 0
        for voucher_type, voucher_names in transaction_plan.items():
            if not voucher_names:
                continue
            filters = {"voucher_type": voucher_type, "voucher_no": ["in", voucher_names]}
            deleted += frappe.db.count(ledger_doctype, filters)
            frappe.db.delete(ledger_doctype, filters=filters)
        if ledger_doctype == "Stock Ledger Entry" and master_plan["Warehouse"]:
            warehouse_filters = {"warehouse": ["in", master_plan["Warehouse"]]}
            deleted += frappe.db.count(ledger_doctype, warehouse_filters)
            frappe.db.delete(ledger_doctype, filters=warehouse_filters)
        if ledger_doctype == "Stock Ledger Entry" and master_plan["Item"]:
            # Older partial seeds may have posted demo items into a company
            # warehouse before the deterministic demo warehouse existed.
            # These item codes are exclusive to this resettable dataset.
            item_filters = {"item_code": ["in", master_plan["Item"]]}
            deleted += frappe.db.count(ledger_doctype, item_filters)
            frappe.db.delete(ledger_doctype, filters=item_filters)
        if deleted:
            removed[ledger_doctype] = deleted
    return removed


def _payment_entry_names(collections: list[str], expenses: list[str], settlements: list[str]) -> list[str]:
    names = set()
    for fieldname, records in (
        ("rd_collection_receipt", collections),
        ("rd_office_expense", expenses),
        ("rd_dsr_day_settlement", settlements),
    ):
        if records:
            names.update(_names("Payment Entry", {fieldname: ["in", records]}))
    return sorted(names)


def _names(doctype: str, filters: dict) -> list[str]:
    return frappe.get_all(doctype, filters=filters, pluck="name", limit_page_length=10_000)


def _purchase_invoice_names(receipt_names: list[str]) -> list[str]:
    """Find every invoice generated from the demo receipts.

    ERPNext maps a receipt to invoice rows through ``purchase_receipt`` while
    Distribution also stores the source receipt in ``rd_source_purchase_receipt``.
    Include both paths so a reset always reverses invoice dependencies before a
    receipt is cancelled, including records created before the custom field was
    available.
    """
    if not receipt_names:
        return []

    names = set(
        _names("Purchase Invoice", {"rd_source_purchase_receipt": ["in", receipt_names]})
    )
    names.update(
        frappe.get_all(
            "Purchase Invoice Item",
            filters={"parenttype": "Purchase Invoice", "purchase_receipt": ["in", receipt_names]},
            pluck="parent",
            limit_page_length=10_000,
        )
    )
    return sorted(names)


def _rollback_document(doctype: str, name: str) -> None:
    if not frappe.db.exists(doctype, name):
        return
    if doctype == "DSR Collection Receipt":
        cancel_collection(name)
    else:
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.flags.ignore_permissions = True
            doc.cancel()
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)


def _hard_reset_demo_transactions(plan: dict[str, list[str]]) -> dict[str, int]:
    """Clear selected demo documents even when ERPNext backlinks block cancellation.

    This is intentionally reserved for ``reset_distribution_test_data`` after
    the caller has explicitly confirmed the reset. The plan is restricted to
    this Company's deterministic RD Demo marker, route, items, and supplier.
    A normal cancellation is attempted first so standard reversal hooks run;
    the direct fallback only removes a selected demo document and its child
    rows when a partially-created legacy chain cannot be cancelled.
    """
    for doctype in ROLLBACK_ORDER:
        for name in plan.get(doctype, []):
            _try_cancel_demo_document(doctype, name)

    removed = Counter()
    for doctype in ROLLBACK_ORDER:
        for name in plan.get(doctype, []):
            if _hard_delete_demo_document(doctype, name):
                removed[doctype] += 1
    return dict(removed)


def _try_cancel_demo_document(doctype: str, name: str) -> None:
    if not frappe.db.exists(doctype, name):
        return
    try:
        if doctype == "DSR Collection Receipt":
            cancel_collection(name)
            return
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.flags.ignore_permissions = True
            doc.cancel()
    except Exception:
        # A reset is allowed to remove only explicitly selected demo records.
        # The controlled delete pass below handles legacy backlink chains.
        return


def _hard_delete_demo_document(doctype: str, name: str) -> bool:
    if not frappe.db.exists(doctype, name):
        return False

    if doctype == "Purchase Receipt":
        for invoice in _purchase_invoice_names([name]):
            _hard_delete_demo_document("Purchase Invoice", invoice)

    try:
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        return True
    except Exception:
        meta = frappe.get_meta(doctype)
        for table_field in meta.get_table_fields():
            child_doctype = table_field.options
            if child_doctype and frappe.db.exists("DocType", child_doctype):
                frappe.db.sql(
                    "delete from `tab{}` where parent = %s".format(child_doctype.replace("`", "")),
                    name,
                )
        frappe.db.delete(doctype, {"name": name})
        return True


def _ensure_demo_masters(company: str, token: str, start_date) -> dict:
    """Create only the narrowly scoped masters a blank training tenant needs."""
    run_distribution_seed(company, f"{token}-defaults")
    ensure_office_expense_defaults(company)
    currency = frappe.db.get_value("Company", company, "default_currency") or "BDT"
    price_list = get_or_create_company_sales_price_list(company)
    source_warehouse = _demo_source_warehouse(company, token)
    van_warehouse = _demo_van_warehouse(company, token)
    supplier = _supplier(company, token)
    customers = [_customer(company, token, index) for index in range(1, len(DEMO_CUSTOMER_DETAILS) + 1)]
    items = [_item(company, token, index) for index in range(1, len(DEMO_ITEM_DETAILS) + 1)]
    for index, item in enumerate(items, start=1):
        _item_price(company, item, price_list, DEMO_ITEM_DETAILS[index - 1][2], currency)

    route = _route(company, token)
    for customer in customers:
        _route_assignment(company, customer, route, start_date)

    settings = frappe.get_doc("Distribution Settings", company)
    changed = False
    if not settings.default_warehouse:
        settings.default_warehouse = source_warehouse
        changed = True
    if not settings.default_cash_account:
        settings.default_cash_account = _office_cash_account(company)
        changed = True
    if changed:
        settings.save(ignore_permissions=True)

    return {
        "company": company,
        "currency": currency,
        "token": token,
        "price_list": price_list,
        "source_warehouse": source_warehouse,
        "van_warehouse": van_warehouse,
        "supplier": supplier,
        "customers": customers,
        "items": items,
        "route": route,
        "cash_account": _office_cash_account(company),
        "expense_settings": frappe.get_doc("Office Expense Settings", company),
    }


def _validate_seed_schema() -> None:
    """Fail before writes when the site has not received Distribution migrations."""
    missing = []
    for doctype, fieldnames in SEED_SCHEMA_REQUIREMENTS.items():
        if not frappe.db.exists("DocType", doctype):
            missing.append(doctype)
            continue
        meta = frappe.get_meta(doctype)
        for fieldname in fieldnames:
            if not meta.has_field(fieldname):
                missing.append(f"{doctype}.{fieldname}")
    if missing:
        frappe.throw(
            _(
                "The Distribution seed requires an up-to-date site schema. Missing: {0}. "
                "Run `bench --site <site> migrate` and try again."
            ).format(", ".join(missing))
        )


def _validate_seed_preflight(company: str) -> None:
    """Validate schema and Company accounting defaults before the first insert."""
    _validate_seed_schema()
    defaults = frappe.db.get_value(
        "Company",
        company,
        ["default_currency", "default_receivable_account", "default_payable_account"],
        as_dict=True,
    )
    missing = []
    if not defaults or not defaults.default_currency:
        missing.append("default currency")
    if not defaults or not defaults.default_receivable_account:
        missing.append("default receivable account")
    if not defaults or not defaults.default_payable_account:
        missing.append("default payable account")
    if missing:
        frappe.throw(
            _("Company {0} must have {1} before seeding invoices and payments.").format(
                company, ", ".join(missing)
            )
        )


def _require_empty_or_healthy_demo_dataset(company: str, token: str) -> dict | None:
    """Prevent a new seed from being layered over a partial prior run."""
    plan = _rollback_plan(company, token)
    existing = {doctype: names for doctype, names in plan.items() if names}
    if not existing:
        return None

    audit = audit_distribution_test_data(company)
    if audit["healthy"]:
        return audit

    frappe.throw(
        _(
            "An incomplete RD Demo dataset already exists for {0}. "
            "Run reset_distribution_test_data with confirm_reset=true before seeding again. Existing: {1}"
        ).format(company, ", ".join(existing))
    )


def _demo_start_date(months: int):
    """Use a stable monthly seed window so repeated runs share the same keys."""
    current = getdate(nowdate())
    return add_months(current.replace(day=1), -months)


def _seed_audit_plan(company: str, token: str) -> dict[str, dict[str, list[str]]]:
    """Return each expected demo document with records that cannot support reports."""
    marker = f"{token}-%"
    masters = _demo_master_plan(company, token)
    suppliers = masters["Supplier"]
    routes = masters["Distribution Route"]
    purchase_orders = _audit_documents(
        "Purchase Order", {"company": company, "supplier": ["in", suppliers]}, docstatus=1
    ) if suppliers else _empty_audit()
    purchase_receipts = _audit_documents(
        "Purchase Receipt",
        {"company": company, "supplier_delivery_note": ["like", f"{marker}-PR"]},
        docstatus=1,
    )
    purchase_invoices = _audit_documents(
        "Purchase Invoice",
        {"rd_source_purchase_receipt": ["in", purchase_receipts["names"]]},
        docstatus=1,
    ) if purchase_receipts["names"] else _empty_audit()
    challans = _audit_documents(
        "DSR Challan", {"company": company, "route": ["in", routes]}, docstatus=1, status="Submitted"
    ) if routes else _empty_audit()
    deliveries = _audit_documents(
        "Delivery Note",
        {"company": company, "rd_idempotency_key": ["like", f"{marker}-DN-%"]},
        docstatus=1,
    )
    sales_invoices = _audit_documents(
        "Sales Invoice", {"company": company, "remarks": ["like", f"{marker}-DN-%-SI"]}, docstatus=1
    )
    collections = _audit_documents(
        "DSR Collection Receipt",
        {"company": company, "idempotency_key": ["like", f"{marker}-COL"]},
        status="Confirmed",
    )
    settlements = _audit_documents(
        "DSR Day Settlement", {"challan": ["in", challans["names"]]}, docstatus=1, status="Submitted"
    ) if challans["names"] else _empty_audit()
    expenses = _audit_documents(
        "Office Expense",
        {"company": company, "reference_no": ["like", f"{marker}-EXP"]},
        docstatus=1,
        status="Submitted",
    )
    visits = _audit_documents(
        "Outlet Visit",
        {"company": company, "idempotency_key": ["like", f"{marker}-VIS"]},
        status="Completed",
        status_field="visit_status",
    )
    orders = _audit_documents(
        "SR Order", {"company": company, "idempotency_key": ["like", f"{marker}-SRO"]}, status="Draft"
    )
    challans["invalid"].extend(
        _invalid_submitted_links("DSR Challan", challans["names"], "stock_entry", "Stock Entry")
    )
    deliveries["invalid"].extend(
        _invalid_allowed_links(
            "Delivery Note", deliveries["names"], "rd_dsr_challan", challans["names"]
        )
    )
    sales_invoices["invalid"].extend(
        _invalid_sales_invoice_delivery_links(sales_invoices["names"], deliveries["names"])
    )
    collections["invalid"].extend(
        _invalid_submitted_links(
            "DSR Collection Receipt", collections["names"], "payment_entry", "Payment Entry"
        )
    )
    settlements["invalid"].extend(
        _invalid_submitted_links(
            "DSR Day Settlement", settlements["names"], "stock_return_entry", "Stock Entry"
        )
    )
    expenses["invalid"].extend(
        _invalid_submitted_links("Office Expense", expenses["names"], "payment_entry", "Payment Entry")
    )
    purchase_receipts["invalid"].extend(
        _invalid_stock_ledger_vouchers("Purchase Receipt", purchase_receipts["names"])
    )
    deliveries["invalid"].extend(
        _invalid_stock_ledger_vouchers("Delivery Note", deliveries["names"])
    )
    purchase_invoices["invalid"].extend(
        _invalid_gl_vouchers("Purchase Invoice", purchase_invoices["names"])
    )
    sales_invoices["invalid"].extend(
        _invalid_gl_vouchers("Sales Invoice", sales_invoices["names"])
    )
    return {
        "purchase_orders": purchase_orders,
        "purchase_receipts": purchase_receipts,
        "purchase_invoices": purchase_invoices,
        "challans": challans,
        "deliveries": deliveries,
        "sales_invoices": sales_invoices,
        "collections": collections,
        "settlements": settlements,
        "office_expenses": expenses,
        "outlet_visits": visits,
        "sr_orders": orders,
    }


def _audit_documents(
    doctype: str,
    filters: dict,
    *,
    docstatus: int | None = None,
    status: str | None = None,
    status_field: str = "status",
) -> dict:
    fields = ["name", "docstatus"]
    if status is not None and frappe.get_meta(doctype).has_field(status_field):
        fields.append(status_field)
    rows = frappe.get_all(doctype, filters=filters, fields=fields, order_by="name")
    invalid = []
    for row in rows:
        if docstatus is not None and cint(row.docstatus) != docstatus:
            invalid.append(row.name)
            continue
        if status is not None and row.get(status_field) != status:
            invalid.append(row.name)
    return {"names": [row.name for row in rows], "invalid": invalid}


def _empty_audit() -> dict[str, list[str]]:
    return {"names": [], "invalid": []}


def _invalid_submitted_links(
    doctype: str, names: list[str], link_field: str, linked_doctype: str
) -> list[str]:
    if not names:
        return []
    rows = frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", link_field])
    invalid = []
    for row in rows:
        linked_name = row.get(link_field)
        if not linked_name or frappe.db.get_value(linked_doctype, linked_name, "docstatus") != 1:
            invalid.append(row.name)
    return invalid


def _invalid_allowed_links(
    doctype: str, names: list[str], link_field: str, allowed_names: list[str]
) -> list[str]:
    if not names:
        return []
    allowed = set(allowed_names)
    rows = frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", link_field])
    return [row.name for row in rows if row.get(link_field) not in allowed]


def _invalid_sales_invoice_delivery_links(invoice_names: list[str], delivery_names: list[str]) -> list[str]:
    if not invoice_names:
        return []
    linked = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": ["in", invoice_names]},
        fields=["parent", "delivery_note"],
    )
    allowed = set(delivery_names)
    linked_by_invoice = {}
    for row in linked:
        linked_by_invoice.setdefault(row.parent, set()).add(row.delivery_note)
    return [
        invoice_name
        for invoice_name in invoice_names
        if not linked_by_invoice.get(invoice_name, set()).intersection(allowed)
    ]


def _invalid_stock_ledger_vouchers(doctype: str, names: list[str]) -> list[str]:
    if not names:
        return []
    posted = set(
        frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_type": doctype, "voucher_no": ["in", names], "is_cancelled": 0},
            pluck="voucher_no",
        )
    )
    return [name for name in names if name not in posted]


def _invalid_gl_vouchers(doctype: str, names: list[str]) -> list[str]:
    if not names:
        return []
    posted = set(
        frappe.get_all(
            "GL Entry",
            filters={"voucher_type": doctype, "voucher_no": ["in", names], "is_cancelled": 0},
            pluck="voucher_no",
        )
    )
    return [name for name in names if name not in posted]


def _ensure_fiscal_year_coverage(company: str, dates: list[date]) -> None:
    """Extend the Company's established fiscal calendar for the seed period.

    ERPNext never permits stock or accounting entries outside an active fiscal
    year.  A training tenant often has an older fiscal year but no current one,
    so derive missing periods from its existing start month and day.  We do not
    invent a fiscal calendar for a Company that has never configured one.
    """
    configured = _company_fiscal_years(company)
    template = configured[-1] if configured else _latest_fiscal_year()
    if not template:
        frappe.throw(
            _(
                "Configure at least one Fiscal Year before seeding RD Demo data. "
                "The seed will then extend that same fiscal calendar for the requested period."
            )
        )

    template_start = getdate(template.year_start_date)
    for posting_date in dates:
        if _has_fiscal_year(company, posting_date):
            continue
        start_date, end_date = _fiscal_period(posting_date, template_start.month, template_start.day)
        _ensure_fiscal_year(company, start_date, end_date)


def _company_fiscal_years(company: str) -> list:
    years = []
    for values in frappe.get_all(
        "Fiscal Year", fields=["name", "year_start_date", "year_end_date"], order_by="year_end_date asc"
    ):
        fiscal_year = frappe.get_doc("Fiscal Year", values.name)
        if any(row.company == company for row in fiscal_year.get("companies") or []):
            years.append(values)
    return years


def _latest_fiscal_year():
    years = frappe.get_all(
        "Fiscal Year", fields=["name", "year_start_date", "year_end_date"], order_by="year_end_date desc", limit_page_length=1
    )
    return years[0] if years else None


def _has_fiscal_year(company: str, posting_date) -> bool:
    from erpnext.accounts.utils import get_fiscal_year

    try:
        get_fiscal_year(posting_date, company=company)
    except Exception as error:
        from erpnext.accounts.utils import FiscalYearError

        if isinstance(error, FiscalYearError):
            return False
        raise
    return True


def _fiscal_period(posting_date, start_month: int, start_day: int) -> tuple[date, date]:
    posting_date = getdate(posting_date)
    start_year = posting_date.year
    if (posting_date.month, posting_date.day) < (start_month, start_day):
        start_year -= 1
    start_date = date(start_year, start_month, start_day)
    return start_date, date(start_year + 1, start_month, start_day) - timedelta(days=1)


def _ensure_fiscal_year(company: str, start_date: date, end_date: date) -> str:
    existing = frappe.db.get_value(
        "Fiscal Year", {"year_start_date": start_date, "year_end_date": end_date}, "name"
    )
    if existing:
        fiscal_year = frappe.get_doc("Fiscal Year", existing)
        if not any(row.company == company for row in fiscal_year.get("companies") or []):
            fiscal_year.append("companies", {"company": company})
            fiscal_year.save(ignore_permissions=True)
        return fiscal_year.name

    label = f"{start_date.year}-{end_date.year}"
    if frappe.db.exists("Fiscal Year", label):
        abbreviation = frappe.db.get_value("Company", company, "abbr") or company
        label = f"{label} {abbreviation}"
    return frappe.get_doc(
        {
            "doctype": "Fiscal Year",
            "year": label,
            "year_start_date": start_date,
            "year_end_date": end_date,
            "companies": [{"company": company}],
        }
    ).insert(ignore_permissions=True).name


def _purchase_order(masters: dict, item: str, posting_date) -> tuple[str, bool]:
    existing = frappe.db.get_value(
        "Purchase Order",
        {
            "company": masters["company"],
            "supplier": masters["supplier"],
            "transaction_date": posting_date,
            "schedule_date": posting_date,
        },
        "name",
    )
    if existing:
        _submit_if_draft("Purchase Order", existing)
        return existing, False
    doc = frappe.get_doc(
        {
            "doctype": "Purchase Order",
            "company": masters["company"],
            "supplier": masters["supplier"],
            "transaction_date": posting_date,
            "schedule_date": posting_date,
            "set_warehouse": masters["source_warehouse"],
            "currency": masters["currency"],
            "price_list_currency": masters["currency"],
            "ignore_pricing_rule": 1,
            "items": [_purchase_item(item, masters["source_warehouse"], posting_date, 160, 55)],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name, True


def _purchase_receipt(masters: dict, posting_date, marker: str) -> tuple[str, bool]:
    existing = frappe.db.get_value(
        "Purchase Receipt",
        {"company": masters["company"], "supplier_delivery_note": f"{marker}-PR"},
        "name",
    )
    if existing:
        _submit_if_draft("Purchase Receipt", existing)
        return existing, False
    purchase_order = frappe.db.get_value(
        "Purchase Order",
        {
            "company": masters["company"],
            "supplier": masters["supplier"],
            "transaction_date": posting_date,
            "schedule_date": posting_date,
        },
        "name",
    )
    if not purchase_order:
        frappe.throw(_("RD Demo purchase order for {0} was not found.").format(posting_date))

    purchase_order_doc = _submit_if_draft("Purchase Order", purchase_order)
    doc = _make_purchase_receipt(purchase_order_doc, masters, posting_date)
    doc.posting_date = posting_date
    doc.posting_time = "08:00:00"
    doc.set_posting_time = 1
    doc.set_warehouse = masters["source_warehouse"]
    doc.supplier_delivery_note = f"{marker}-PR"
    doc.bill_no = f"{marker}-BILL"
    doc.bill_date = posting_date
    doc.currency = masters["currency"]
    doc.price_list_currency = masters["currency"]
    doc.ignore_pricing_rule = 1
    for row in doc.get("items") or []:
        row.rd_paid_qty = flt(row.qty)
        row.rd_free_qty = 0
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name, True


def _purchase_invoice(receipt_name: str, posting_date, marker: str) -> tuple[str, bool]:
    """Submit one native supplier invoice per seeded receipt for payable reports."""
    existing = frappe.db.get_value(
        "Purchase Invoice",
        {"rd_source_purchase_receipt": receipt_name, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        doc = frappe.get_doc("Purchase Invoice", existing)
        if doc.docstatus == 0:
            doc.posting_date = posting_date
            doc.posting_time = "09:00:00"
            doc.set_posting_time = 1
            doc.bill_no = f"{marker}-BILL"
            doc.bill_date = posting_date
            doc.due_date = posting_date
            doc.remarks = f"{marker}-PI"
            doc.submit()
        if doc.docstatus != 1:
            frappe.throw(_("RD Demo Purchase Invoice {0} is cancelled and cannot be reused.").format(existing))
        frappe.db.set_value("Purchase Receipt", receipt_name, "rd_invoice_status", "Submitted")
        return existing, False

    from reckon_distribution.purchase_receipt import _map_purchase_invoice

    receipt = _submit_if_draft("Purchase Receipt", receipt_name)
    doc = _map_purchase_invoice(receipt)
    doc.posting_date = posting_date
    doc.posting_time = "09:00:00"
    doc.set_posting_time = 1
    doc.bill_no = f"{marker}-BILL"
    doc.bill_date = posting_date
    doc.due_date = posting_date
    doc.remarks = f"{marker}-PI"
    doc.insert(ignore_permissions=True)
    doc.submit()
    receipt.db_set("rd_purchase_invoice", doc.name, update_modified=False)
    receipt.db_set("rd_invoice_status", "Submitted", update_modified=False)
    return doc.name, True


def _ensure_challan_stock(masters: dict, item: str, posting_date, marker: str) -> None:
    """Guarantee the demo handoff has stock even if an older partial run did not post it."""
    from erpnext.stock.utils import get_stock_balance

    required_qty = 80
    available_qty = flt(
        get_stock_balance(
            item,
            masters["source_warehouse"],
            posting_date,
            posting_time=DEMO_SOURCE_STOCK_TIME,
        )
    )
    if available_qty >= required_qty:
        return

    entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "purpose": "Material Receipt",
            "company": masters["company"],
            "posting_date": posting_date,
            "posting_time": "08:30:00",
            "set_posting_time": 1,
            "to_warehouse": masters["source_warehouse"],
            "remarks": f"{marker}-STOCK source warehouse safeguard",
            "items": [
                {
                    "item_code": item,
                    "qty": required_qty - available_qty,
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "t_warehouse": masters["source_warehouse"],
                    "basic_rate": 55,
                }
            ],
        }
    )
    entry.insert(ignore_permissions=True)
    entry.submit()
    available_qty = flt(
        get_stock_balance(
            item,
            masters["source_warehouse"],
            posting_date,
            posting_time=DEMO_SOURCE_STOCK_TIME,
        )
    )
    if available_qty + 0.000001 < required_qty:
        frappe.throw(
            _(
                "RD Demo source stock safeguard could not post {0} of Item {1} in warehouse {2} "
                "by {3}; only {4} is available."
            ).format(required_qty, item, masters["source_warehouse"], DEMO_SOURCE_STOCK_TIME, available_qty)
        )


def _make_purchase_receipt(purchase_order, masters: dict, posting_date):
    """Map the native Purchase Order so receipt rows retain ERPNext links."""
    try:
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

        return make_purchase_receipt(purchase_order.name)
    except ImportError:
        doc = frappe.get_doc(
            {
                "doctype": "Purchase Receipt",
                "company": masters["company"],
                "supplier": masters["supplier"],
                "posting_date": posting_date,
                "posting_time": "08:00:00",
                "set_warehouse": masters["source_warehouse"],
                "items": [],
            }
        )
        for order_item in purchase_order.get("items") or []:
            pending_qty = flt(order_item.qty) - flt(order_item.received_qty)
            if pending_qty <= 0:
                continue
            row = _purchase_item(
                item=order_item.item_code,
                warehouse=order_item.warehouse,
                schedule_date=posting_date,
                qty=pending_qty,
                rate=order_item.rate,
            )
            row.update(
                {
                    "purchase_order": purchase_order.name,
                    "purchase_order_item": order_item.name,
                    "rd_paid_qty": pending_qty,
                    "rd_free_qty": 0,
                }
            )
            doc.append("items", row)
        return doc


def _submit_if_draft(doctype: str, name: str):
    """Resume a prior partial seed only when its source document is still usable."""
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus == 0:
        doc.submit()
    if doc.docstatus != 1:
        frappe.throw(
            _("RD Demo {0} {1} is cancelled and cannot be reused. Delete it or create a new demo Company.").format(
                doctype, name
            )
        )
    return doc


def _purchase_item(item: str, warehouse: str, schedule_date, qty: int, rate: int) -> dict:
    return {
        "item_code": item,
        "qty": qty,
        "received_qty": qty,
        "stock_qty": qty,
        "uom": "Nos",
        "stock_uom": "Nos",
        "conversion_factor": 1,
        "warehouse": warehouse,
        "schedule_date": schedule_date,
        "rate": rate,
        "base_rate": rate,
        "amount": qty * rate,
        "base_amount": qty * rate,
    }


def _challan(masters: dict, item: str, posting_date, marker: str) -> tuple[str, bool]:
    existing = frappe.db.get_value(
        "DSR Challan",
        {"company": masters["company"], "route": masters["route"], "posting_date": posting_date},
        "name",
    )
    if existing:
        _submit_if_draft("DSR Challan", existing)
        _assert_challan_stock_transfer(existing, masters, posting_date)
        return existing, False
    doc = frappe.get_doc(
        {
            "doctype": "DSR Challan",
            "company": masters["company"],
            "posting_date": posting_date,
            "status": "Draft",
            "distributor_warehouse": masters["source_warehouse"],
            "van_warehouse": masters["van_warehouse"],
            "route": masters["route"],
            "dsr": DEMO_USER,
            "items": [
                {
                    "item_code": item,
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "qty": 80,
                    "unit_price": _selling_rate(masters["price_list"], item),
                    "stock_category": "Saleable",
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.flags.rd_stock_entry_posting_time = DEMO_CHALLAN_POSTING_TIME
    doc.submit()
    _assert_challan_stock_transfer(doc.name, masters, posting_date)
    return doc.name, True


def _assert_challan_stock_transfer(challan_name: str, masters: dict, posting_date) -> None:
    """Fail early if a submitted challan did not post its required stock movement."""
    stock_entry = frappe.db.get_value("DSR Challan", challan_name, "stock_entry")
    if not stock_entry:
        frappe.throw(_("RD Demo DSR Challan {0} did not create a stock transfer.").format(challan_name))
    entry = frappe.db.get_value(
        "Stock Entry", stock_entry, ["docstatus", "posting_date", "to_warehouse"], as_dict=True
    )
    if (
        not entry
        or cint(entry.docstatus) != 1
        or getdate(entry.posting_date) != getdate(posting_date)
        or entry.to_warehouse != masters["van_warehouse"]
    ):
        frappe.throw(
            _("RD Demo DSR Challan {0} has an invalid linked stock transfer {1}.").format(
                challan_name, stock_entry
            )
        )


def _delivery(
    masters: dict,
    challan: tuple[str, bool],
    customer: str,
    item: str,
    posting_date,
    marker: str,
    quantity: int,
    posting_time: str,
) -> tuple[str, bool]:
    existing = frappe.db.get_value("Delivery Note", {"rd_idempotency_key": marker}, "name")
    if existing:
        _submit_if_draft("Delivery Note", existing)
        return existing, False
    challan_name = challan[0]
    _assert_delivery_stock(masters, item, posting_date, marker, quantity, posting_time)
    rate = _selling_rate(masters["price_list"], item)
    doc = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "company": masters["company"],
            "customer": customer,
            "posting_date": posting_date,
            "posting_time": posting_time,
            "set_posting_time": 1,
            "set_warehouse": masters["van_warehouse"],
            "selling_price_list": masters["price_list"],
            "price_list_currency": masters["currency"],
            "ignore_pricing_rule": 1,
            "rd_route": masters["route"],
            "rd_dsr": DEMO_USER,
            "rd_dsr_challan": challan_name,
            "rd_idempotency_key": marker,
            "items": [
                {
                    "item_code": item,
                    "qty": quantity,
                    "uom": "Nos",
                    "stock_uom": "Nos",
                    "conversion_factor": 1,
                    "stock_qty": quantity,
                    "warehouse": masters["van_warehouse"],
                    "rd_stock_category": "Saleable",
                    "rate": rate,
                    "base_rate": rate,
                    "amount": quantity * rate,
                    "base_amount": quantity * rate,
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name, True


def _assert_delivery_stock(
    masters: dict, item: str, posting_date, marker: str, quantity: int, posting_time: str
) -> None:
    """Verify that the linked challan stock is available before creating a delivery."""
    from erpnext.stock.utils import get_stock_balance

    available_qty = flt(
        get_stock_balance(item, masters["van_warehouse"], posting_date, posting_time=posting_time)
    )
    if available_qty + 0.000001 >= flt(quantity):
        return

    frappe.throw(
        _(
            "RD Demo delivery {0} needs {1} of Item {2} in van warehouse {3} at {4}, but only {5} is posted."
        ).format(marker, quantity, item, masters["van_warehouse"], posting_time, available_qty)
    )


def _sales_invoice(
    delivery_name: str, posting_date, marker: str, delivery_index: int, posting_time: str
) -> tuple[str, bool]:
    """Submit one native Sales Invoice per delivery for revenue and ageing reports."""
    invoice_marker = f"{marker}-DN-{delivery_index}-SI"
    existing = frappe.db.get_value(
        "Sales Invoice", {"remarks": invoice_marker, "docstatus": ["!=", 2]}, "name"
    )
    if existing:
        _submit_if_draft("Sales Invoice", existing)
        return existing, False

    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

    delivery = _submit_if_draft("Delivery Note", delivery_name)
    doc = make_sales_invoice(delivery.name)
    doc.posting_date = posting_date
    doc.posting_time = posting_time
    doc.set_posting_time = 1
    doc.due_date = posting_date
    doc.update_stock = 0
    doc.ignore_pricing_rule = 1
    doc.remarks = invoice_marker
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name, True


def _collection(masters: dict, customer: str, posting_date, marker: str) -> tuple[str, bool]:
    key = f"{marker}-COL"
    existing = frappe.db.get_value("DSR Collection Receipt", {"idempotency_key": key}, "name")
    if existing:
        collection = frappe.get_doc("DSR Collection Receipt", existing)
        if collection.status == "Cancelled":
            frappe.throw(_("RD Demo collection {0} is cancelled and cannot be reused.").format(existing))
        if collection.status != "Confirmed":
            confirm_collection(existing)
        return existing, False
    doc = frappe.get_doc(
        {
            "doctype": "DSR Collection Receipt",
            "company": masters["company"],
            "customer": customer,
            "route": masters["route"],
            "dsr": DEMO_USER,
            "collection_date": posting_date,
            "amount": 4_000,
            "payment_method": "Cash",
            "reference_no": f"{marker}-COL",
            "receiving_account": masters["cash_account"],
            "note": f"RD Demo cash collection {marker}",
            "idempotency_key": key,
        }
    )
    doc.insert(ignore_permissions=True)
    confirm_collection(doc.name)
    return doc.name, True


def _settlement(challan: tuple[str, bool]) -> tuple[str, bool]:
    challan_name = challan[0]
    existing = frappe.db.get_value("DSR Day Settlement", {"challan": challan_name}, "name")
    if existing:
        doc = frappe.get_doc("DSR Day Settlement", existing)
        if doc.docstatus == 0:
            _prepare_demo_settlement(doc)
            doc.submit()
        if doc.docstatus != 1:
            frappe.throw(_("RD Demo settlement {0} is cancelled and cannot be reused.").format(existing))
        if doc.status != "Submitted":
            frappe.throw(_("RD Demo settlement {0} is not submitted.").format(existing))
        return existing, False
    settlement_name = create_day_settlement(challan_name)
    doc = frappe.get_doc("DSR Day Settlement", settlement_name)
    _prepare_demo_settlement(doc)
    doc.submit()
    return doc.name, True


def _prepare_demo_settlement(doc) -> None:
    """Populate required reconciliation values before submitting a new or resumed draft."""
    # Populate the source-driven fields first: the expected cash is calculated
    # from confirmed collections and any earlier route settlement.
    doc.run_method("validate")
    doc.cash_handover = flt(doc.expected_cash)
    for row in doc.stock_items:
        row.closing_qty = row.expected_closing_qty
    doc.run_method("validate")


def _office_expense(masters: dict, posting_date, marker: str, index: int) -> tuple[str, bool]:
    reference = f"{marker}-EXP"
    existing = frappe.db.get_value(
        "Office Expense", {"company": masters["company"], "reference_no": reference}, "name"
    )
    if existing:
        _submit_if_draft("Office Expense", existing)
        return existing, False
    settings = masters["expense_settings"]
    category = settings.categories[(index - 1) % len(settings.categories)].expense_account
    doc = frappe.get_doc(
        {
            "doctype": "Office Expense",
            "company": masters["company"],
            "posting_date": posting_date,
            "payment_method": settings.default_payment_method,
            "payee": f"RD Demo Expense Supplier {index}",
            "reference_no": reference,
            "reference_date": posting_date,
            "remarks": f"RD Demo office expense {marker}",
            "items": [
                {
                    "expense_category": category,
                    "description": "Training and report verification expense",
                    "amount": 500 + index * 25,
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name, True


def _outlet_visit(masters: dict, customer: str, posting_date, marker: str) -> tuple[str, bool]:
    key = f"{marker}-VIS"
    existing = frappe.db.get_value("Outlet Visit", {"idempotency_key": key}, "name")
    if existing:
        return existing, False
    doc = frappe.get_doc(
        {
            "doctype": "Outlet Visit",
            "company": masters["company"],
            "customer": customer,
            "route": masters["route"],
            "field_user": DEMO_USER,
            "visited_on": posting_date,
            "visit_status": "Completed",
            "idempotency_key": key,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name, True


def _sr_order(masters: dict, customer: str, item: str, posting_date, marker: str) -> tuple[str, bool]:
    key = f"{marker}-SRO"
    existing = frappe.db.get_value("SR Order", {"idempotency_key": key}, "name")
    if existing:
        return existing, False
    rate = _selling_rate(masters["price_list"], item)
    doc = frappe.get_doc(
        {
            "doctype": "SR Order",
            "company": masters["company"],
            "customer": customer,
            "route": masters["route"],
            "field_user": DEMO_USER,
            "order_date": posting_date,
            "price_list": masters["price_list"],
            "status": "Draft",
            "idempotency_key": key,
            "items": [
                {
                    "item_code": item,
                    "uom": "Nos",
                    "qty": 12,
                    "conversion_factor": 1,
                    "stock_qty": 12,
                    "rate": rate,
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name, True


def _supplier(company: str, token: str) -> str:
    supplier_name = f"Sundarban FMCG Distributors Ltd. (RD Demo {token[-6:]})"
    existing = frappe.db.get_value("Supplier", {"rd_company": company, "supplier_name": supplier_name}, "name")
    if existing:
        return existing
    group = _first_leaf("Supplier Group")
    return frappe.get_doc(
        {"doctype": "Supplier", "supplier_name": supplier_name, "supplier_group": group, "rd_company": company}
    ).insert(ignore_permissions=True).name


def _customer(company: str, token: str, index: int) -> str:
    outlet_name, location = DEMO_CUSTOMER_DETAILS[index - 1]
    customer_name = f"{outlet_name}, {location} (RD Demo {token[-6:]})"
    existing = frappe.db.get_value("Customer", {"rd_company": company, "customer_name": customer_name}, "name")
    if existing:
        return existing
    return frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_group": _first_leaf("Customer Group"),
            "territory": _first_leaf("Territory"),
            "rd_company": company,
        }
    ).insert(ignore_permissions=True).name


def _item(company: str, token: str, index: int) -> str:
    item_name, item_suffix, _rate = DEMO_ITEM_DETAILS[index - 1]
    item_code = f"{token}-{item_suffix}"
    if frappe.db.exists("Item", item_code):
        return item_code
    return frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_name,
            "item_group": _first_leaf("Item Group"),
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "rd_company": company,
        }
    ).insert(ignore_permissions=True).name


def _item_price(company: str, item: str, price_list: str, rate: int, currency: str) -> str:
    existing = frappe.db.get_value(
        "Item Price", {"item_code": item, "price_list": price_list, "selling": 1, "uom": "Nos"}, "name"
    )
    if existing:
        return existing
    return frappe.get_doc(
        {
            "doctype": "Item Price",
            "item_code": item,
            "price_list": price_list,
            "selling": 1,
            "uom": "Nos",
            "price_list_rate": rate,
            "currency": currency,
            "rd_company": company,
        }
    ).insert(ignore_permissions=True).name


def _route(company: str, token: str) -> str:
    code = f"DHK-MIRPUR10-{token[-6:]}"
    existing = frappe.db.get_value("Distribution Route", {"company": company, "route_code": code}, "name")
    if existing:
        return existing
    return frappe.get_doc(
        {
            "doctype": "Distribution Route",
            "company": company,
            "route_code": code,
            "route_name": f"Mirpur 10 - Kazipara Retail Route, Dhaka (RD Demo {token[-6:]})",
            "active": 1,
            "assigned_user": DEMO_USER,
        }
    ).insert(ignore_permissions=True).name


def _route_assignment(company: str, customer: str, route: str, start_date) -> str:
    existing = frappe.db.get_value(
        "Retailer Route Assignment", {"company": company, "customer": customer, "route": route}, "name"
    )
    if existing:
        return existing
    return frappe.get_doc(
        {
            "doctype": "Retailer Route Assignment",
            "company": company,
            "customer": customer,
            "route": route,
            "assigned_user": DEMO_USER,
            "effective_from": start_date,
            "effective_to": add_days(getdate(nowdate()), 31),
            "active": 1,
        }
    ).insert(ignore_permissions=True).name


def _demo_warehouse_names(token: str) -> tuple[str, ...]:
    """Return current and legacy warehouse labels for a resettable Dhaka demo."""
    suffix = token[-6:]
    return (
        f"RD Demo Van {token}",
        f"Dhaka North FMCG Distribution Hub - Tejgaon (RD Demo {suffix})",
        f"Mirpur 10 DSR Sales Van (RD Demo {suffix})",
        # Kept for reset discovery after a tenant upgrades from the prior seed.
        f"Dhaka FMCG Distribution Hub (RD Demo {suffix})",
        f"Mirpur 10 Delivery Van (RD Demo {suffix})",
    )


def _demo_source_warehouse(company: str, token: str) -> str:
    return _demo_warehouse(company, f"Dhaka North FMCG Distribution Hub - Tejgaon (RD Demo {token[-6:]})")


def _demo_van_warehouse(company: str, token: str) -> str:
    return _demo_warehouse(company, f"Mirpur 10 DSR Sales Van (RD Demo {token[-6:]})")


def _demo_warehouse(company: str, name: str) -> str:
    existing = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": name}, "name")
    if existing:
        return existing
    parent = frappe.db.get_value(
        "Warehouse", {"company": company, "is_group": 1, "disabled": 0}, "name", order_by="lft asc"
    )
    if not parent:
        frappe.throw(_("Create a Warehouse group for {0} before seeding RD Demo data.").format(company))
    return frappe.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": name,
            "company": company,
            "parent_warehouse": parent,
            "is_group": 0,
        }
    ).insert(ignore_permissions=True).name


def _office_cash_account(company: str) -> str:
    settings = frappe.get_doc("Office Expense Settings", company)
    account = next((row.payment_account for row in settings.payment_methods if row.enabled), None)
    if not account:
        frappe.throw(_("Office Expense Settings needs an enabled Cash or Bank payment account."))
    return account


def _selling_rate(price_list: str, item: str) -> float:
    rate = frappe.db.get_value(
        "Item Price", {"item_code": item, "price_list": price_list, "selling": 1, "uom": "Nos"}, "price_list_rate"
    )
    if rate is None:
        frappe.throw(_("RD Demo Item {0} has no selling price.").format(item))
    return flt(rate)


def _first_leaf(doctype: str) -> str:
    name = frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")
    if not name:
        frappe.throw(_("Create a leaf {0} before seeding RD Demo data.").format(doctype))
    return name


def _sample_date(start_date, index: int, total: int):
    end_date = getdate(nowdate())
    if total <= 1:
        return end_date
    offset = (end_date - start_date).days * index // (total - 1)
    return add_days(start_date, offset)


def _token(company: str) -> str:
    digest = hashlib.sha1(company.encode()).hexdigest()[:6].upper()
    return f"RDDEMO-{digest}"


def _count(counter: Counter, key: str, record: tuple[str, bool]) -> None:
    if record[1]:
        counter[key] += 1


def _require_system_manager() -> None:
    if frappe.session.user == "Administrator":
        return
    frappe.only_for("System Manager")
