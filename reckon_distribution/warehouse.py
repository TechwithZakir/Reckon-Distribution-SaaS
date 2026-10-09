from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant


def validate_warehouse(doc, method=None) -> None:
    """Keep native ERPNext Warehouse records inside the active tenant Company."""
    if user_can_bypass_tenant():
        return

    tenant = require_tenant()
    if not doc.company:
        doc.company = tenant.company
    if doc.company != tenant.company:
        frappe.throw(
            _("This Distribution Warehouse must belong to your Company: {0}.").format(tenant.company),
            frappe.PermissionError,
        )
