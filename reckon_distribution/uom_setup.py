from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import require_tenant, user_can_bypass_tenant


@frappe.whitelist()
def get_uom_setup(company: str, item: str | None = None) -> dict:
    tenant = require_tenant(company=company)
    items = frappe.get_all(
        "Item",
        filters={"name": ["in", _scoped_items(tenant.company)]},
        fields=["name", "item_name", "stock_uom"],
        order_by="item_name asc",
    )
    units = _enabled_units(tenant.company)
    selected = None
    if item:
        validate_master_scope(tenant.company, "Item", item)
        selected = frappe.get_doc("Item", item)
    return {
        "company": tenant.company,
        "items": items,
        "units": units,
        "item": {
            "name": selected.name,
            "item_name": selected.item_name,
            "stock_uom": selected.stock_uom,
            "uoms": [{"uom": row.uom, "conversion_factor": row.conversion_factor} for row in selected.uoms],
        } if selected else None,
    }


@frappe.whitelist()
def save_uom_setup(company: str, item: str, rows: str | list[dict]) -> dict:
    tenant = require_tenant(company=company)
    validate_master_scope(tenant.company, "Item", item)
    if not _can_manage():
        frappe.throw(_("You do not have permission to change item units."), frappe.PermissionError)
    doc = frappe.get_doc("Item", item)
    data = json.loads(rows) if isinstance(rows, str) else rows
    seen = set()
    allowed = set(_enabled_units(tenant.company))
    for row in data:
        uom = str(row.get("uom") or "").strip()
        factor = flt(row.get("conversion_factor"))
        if not uom or uom == doc.stock_uom:
            frappe.throw(_("Choose a different sales unit from the stock unit."))
        if uom in seen:
            frappe.throw(_("UOM {0} is repeated.").format(uom))
        if uom not in allowed:
            frappe.throw(_("UOM {0} is not enabled for this Company.").format(uom))
        if factor <= 0:
            frappe.throw(_("Conversion factor for {0} must be greater than zero.").format(uom))
        seen.add(uom)
    doc.set("uoms", [])
    for row in data:
        doc.append("uoms", {"uom": row["uom"].strip(), "conversion_factor": flt(row["conversion_factor"])})
    doc.save()
    return {"item": doc.name, "uoms": [{"uom": row.uom, "conversion_factor": row.conversion_factor} for row in doc.uoms]}


def _scoped_items(company: str) -> list[str]:
    return frappe.get_all("Distribution Master Scope", filters={"company": company, "master_type": "Item", "active": 1}, pluck="master_name") or [""]


def _enabled_units(company: str) -> list[str]:
    profile = frappe.db.get_value("Distribution Settings", {"company": company}, "default_uom_profile")
    if not profile:
        profile = frappe.db.get_value("Company UOM Profile", {"company": company, "enabled": 1}, "name")
    if profile:
        return frappe.get_all("Company UOM Profile Item", filters={"parent": profile, "allow_sales": 1}, pluck="uom")
    return frappe.get_all("UOM", pluck="name", order_by="name asc")


def _can_manage() -> bool:
    if user_can_bypass_tenant():
        return True
    return bool(set(frappe.get_roles()) & {"Reckon Distribution Admin", "Reckon Distribution Manager", "Reckon Master Data Manager"})
