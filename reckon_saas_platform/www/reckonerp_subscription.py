from __future__ import annotations

import frappe

from reckon_saas_platform.saas import get_subscription_summary
from reckon_saas_platform.tenant_security import TenantResolutionError


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect

    context.no_cache = 1
    context.title = "Subscription and Payment"
    try:
        context.summary = frappe._dict(get_subscription_summary())
    except TenantResolutionError:
        context.summary = frappe._dict({"status": "Missing", "company": ""})
    return context
