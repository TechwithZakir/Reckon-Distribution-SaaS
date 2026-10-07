from __future__ import annotations

import frappe

from reckon_distribution.tenant_security import (
    get_user_companies,
    require_tenant,
    user_can_bypass_tenant,
)


@frappe.whitelist()
def get_setup_companies() -> list[dict]:
    if user_can_bypass_tenant():
        return frappe.get_all("Company", fields=["name"], order_by="name asc")
    return [{"name": company} for company in get_user_companies()]


@frappe.whitelist()
def get_setup_status(company: str) -> dict:
    tenant = require_tenant(company=company)
    def count(doctype: str, filters: dict) -> int:
        return frappe.db.count(doctype, filters)

    return {
        "company": tenant.company,
        "settings": count("Distribution Settings", {"company": tenant.company}),
        "routes": count("Distribution Route", {"company": tenant.company, "active": 1}),
        "retailers": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Customer", "active": 1}),
        "products": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Item", "active": 1}),
        "prices": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Price List", "active": 1}),
        "assignments": count("Retailer Route Assignment", {"company": tenant.company, "active": 1}),
    }
