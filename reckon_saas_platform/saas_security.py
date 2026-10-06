from __future__ import annotations

import frappe


def is_vendor_user(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return "Reckon Vendor Superuser" in frappe.get_roles(user) or "System Manager" in frappe.get_roles(user)


def get_vendor_only_query(user: str | None = None) -> str:
    return "" if is_vendor_user(user) else "1 = 0"


def has_vendor_only_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    return is_vendor_user(user)
