from __future__ import annotations

import frappe


def run_distribution_seed(company: str, seed_version: str) -> dict:
    """Seed additive distribution defaults for a tenant company.

    Business data such as Item, Customer, Supplier, prices, balances, contacts,
    and stock must never be cloned from another tenant.
    """
    if not frappe.db.exists("Company", company):
        frappe.throw(frappe._("Company {0} does not exist.").format(company))

    created = []
    if not frappe.db.exists("Distribution Settings", company):
        frappe.get_doc(
            {
                "doctype": "Distribution Settings",
                "company": company,
                "supplier_goods_policy": "Supplier Provided Goods Only",
                "allow_batch_expiry": 1,
            }
        ).insert(ignore_permissions=True)
        created.append("Distribution Settings")

    if not frappe.db.exists("Company UOM Profile", company):
        frappe.get_doc(
            {
                "doctype": "Company UOM Profile",
                "company": company,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        created.append("Company UOM Profile")

    return {
        "company": company,
        "seed_version": seed_version,
        "status": "complete",
        "created": created,
        "preserved_existing_data": True,
    }
