from __future__ import annotations

import frappe


def get_context(context):
    context.no_cache = 1
    context.title = "Reckon ERP Signup"
    context.plans = frappe.get_all(
        "SaaS Plan",
        filters={"enabled": 1},
        fields=["name", "plan_name", "plan_version", "price", "currency", "billing_cycle", "features"],
        order_by="price asc",
        ignore_permissions=True,
    )
    return context
