"""Company context for Distribution forms; no global Desk customization."""
import frappe
from frappe import _

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant

DIRECT_RATE_PURCHASE_DOCTYPES = frozenset(
    {"Purchase Order", "Purchase Receipt", "Purchase Invoice"}
)


@frappe.whitelist()
def get_form_company():
    if user_can_bypass_tenant():
        return {"restricted": False}
    return {"restricted": True, "company": require_tenant().company}


def bind_form_company(doc, method=None):
    prepare_direct_rate_purchase_document(doc)
    if user_can_bypass_tenant():
        return
    company = require_tenant().company
    field = "rd_company" if doc.meta.has_field("rd_company") else "company"
    if not doc.meta.has_field(field):
        return
    if doc.get(field) and doc.get(field) != company:
        frappe.throw(_("This document belongs to another Company."), frappe.PermissionError)
    if not doc.is_new() and frappe.db.get_value(doc.doctype, doc.name, field) != company:
        frappe.throw(_("This document is not owned by your Company."), frappe.PermissionError)
    doc.set(field, company)


def prepare_direct_rate_purchase_document(doc, method=None):
    """Keep simplified procurement independent of ERPNext buying price lists."""
    if doc.doctype not in DIRECT_RATE_PURCHASE_DOCTYPES or doc.get("docstatus") != 0:
        return

    # Procurement rates are entered on the transaction rows. ERPNext may prefill
    # its global Standard Buying list, which is intentionally outside tenant scope.
    doc.update(
        {
            "buying_price_list": None,
            "price_list_currency": None,
            "plc_conversion_rate": 1,
            "ignore_pricing_rule": 1,
        }
    )
