from __future__ import annotations

import frappe

from reckon_distribution.constants import OPERATIONAL_ROLES


def check_app_permission() -> bool:
    if frappe.session.user == "Administrator":
        return True

    roles = set(frappe.get_roles(frappe.session.user))
    return any(role.name in roles for role in OPERATIONAL_ROLES)
