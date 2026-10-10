from __future__ import annotations

import frappe
from frappe.utils import cint

from reckon_distribution.master_data import get_or_create_company_sales_price_list


OFFICE_EXPENSE_CATEGORIES = (
    ("Freight & Delivery", "Direct Expenses"),
    ("Loading & Unloading", "Direct Expenses"),
    ("Vehicle Fuel", "Direct Expenses"),
    ("Office Rent", "Indirect Expenses"),
    ("Utilities", "Indirect Expenses"),
    ("Telephone & Internet", "Indirect Expenses"),
    ("Office Supplies", "Indirect Expenses"),
    ("Travel & Conveyance", "Indirect Expenses"),
    ("Repairs & Maintenance", "Indirect Expenses"),
    ("Miscellaneous Office Expense", "Indirect Expenses"),
)


def run_distribution_seed(company: str, seed_version: str) -> dict:
    """Seed additive distribution defaults for a tenant company.

    Business data such as Item, Customer, Supplier, prices, balances, contacts,
    and stock must never be cloned from another tenant.
    """
    if not frappe.db.exists("Company", company):
        frappe.throw(frappe._("Company {0} does not exist.").format(company))

    created = []
    if not frappe.db.exists("Distribution Settings", company):
        frappe.get_doc(
            {
                "doctype": "Distribution Settings",
                "company": company,
                "supplier_goods_policy": "Supplier Provided Goods Only",
                "supplier_invoice_policy": "Auto-create Draft",
                "auto_invoice_requires_supplier_bill": 1,
                "allow_supplier_advance_without_purchase_order": 1,
                "allow_batch_expiry": 1,
            }
        ).insert(ignore_permissions=True)
        created.append("Distribution Settings")

    if not frappe.db.exists("Company UOM Profile", company):
        frappe.get_doc(
            {
                "doctype": "Company UOM Profile",
                "company": company,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        created.append("Company UOM Profile")

    get_or_create_company_sales_price_list(company)
    created.extend(ensure_office_expense_defaults(company))

    return {
        "company": company,
        "seed_version": seed_version,
        "status": "complete",
        "created": created,
        "preserved_existing_data": True,
    }


def ensure_office_expense_defaults(company: str) -> list[str]:
    """Seed a usable, Company-owned office-expense setup without replacing it.

    Every ledger is created in the tenant's own chart of accounts.  The expense
    form itself only exposes the friendly category and payment labels.
    """
    required_doctypes = {
        "Account",
        "Cost Center",
        "Mode of Payment",
        "Office Expense Settings",
    }
    if not required_doctypes.issubset(
        set(frappe.get_all("DocType", filters={"name": ["in", list(required_doctypes)]}, pluck="name"))
    ):
        return []
    if frappe.db.exists("Office Expense Settings", company):
        return []

    created: list[str] = []
    expense_root = _get_or_create_root_account(company, "Expenses", "Expense", created)
    direct_expenses = _get_or_create_account(
        company, "Direct Expenses", expense_root, "Expense", is_group=True, created=created
    )
    indirect_expenses = _get_or_create_account(
        company, "Indirect Expenses", expense_root, "Expense", is_group=True, created=created
    )
    category_rows = []
    for category, parent in OFFICE_EXPENSE_CATEGORIES:
        parent_account = direct_expenses if parent == "Direct Expenses" else indirect_expenses
        expense_account = _get_or_create_account(
            company,
            category,
            parent_account,
            "Expense",
            is_group=False,
            created=created,
        )
        category_rows.append(
            {"category": category, "expense_account": expense_account, "enabled": 1}
        )

    default_cost_center = _get_or_create_cost_center(company, created)
    cash_account = _get_or_create_cash_account(company, created)
    cash_mode = _get_or_create_cash_mode_of_payment(created)
    payment_methods = [
        {"payment_method": cash_mode, "payment_account": cash_account, "enabled": 1}
    ]
    bank_account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Bank", "is_group": 0, "disabled": 0},
        "name",
        order_by="lft asc",
    )
    if bank_account and frappe.db.exists("Mode of Payment", "Bank"):
        payment_methods.append(
            {"payment_method": "Bank", "payment_account": bank_account, "enabled": 1}
        )

    frappe.get_doc(
        {
            "doctype": "Office Expense Settings",
            "company": company,
            "default_expense_category": "Office Supplies",
            "default_payment_method": cash_mode,
            "default_cost_center": default_cost_center,
            "categories": category_rows,
            "payment_methods": payment_methods,
        }
    ).insert(ignore_permissions=True)
    created.append("Office Expense Settings")
    return created


def _get_or_create_root_account(
    company: str, account_name: str, root_type: str, created: list[str]
) -> str:
    roots = frappe.get_all(
        "Account",
        filters={"company": company, "root_type": root_type, "is_group": 1, "disabled": 0},
        fields=["name", "parent_account"],
        order_by="lft asc",
    )
    root = next((row.name for row in roots if not row.parent_account), None)
    if root:
        return root
    return _get_or_create_account(
        company, account_name, None, root_type, is_group=True, created=created
    )


def _get_or_create_account(
    company: str,
    account_name: str,
    parent_account: str | None,
    root_type: str,
    *,
    is_group: bool,
    created: list[str],
    account_type: str | None = None,
) -> str:
    existing = _matching_account(company, account_name, root_type, is_group, account_type)
    if existing:
        return existing
    # Do not wire a category to an unrelated ledger that happens to use the
    # same label in a custom chart of accounts.
    if frappe.db.exists("Account", {"company": company, "account_name": account_name}):
        account_name = f"{account_name} - Distribution"
        existing = _matching_account(company, account_name, root_type, is_group, account_type)
        if existing:
            return existing
    values = {
        "doctype": "Account",
        "account_name": account_name,
        "company": company,
        "root_type": root_type,
        "is_group": 1 if is_group else 0,
    }
    if parent_account:
        values["parent_account"] = parent_account
    if account_type:
        values["account_type"] = account_type
    account = frappe.get_doc(values)
    account.insert(ignore_permissions=True)
    created.append(f"Account: {account.name}")
    return account.name


def _matching_account(
    company: str,
    account_name: str,
    root_type: str,
    is_group: bool,
    account_type: str | None,
) -> str | None:
    account = frappe.db.get_value(
        "Account",
        {"company": company, "account_name": account_name},
        ["name", "root_type", "is_group", "disabled", "account_type"],
        as_dict=True,
    )
    if not account or account.disabled:
        return None
    if account.root_type != root_type or bool(cint(account.is_group)) != is_group:
        return None
    if account_type and account.account_type != account_type:
        return None
    return account.name


def _get_or_create_cost_center(company: str, created: list[str]) -> str:
    existing = frappe.db.get_value(
        "Cost Center",
        {"company": company, "is_group": 0, "disabled": 0},
        "name",
        order_by="lft asc",
    )
    if existing:
        return existing
    cost_center = frappe.get_doc(
        {"doctype": "Cost Center", "cost_center_name": "Main", "company": company, "is_group": 0}
    )
    cost_center.insert(ignore_permissions=True)
    created.append(f"Cost Center: {cost_center.name}")
    return cost_center.name


def _get_or_create_cash_account(company: str, created: list[str]) -> str:
    cash_account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Cash", "is_group": 0, "disabled": 0},
        "name",
        order_by="lft asc",
    )
    if cash_account:
        return cash_account
    asset_root = _get_or_create_root_account(company, "Assets", "Asset", created)
    cash_group = _get_or_create_account(
        company, "Cash", asset_root, "Asset", is_group=True, created=created
    )
    return _get_or_create_account(
        company,
        "Office Cash",
        cash_group,
        "Asset",
        is_group=False,
        account_type="Cash",
        created=created,
    )


def _get_or_create_cash_mode_of_payment(created: list[str]) -> str:
    if frappe.db.exists("Mode of Payment", "Cash"):
        return "Cash"
    mode = frappe.get_doc(
        {"doctype": "Mode of Payment", "mode_of_payment": "Cash", "type": "Cash", "enabled": 1}
    )
    mode.insert(ignore_permissions=True)
    created.append("Mode of Payment: Cash")
    return mode.name
