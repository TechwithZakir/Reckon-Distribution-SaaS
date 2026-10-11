from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from reckon_distribution.tenant_security import require_tenant


def report_context(filters: dict | None) -> tuple[dict, str, object, object, str]:
    """Return a tenant-bound report period and its company currency."""
    values = filters or {}
    tenant = require_tenant()
    from_date = getdate(values.get("from_date") or nowdate())
    to_date = getdate(values.get("to_date") or from_date)
    if from_date > to_date:
        frappe.throw(_("From Date cannot be after To Date."))
    currency = frappe.db.get_value("Company", tenant.company, "default_currency") or "BDT"
    return values, tenant.company, from_date, to_date, currency


def summary(label: str, value: float, currency: str, indicator: str = "Blue") -> dict:
    return {"label": label, "value": flt(value), "indicator": indicator, "datatype": "Currency", "currency": currency}


def _dates(from_date, to_date) -> Iterable:
    current = from_date
    while current <= to_date:
        yield current
        current = add_days(current, 1)


def _cash_accounts(company: str, account: str | None = None) -> list[str]:
    filters = {"company": company, "is_group": 0, "account_type": ["in", ["Cash", "Bank"]]}
    if account:
        filters["name"] = account
    return frappe.get_all("Account", filters=filters, pluck="name", order_by="name")


def _account_placeholders(accounts: list[str]) -> tuple[str, list[str]]:
    return ", ".join(["%s"] * len(accounts)), accounts


def _cash_openings(company: str, accounts: list[str], from_date) -> dict[str, float]:
    if not accounts:
        return {}
    placeholders, account_values = _account_placeholders(accounts)
    rows = frappe.db.sql(
        f"""
        select account, coalesce(sum(debit - credit), 0) as balance
        from `tabGL Entry`
        where company = %s and posting_date < %s and ifnull(is_cancelled, 0) = 0
          and account in ({placeholders})
        group by account
        """,
        [company, from_date, *account_values],
        as_dict=True,
    )
    return {row.account: flt(row.balance) for row in rows}


def daily_opening_closing_balance(filters: dict | None = None):
    values, company, from_date, to_date, currency = report_context(filters)
    accounts = _cash_accounts(company, values.get("cash_account"))
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 105},
        {"label": _("Cash / Bank Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 220},
        {"label": _("Opening Balance"), "fieldname": "opening_balance", "fieldtype": "Currency", "options": "currency", "width": 135},
        {"label": _("Receipts"), "fieldname": "receipts", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Payments"), "fieldname": "payments", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Closing Balance"), "fieldname": "closing_balance", "fieldtype": "Currency", "options": "currency", "width": 135},
    ]
    if not accounts:
        return columns, [], []

    placeholders, account_values = _account_placeholders(accounts)
    movements = frappe.db.sql(
        f"""
        select posting_date, account, coalesce(sum(debit), 0) as receipts,
            coalesce(sum(credit), 0) as payments
        from `tabGL Entry`
        where company = %s and posting_date between %s and %s and ifnull(is_cancelled, 0) = 0
          and account in ({placeholders})
        group by posting_date, account
        """,
        [company, from_date, to_date, *account_values],
        as_dict=True,
    )
    movement_by_day = {(row.account, row.posting_date): row for row in movements}
    balances = defaultdict(float, _cash_openings(company, accounts, from_date))
    data = []
    total_receipts = total_payments = 0.0
    opening_total = sum(balances.values())
    for posting_date in _dates(from_date, to_date):
        for account in accounts:
            movement = movement_by_day.get((account, posting_date))
            receipts = flt(movement.receipts) if movement else 0.0
            payments = flt(movement.payments) if movement else 0.0
            opening = balances[account]
            closing = opening + receipts - payments
            data.append(
                {
                    "posting_date": posting_date,
                    "account": account,
                    "opening_balance": opening,
                    "receipts": receipts,
                    "payments": payments,
                    "closing_balance": closing,
                    "currency": currency,
                }
            )
            balances[account] = closing
            total_receipts += receipts
            total_payments += payments
    return columns, data, [
        summary(_("Opening Balance"), opening_total, currency),
        summary(_("Receipts"), total_receipts, currency, "Green"),
        summary(_("Payments"), total_payments, currency, "Orange"),
        summary(_("Closing Balance"), sum(balances.values()), currency),
    ]


def day_book(filters: dict | None = None):
    _, company, from_date, to_date, currency = report_context(filters)
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 145},
        {"label": _("Voucher No."), "fieldname": "voucher_no", "fieldtype": "Data", "width": 150},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 210},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 105},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 180},
        {"label": _("Description"), "fieldname": "remarks", "fieldtype": "Data", "width": 280},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "currency", "width": 120},
    ]
    data = frappe.db.sql(
        """
        select posting_date, voucher_type, voucher_no, account, party_type, party, remarks,
            coalesce(debit, 0) as debit, coalesce(credit, 0) as credit
        from `tabGL Entry`
        where company = %s and posting_date between %s and %s and ifnull(is_cancelled, 0) = 0
        order by posting_date, creation, name
        """,
        [company, from_date, to_date],
        as_dict=True,
    )
    debit_total = sum(flt(row.debit) for row in data)
    credit_total = sum(flt(row.credit) for row in data)
    for row in data:
        row.currency = currency
    return columns, data, [
        summary(_("Total Debit"), debit_total, currency, "Green"),
        summary(_("Total Credit"), credit_total, currency, "Blue"),
    ]


def cash_book(filters: dict | None = None):
    values, company, from_date, to_date, currency = report_context(filters)
    accounts = _cash_accounts(company, values.get("cash_account"))
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Cash / Bank Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 220},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 140},
        {"label": _("Voucher No."), "fieldname": "voucher_no", "fieldtype": "Data", "width": 150},
        {"label": _("Description"), "fieldname": "remarks", "fieldtype": "Data", "width": 260},
        {"label": _("Receipts"), "fieldname": "debit", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Payments"), "fieldname": "credit", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": "currency", "width": 125},
    ]
    if not accounts:
        return columns, [], []
    placeholders, account_values = _account_placeholders(accounts)
    data = frappe.db.sql(
        f"""
        select posting_date, account, voucher_type, voucher_no, remarks,
            coalesce(debit, 0) as debit, coalesce(credit, 0) as credit
        from `tabGL Entry`
        where company = %s and posting_date between %s and %s and ifnull(is_cancelled, 0) = 0
          and account in ({placeholders})
        order by account, posting_date, creation, name
        """,
        [company, from_date, to_date, *account_values],
        as_dict=True,
    )
    balances = defaultdict(float, _cash_openings(company, accounts, from_date))
    opening_total = sum(balances.values())
    receipts = payments = 0.0
    for row in data:
        balances[row.account] += flt(row.debit) - flt(row.credit)
        row.balance = balances[row.account]
        row.currency = currency
        receipts += flt(row.debit)
        payments += flt(row.credit)
    return columns, data, [
        summary(_("Opening Balance"), opening_total, currency),
        summary(_("Receipts"), receipts, currency, "Green"),
        summary(_("Payments"), payments, currency, "Orange"),
        summary(_("Closing Balance"), sum(balances.values()), currency),
    ]


def supplier_ledger(filters: dict | None = None):
    values, company, from_date, to_date, currency = report_context(filters)
    supplier = values.get("supplier")
    supplier_clause = " and party = %s" if supplier else ""
    supplier_values = [supplier] if supplier else []
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 210},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 145},
        {"label": _("Voucher No."), "fieldname": "voucher_no", "fieldtype": "Data", "width": 145},
        {"label": _("Description"), "fieldname": "remarks", "fieldtype": "Data", "width": 240},
        {"label": _("Invoice / Due"), "fieldname": "credit", "fieldtype": "Currency", "options": "currency", "width": 125},
        {"label": _("Payment / Adjustment"), "fieldname": "debit", "fieldtype": "Currency", "options": "currency", "width": 150},
        {"label": _("Balance Due"), "fieldname": "balance_due", "fieldtype": "Currency", "options": "currency", "width": 130},
    ]
    openings = frappe.db.sql(
        f"""
        select party as supplier, account, coalesce(sum(credit - debit), 0) as balance_due
        from `tabGL Entry`
        where company = %s and party_type = 'Supplier' and posting_date < %s
          and ifnull(is_cancelled, 0) = 0{supplier_clause}
        group by party, account
        """,
        [company, from_date, *supplier_values],
        as_dict=True,
    )
    data = frappe.db.sql(
        f"""
        select posting_date, party as supplier, account, voucher_type, voucher_no, remarks,
            coalesce(debit, 0) as debit, coalesce(credit, 0) as credit
        from `tabGL Entry`
        where company = %s and party_type = 'Supplier' and posting_date between %s and %s
          and ifnull(is_cancelled, 0) = 0{supplier_clause}
        order by party, account, posting_date, creation, name
        """,
        [company, from_date, to_date, *supplier_values],
        as_dict=True,
    )
    balances = defaultdict(float, {(row.supplier, row.account): flt(row.balance_due) for row in openings})
    opening_total = sum(balances.values())
    invoices = payments = 0.0
    for row in data:
        key = (row.supplier, row.account)
        balances[key] += flt(row.credit) - flt(row.debit)
        row.balance_due = balances[key]
        row.currency = currency
        invoices += flt(row.credit)
        payments += flt(row.debit)
    return columns, data, [
        summary(_("Opening Due"), opening_total, currency),
        summary(_("Invoices / Charges"), invoices, currency, "Orange"),
        summary(_("Payments / Adjustments"), payments, currency, "Green"),
        summary(_("Closing Due"), sum(balances.values()), currency),
    ]


def dsr_ledger(filters: dict | None = None):
    values, company, from_date, to_date, currency = report_context(filters)
    dsr = values.get("dsr")
    dsr_clause = " and dsr = %s" if dsr else ""
    dsr_values = [dsr] if dsr else []
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("DSR"), "fieldname": "dsr", "fieldtype": "Link", "options": "User", "width": 180},
        {"label": _("Transaction"), "fieldname": "transaction_type", "fieldtype": "Data", "width": 170},
        {"label": _("Reference"), "fieldname": "reference", "fieldtype": "Data", "width": 140},
        {"label": _("Retailer / Detail"), "fieldname": "detail", "fieldtype": "Data", "width": 230},
        {"label": _("Collected"), "fieldname": "collected", "fieldtype": "Currency", "options": "currency", "width": 125},
        {"label": _("Handed Over"), "fieldname": "handed_over", "fieldtype": "Currency", "options": "currency", "width": 130},
        {"label": _("DSR Custody Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": "currency", "width": 150},
    ]
    collection_opening = frappe.db.sql(
        f"""
        select dsr, coalesce(sum(amount), 0) as amount
        from `tabDSR Collection Receipt`
        where company = %s and status = 'Confirmed' and collection_date < %s{dsr_clause}
        group by dsr
        """,
        [company, from_date, *dsr_values],
        as_dict=True,
    )
    settlement_opening = frappe.db.sql(
        f"""
        select dsr, coalesce(sum(cash_handover), 0) as amount
        from `tabDSR Day Settlement`
        where company = %s and status = 'Approved' and settlement_date < %s{dsr_clause}
        group by dsr
        """,
        [company, from_date, *dsr_values],
        as_dict=True,
    )
    balances = defaultdict(float, {row.dsr: flt(row.amount) for row in collection_opening})
    for row in settlement_opening:
        balances[row.dsr] -= flt(row.amount)
    opening_total = sum(balances.values())
    collections = frappe.db.sql(
        f"""
        select collection_date as posting_date, dsr, name as reference, customer as detail,
            amount as collected
        from `tabDSR Collection Receipt`
        where company = %s and status = 'Confirmed' and collection_date between %s and %s{dsr_clause}
        """,
        [company, from_date, to_date, *dsr_values],
        as_dict=True,
    )
    settlements = frappe.db.sql(
        f"""
        select settlement_date as posting_date, dsr, name as reference, route as detail,
            cash_handover as handed_over
        from `tabDSR Day Settlement`
        where company = %s and status = 'Approved' and settlement_date between %s and %s{dsr_clause}
        """,
        [company, from_date, to_date, *dsr_values],
        as_dict=True,
    )
    data = []
    for row in collections:
        data.append({**row, "transaction_type": _("Collection"), "handed_over": 0.0, "sort_order": 0})
    for row in settlements:
        data.append({**row, "transaction_type": _("Cash Handover"), "collected": 0.0, "sort_order": 1})
    data.sort(key=lambda row: (row.posting_date, row.dsr, row.sort_order, row.reference))
    collected_total = handover_total = 0.0
    for row in data:
        collected = flt(row.collected)
        handed_over = flt(row.handed_over)
        balances[row.dsr] += collected - handed_over
        row.balance = balances[row.dsr]
        row.currency = currency
        collected_total += collected
        handover_total += handed_over
        row.pop("sort_order", None)
    return columns, data, [
        summary(_("Opening DSR Custody"), opening_total, currency),
        summary(_("Collections"), collected_total, currency, "Green"),
        summary(_("Cash Handed Over"), handover_total, currency, "Blue"),
        summary(_("Closing DSR Custody"), sum(balances.values()), currency),
    ]


def ledger_summary(filters: dict | None = None):
    _, company, from_date, to_date, currency = report_context(filters)
    columns = [
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 250},
        {"label": _("Account Type"), "fieldname": "root_type", "fieldtype": "Data", "width": 110},
        {"label": _("Opening Balance"), "fieldname": "opening_balance", "fieldtype": "Currency", "options": "currency", "width": 135},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Closing Balance"), "fieldname": "closing_balance", "fieldtype": "Currency", "options": "currency", "width": 135},
    ]
    openings = frappe.db.sql(
        """
        select gle.account, coalesce(sum(gle.debit - gle.credit), 0) as opening_balance
        from `tabGL Entry` gle
        where gle.company = %s and gle.posting_date < %s and ifnull(gle.is_cancelled, 0) = 0
        group by gle.account
        """,
        [company, from_date],
        as_dict=True,
    )
    movements = frappe.db.sql(
        """
        select gle.account, account.root_type, coalesce(sum(gle.debit), 0) as debit,
            coalesce(sum(gle.credit), 0) as credit
        from `tabGL Entry` gle
        left join `tabAccount` account on account.name = gle.account
        where gle.company = %s and gle.posting_date between %s and %s
          and ifnull(gle.is_cancelled, 0) = 0
        group by gle.account, account.root_type
        """,
        [company, from_date, to_date],
        as_dict=True,
    )
    opening_by_account = {row.account: flt(row.opening_balance) for row in openings}
    movement_by_account = {row.account: row for row in movements}
    data = []
    for account in sorted(set(opening_by_account) | set(movement_by_account)):
        movement = movement_by_account.get(account, {})
        opening = opening_by_account.get(account, 0.0)
        debit = flt(movement.get("debit"))
        credit = flt(movement.get("credit"))
        data.append(
            {
                "account": account,
                "root_type": movement.get("root_type") or "",
                "opening_balance": opening,
                "debit": debit,
                "credit": credit,
                "closing_balance": opening + debit - credit,
                "currency": currency,
            }
        )
    return columns, data, [
        summary(_("Opening Balance"), sum(row.opening_balance for row in data), currency),
        summary(_("Total Debit"), sum(row.debit for row in data), currency, "Green"),
        summary(_("Total Credit"), sum(row.credit for row in data), currency, "Blue"),
        summary(_("Closing Balance"), sum(row.closing_balance for row in data), currency),
    ]


def profit_and_loss(filters: dict | None = None):
    _, company, from_date, to_date, currency = report_context(filters)
    columns = [
        {"label": _("Type"), "fieldname": "statement_type", "fieldtype": "Data", "width": 110},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 280},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 150},
    ]
    rows = frappe.db.sql(
        """
        select account.root_type, gle.account, coalesce(sum(gle.debit), 0) as debit,
            coalesce(sum(gle.credit), 0) as credit
        from `tabGL Entry` gle
        inner join `tabAccount` account on account.name = gle.account
        where gle.company = %s and gle.posting_date between %s and %s
          and account.root_type in ('Income', 'Expense') and ifnull(gle.is_cancelled, 0) = 0
        group by account.root_type, gle.account
        order by account.root_type, gle.account
        """,
        [company, from_date, to_date],
        as_dict=True,
    )
    income_total = expense_total = 0.0
    data = []
    for row in rows:
        is_income = row.root_type == "Income"
        amount = flt(row.credit) - flt(row.debit) if is_income else flt(row.debit) - flt(row.credit)
        if not amount:
            continue
        if is_income:
            income_total += amount
        else:
            expense_total += amount
        data.append(
            {
                "statement_type": _("Income") if is_income else _("Expense"),
                "account": row.account,
                "amount": amount,
                "currency": currency,
            }
        )
    net_profit = income_total - expense_total
    return columns, data, [
        summary(_("Total Income"), income_total, currency, "Green"),
        summary(_("Total Expense"), expense_total, currency, "Orange"),
        summary(_("Net Profit") if net_profit >= 0 else _("Net Loss"), abs(net_profit), currency, "Green" if net_profit >= 0 else "Red"),
    ]
