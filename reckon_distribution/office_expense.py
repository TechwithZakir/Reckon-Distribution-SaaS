from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant


def validate_office_expense_settings(doc: Document) -> None:
    """Validate the Company-owned mappings that hide accounting from users."""
    _require_company(doc.company)
    categories = _category_map(doc)
    payment_methods = _payment_method_map(doc)

    if doc.default_expense_category not in categories:
        frappe.throw(_("Default Expense Category must be an enabled category in this setup."))
    if doc.default_payment_method not in payment_methods:
        frappe.throw(_("Default Paid By must be an enabled payment method in this setup."))
    _validate_cost_center(doc.company, doc.default_cost_center)

    for category, row in categories.items():
        _validate_expense_account(doc.company, row.expense_account, category)
    for payment_method, row in payment_methods.items():
        _validate_payment_account(doc.company, row.payment_account, payment_method)


def validate_office_expense(doc: Document) -> None:
    """Resolve friendly choices to Company accounts and prepare a balanced posting."""
    if not doc.company:
        if user_can_bypass_tenant():
            frappe.throw(_("Company is required before recording an expense."))
        doc.company = require_tenant().company
    _require_company(doc.company)
    settings = _get_settings(doc.company)
    categories = _category_map(settings)
    payment_methods = _payment_method_map(settings)

    if not doc.payment_method:
        doc.payment_method = settings.default_payment_method
    payment_setup = payment_methods.get(doc.payment_method)
    if not payment_setup:
        frappe.throw(
            _("Paid By {0} is not enabled in Office Expense Setup.").format(
                doc.payment_method or _("selected payment method")
            )
        )

    doc.payment_account = payment_setup.payment_account
    doc.cost_center = settings.default_cost_center
    _validate_payment_account(doc.company, doc.payment_account, doc.payment_method)
    _validate_cost_center(doc.company, doc.cost_center)

    total = 0.0
    if not doc.items:
        frappe.throw(_("Add at least one expense item."))
    for row in doc.items:
        if not row.expense_category:
            row.expense_category = settings.default_expense_category
        category_setup = categories.get(row.expense_category)
        if not category_setup:
            frappe.throw(
                _("Expense Category {0} is not enabled in Office Expense Setup.").format(
                    row.expense_category or _("selected category")
                )
            )
        if not row.description or not row.description.strip():
            frappe.throw(_("Enter a description for expense row {0}.").format(row.idx))
        if flt(row.amount) <= 0:
            frappe.throw(_("Expense amount in row {0} must be greater than zero.").format(row.idx))
        row.expense_account = category_setup.expense_account
        row.cost_center = doc.cost_center
        _validate_expense_account(doc.company, row.expense_account, row.expense_category)
        total += flt(row.amount)

    doc.total_amount = total
    doc.status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(doc.docstatus, "Draft")


def create_office_expense_payment_entry(doc: Document) -> None:
    """Post a controlled Pay Payment Entry after an office expense is submitted."""
    if doc.payment_entry:
        existing = frappe.get_doc("Payment Entry", doc.payment_entry)
        if existing.docstatus == 1:
            return
        frappe.throw(_("The linked accounting voucher must be submitted before this expense can continue."))

    payment_entry = frappe.get_doc(
        {
            "doctype": "Payment Entry",
            "payment_type": "Pay",
            "company": doc.company,
            "posting_date": doc.posting_date,
            "mode_of_payment": doc.payment_method,
            # This is an internal, no-party cash/bank payment. The overridden
            # controller permits it only when it is linked to this Office Expense.
            "paid_from": doc.payment_account,
            "paid_to": doc.payment_account,
            "paid_amount": flt(doc.total_amount),
            "received_amount": flt(doc.total_amount),
            "cost_center": doc.cost_center,
            "reference_no": doc.reference_no or doc.name,
            "reference_date": doc.reference_date or doc.posting_date,
            "custom_remarks": 1,
            "remarks": _("Office Expense {0} paid to {1}").format(doc.name, doc.payee),
            "rd_office_expense": doc.name,
            "deductions": [
                {
                    "account": row.expense_account,
                    "amount": flt(row.amount),
                    "cost_center": row.cost_center,
                }
                for row in doc.items
            ],
        }
    )
    payment_entry.flags.reckon_office_expense_payment = True
    payment_entry.flags.ignore_permissions = True
    payment_entry.insert(ignore_permissions=True)
    # Persist the ownership link before submit. This lets the narrowly scoped
    # controller exception apply on submit and later cancellation as well.
    doc.db_set("payment_entry", payment_entry.name, update_modified=False)
    payment_entry.flags.ignore_permissions = True
    payment_entry.submit()
    doc.db_set("status", "Submitted", update_modified=False)


def cancel_office_expense_payment_entry(doc: Document) -> None:
    """Cancel the generated Payment Entry, retaining support for legacy vouchers."""
    if doc.payment_entry and frappe.db.exists("Payment Entry", doc.payment_entry):
        payment_entry = frappe.get_doc("Payment Entry", doc.payment_entry)
        if payment_entry.docstatus == 1:
            payment_entry.flags.ignore_permissions = True
            payment_entry.cancel()
    elif doc.journal_entry and frappe.db.exists("Journal Entry", doc.journal_entry):
        journal_entry = frappe.get_doc("Journal Entry", doc.journal_entry)
        if journal_entry.docstatus == 1:
            journal_entry.flags.ignore_permissions = True
            journal_entry.cancel()
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist()
def get_office_expense_defaults() -> dict:
    """Return only friendly choices for the simplified expense form."""
    tenant = require_tenant()
    if not frappe.db.exists("Office Expense Settings", tenant.company):
        return {"configured": False, "company": tenant.company}

    settings = frappe.get_doc("Office Expense Settings", tenant.company)
    return {
        "configured": True,
        "company": tenant.company,
        "default_expense_category": settings.default_expense_category,
        "default_payment_method": settings.default_payment_method,
        "categories": sorted(_category_map(settings)),
        "payment_methods": sorted(_payment_method_map(settings)),
    }


def _get_settings(company: str) -> Document:
    if not frappe.db.exists("Office Expense Settings", company):
        frappe.throw(_("Office Expense Setup is required before recording an expense."))
    return frappe.get_doc("Office Expense Settings", company)


def _category_map(settings: Document) -> dict[str, Document]:
    categories: dict[str, Document] = {}
    for row in settings.categories:
        category = (row.category or "").strip()
        if not category or not row.enabled:
            continue
        if category in categories:
            frappe.throw(_("Expense Category {0} is configured more than once.").format(category))
        categories[category] = row
    return categories


def _payment_method_map(settings: Document) -> dict[str, Document]:
    payment_methods: dict[str, Document] = {}
    for row in settings.payment_methods:
        payment_method = row.payment_method
        if not payment_method or not row.enabled:
            continue
        if payment_method in payment_methods:
            frappe.throw(_("Paid By {0} is configured more than once.").format(payment_method))
        payment_methods[payment_method] = row
    return payment_methods


def _require_company(company: str) -> None:
    if not company:
        frappe.throw(_("Company is required before recording an expense."))
    if not user_can_bypass_tenant():
        require_tenant(company=company)


def _validate_expense_account(company: str, account_name: str, category: str) -> None:
    account = _get_account(company, account_name, category)
    if account.root_type != "Expense":
        frappe.throw(_("The account configured for {0} must be an expense account.").format(category))


def _validate_payment_account(company: str, account_name: str, payment_method: str) -> None:
    account = _get_account(company, account_name, payment_method)
    if account.account_type not in {"Cash", "Bank"}:
        frappe.throw(
            _("The payment account configured for {0} must be Cash or Bank.").format(
                payment_method
            )
        )


def _get_account(company: str, account_name: str, label: str):
    account = frappe.db.get_value(
        "Account",
        account_name,
        ["company", "is_group", "disabled", "root_type", "account_type"],
        as_dict=True,
    )
    if not account or account.company != company:
        frappe.throw(_("Account setup for {0} must belong to the selected Company.").format(label))
    if account.is_group or account.disabled:
        frappe.throw(_("Account setup for {0} must be an active ledger account.").format(label))
    return account


def _validate_cost_center(company: str, cost_center_name: str) -> None:
    cost_center = frappe.db.get_value(
        "Cost Center", cost_center_name, ["company", "is_group", "disabled"], as_dict=True
    )
    if not cost_center or cost_center.company != company:
        frappe.throw(_("Default Cost Center must belong to the selected Company."))
    if cost_center.is_group or cost_center.disabled:
        frappe.throw(_("Default Cost Center must be an active ledger cost center."))
