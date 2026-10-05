from __future__ import annotations

import frappe

from reckon_distribution.api import check_app_permission


def get_context(context):
    if frappe.session.user == "Guest" or not check_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)

    context.no_cache = 1
    context.show_sidebar = False
    context.title = "Distribution"
    return context
