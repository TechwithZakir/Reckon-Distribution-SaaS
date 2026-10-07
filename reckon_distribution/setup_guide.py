from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, nowdate

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
        "users": count("Tenant User Assignment", {"company": tenant.company, "active": 1}),
        "routes": count("Distribution Route", {"company": tenant.company, "active": 1}),
        "retailers": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Customer", "active": 1}),
        "products": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Item", "active": 1}),
        "prices": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Price List", "active": 1}),
        "assignments": count("Retailer Route Assignment", {"company": tenant.company, "active": 1}),
    }


@frappe.whitelist()
def save_company_settings(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    values = {
        "company": tenant.company,
        "supplier_goods_policy": "Supplier Provided Goods Only",
        "default_warehouse": data.get("default_warehouse"),
        "default_price_list": data.get("default_price_list"),
        "default_receivable_account": data.get("default_receivable_account"),
        "default_cash_account": data.get("default_cash_account"),
    }
    existing = frappe.db.exists("Distribution Settings", {"company": tenant.company})
    doc = frappe.get_doc("Distribution Settings", existing) if existing else frappe.get_doc({"doctype": "Distribution Settings"})
    doc.update(values)
    doc.save(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def create_route(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    code = cstr(data.get("route_code")).strip()
    name = cstr(data.get("route_name")).strip()
    assigned_user = cstr(data.get("assigned_user")).strip()
    if not code or not name or not assigned_user:
        frappe.throw(_("Route name, code, and field user are required."))
    doc = frappe.get_doc({"doctype": "Distribution Route", "company": tenant.company, "route_code": code, "route_name": name, "assigned_user": assigned_user, "active": 1})
    doc.insert()
    return doc.name


@frappe.whitelist()
def create_retailer(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    name = cstr(data.get("customer_name")).strip()
    if not name:
        frappe.throw(_("Retailer name is required."))
    customer = frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company", "customer_group": data.get("customer_group") or "All Customer Groups", "territory": data.get("territory") or "All Territories"})
    customer.insert(ignore_permissions=True)
    _scope(tenant.company, "Customer", customer.name)
    return customer.name


@frappe.whitelist()
def assign_retailer(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    route = frappe.get_doc("Distribution Route", data.get("route"))
    if route.company != tenant.company:
        frappe.throw(_("Route does not belong to this Company."))
    if not data.get("customer") or not data.get("assigned_user"):
        frappe.throw(_("Retailer, route, and field user are required."))
    doc = frappe.get_doc({"doctype": "Retailer Route Assignment", "company": tenant.company, "customer": data["customer"], "route": route.name, "assigned_user": data["assigned_user"], "effective_from": data.get("effective_from") or nowdate(), "effective_to": data.get("effective_to") or "2099-12-31", "active": 1})
    doc.insert()
    return doc.name


@frappe.whitelist()
def create_product(payload: str | dict) -> dict:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    item_name = cstr(data.get("item_name")).strip()
    uom = cstr(data.get("uom")).strip()
    price = data.get("price")
    if not item_name or not uom or price in (None, ""):
        frappe.throw(_("Product name, sales unit, and price are required."))
    if not frappe.db.exists("UOM", uom):
        frappe.throw(_("Sales unit {0} does not exist in ERPNext.").format(uom))
    item = frappe.get_doc({"doctype": "Item", "item_code": item_name, "item_name": item_name, "stock_uom": uom, "is_stock_item": 1})
    item.insert(ignore_permissions=True)
    price_list = data.get("price_list") or _default_price_list(tenant.company)
    if not price_list:
        price_list_doc = frappe.get_doc({"doctype": "Price List", "price_list_name": f"{tenant.company} Sales", "selling": 1, "buying": 0, "currency": "BDT"})
        price_list_doc.insert(ignore_permissions=True)
        price_list = price_list_doc.name
    item_price = frappe.get_doc({"doctype": "Item Price", "item_code": item.name, "price_list": price_list, "uom": uom, "price_list_rate": price, "selling": 1})
    item_price.insert(ignore_permissions=True)
    _scope(tenant.company, "Item", item.name)
    _scope(tenant.company, "Price List", price_list)
    _scope(tenant.company, "Item Price", item_price.name)
    return {"item": item.name, "price_list": price_list}


def _scope(company: str, master_type: str, master_name: str) -> None:
    if not frappe.db.exists("Distribution Master Scope", {"company": company, "master_type": master_type, "master_name": master_name}):
        frappe.get_doc({"doctype": "Distribution Master Scope", "company": company, "master_type": master_type, "master_name": master_name, "access_scope": "Read", "active": 1}).insert(ignore_permissions=True)


def _default_price_list(company: str) -> str | None:
    return frappe.db.get_value("Distribution Settings", {"company": company}, "default_price_list")


def _payload(payload: str | dict) -> dict:
    return frappe.parse_json(payload) if isinstance(payload, str) else payload


def _require_manager() -> None:
    if user_can_bypass_tenant() or {"Reckon Distribution Admin", "Reckon Distribution Manager"}.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Company Admin or Company Manager access is required."), frappe.PermissionError)
