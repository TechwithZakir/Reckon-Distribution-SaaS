from __future__ import annotations

import frappe

from reckon_saas_platform.saas import get_vendor_saas_summary
from reckon_saas_platform.saas_security import is_vendor_user


def get_context(context):
    if not is_vendor_user():
        frappe.throw("Not permitted", frappe.PermissionError)

    context.no_cache = 1
    context.title = "SaaS Admin"
    context.summary = frappe._dict(get_vendor_saas_summary())
    context.pending_payments = frappe.get_all(
        "SaaS Payment",
        filters={"status": "Pending Verification"},
        fields=["name", "company", "amount", "currency", "gateway_reference", "subscription"],
        ignore_permissions=True,
    )
    context.seed_jobs = frappe.get_all(
        "Tenant Provisioning Job",
        fields=["name", "company", "seed_version", "status", "current_step", "error"],
        ignore_permissions=True,
        order_by="modified desc",
        limit=20,
    )
    return context
