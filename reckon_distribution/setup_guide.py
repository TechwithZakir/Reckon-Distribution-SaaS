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
        if not frappe.db.exists("DocType", doctype):
            return 0
        return frappe.db.count(doctype, filters)

    return {
        "company": tenant.company,
        "settings": count("Distribution Settings", {"company": tenant.company}),
        "users": count("Tenant User Assignment", {"company": tenant.company, "active": 1}),
        "routes": count("Distribution Route", {"company": tenant.company, "active": 1}),
        "retailers": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Customer", "active": 1}),
        "suppliers": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Supplier", "active": 1}),
        "products": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Item", "active": 1}),
        "prices": count("Distribution Master Scope", {"company": tenant.company, "master_type": "Price List", "active": 1}),
        "assignments": count("Retailer Route Assignment", {"company": tenant.company, "active": 1}),
        "records": {
            "routes": frappe.db.sql("select name, route_code, route_name, assigned_user from `tabDistribution Route` where company=%s order by route_name", tenant.company, as_dict=True),
            "retailers": frappe.db.sql("select s.master_name as name, c.customer_name, c.customer_group, c.territory from `tabDistribution Master Scope` s left join `tabCustomer` c on c.name=s.master_name where s.company=%s and s.master_type='Customer' and s.active=1 order by c.customer_name, s.master_name", tenant.company, as_dict=True),
            "assignments_list": frappe.db.sql("select name, customer, route, assigned_user, active from `tabRetailer Route Assignment` where company=%s order by customer", tenant.company, as_dict=True),
            "products": frappe.db.sql("select s.master_name as name, i.item_name, i.stock_uom from `tabDistribution Master Scope` s left join `tabItem` i on i.name=s.master_name where s.company=%s and s.master_type='Item' and s.active=1 order by i.item_name, s.master_name", tenant.company, as_dict=True),
        },
    }


@frappe.whitelist()
def get_setup_links(company: str) -> dict:
    """Return only linked values visible inside the selected Company."""
    tenant = require_tenant(company=company)
    users = frappe.db.sql(
        """select distinct a.user, coalesce(u.full_name, a.user) as full_name
        from `tabTenant User Assignment` a left join `tabUser` u on u.name=a.user
        where a.company=%s and a.active=1 order by full_name, a.user""",
        tenant.company,
        as_dict=True,
    )
    return {
        "users": users,
        "routes": frappe.get_all("Distribution Route", filters={"company": tenant.company, "active": 1}, fields=["name", "route_name"], order_by="route_name asc"),
        "customers": frappe.db.sql("select s.master_name as name, coalesce(c.customer_name, s.master_name) as customer_name from `tabDistribution Master Scope` s left join `tabCustomer` c on c.name=s.master_name where s.company=%s and s.master_type='Customer' and s.active=1 order by customer_name", tenant.company, as_dict=True),
        "items": frappe.db.sql("select s.master_name as name, coalesce(i.item_name, s.master_name) as item_name from `tabDistribution Master Scope` s left join `tabItem` i on i.name=s.master_name where s.company=%s and s.master_type='Item' and s.active=1 order by item_name", tenant.company, as_dict=True),
        "uoms": frappe.get_all("UOM", fields=["name"], order_by="name asc"),
        "price_lists": frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, fields=["name", "price_list_name"], order_by="price_list_name asc"),
        "payment_terms": frappe.get_all("Payment Terms Template", fields=["name", "template_name"], order_by="template_name asc"),
        "warehouses": frappe.get_all("Warehouse", filters={"company": tenant.company, "is_group": 0, "disabled": 0}, fields=["name", "warehouse_name"], order_by="warehouse_name asc"),
        "accounts": frappe.get_all("Account", filters={"company": tenant.company, "is_group": 0, "disabled": 0}, fields=["name", "account_name", "account_type"], order_by="account_name asc"),
        "customer_groups": frappe.get_all("Customer Group", fields=["name"], order_by="name asc"),
        "territories": frappe.get_all("Territory", fields=["name"], order_by="name asc"),
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
    if data.get("default_price_list"):
        _scope(tenant.company, "Price List", data["default_price_list"])
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
    doc = frappe.get_doc("Distribution Route", data["name"]) if data.get("name") else frappe.get_doc({"doctype": "Distribution Route", "company": tenant.company})
    if data.get("name") and doc.company != tenant.company:
        frappe.throw(_("This route belongs to another Company."), frappe.PermissionError)
    doc.update({"company": tenant.company, "route_code": code, "route_name": name, "assigned_user": assigned_user, "active": 1})
    doc.save() if doc.name else doc.insert()
    return doc.name


@frappe.whitelist()
def create_retailer(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    name = cstr(data.get("customer_name")).strip()
    if not name:
        frappe.throw(_("Retailer name is required."))
    customer = frappe.get_doc("Customer", data["name"]) if data.get("name") else frappe.get_doc({"doctype": "Customer"})
    if data.get("name"):
        _assert_company_master(tenant.company, "Customer", customer.name)
    customer.update({"customer_name": name, "customer_type": "Company", "customer_group": data.get("customer_group") or "All Customer Groups", "territory": data.get("territory") or "All Territories"})
    customer.save(ignore_permissions=True) if customer.name else customer.insert(ignore_permissions=True)
    _scope(tenant.company, "Customer", customer.name)
    return customer.name


@frappe.whitelist()
def create_supplier(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    supplier_name = cstr(data.get("supplier_name")).strip()
    if not supplier_name:
        frappe.throw(_("Supplier name is required."))
    supplier = frappe.get_doc("Supplier", data["name"]) if data.get("name") else frappe.get_doc({"doctype": "Supplier"})
    if data.get("name"):
        _assert_company_master(tenant.company, "Supplier", supplier.name)
    supplier.update({"supplier_name": supplier_name, "supplier_group": data.get("supplier_group") or "All Supplier Groups", "supplier_type": data.get("supplier_type") or "Company"})
    supplier.save(ignore_permissions=True) if supplier.name else supplier.insert(ignore_permissions=True)
    _scope(tenant.company, "Supplier", supplier.name)
    return supplier.name


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
    doc = frappe.get_doc("Retailer Route Assignment", data["name"]) if data.get("name") else frappe.get_doc({"doctype": "Retailer Route Assignment"})
    if data.get("name") and doc.company != tenant.company:
        frappe.throw(_("This assignment belongs to another Company."), frappe.PermissionError)
    doc.update({"company": tenant.company, "customer": data["customer"], "route": route.name, "assigned_user": data["assigned_user"], "effective_from": data.get("effective_from") or nowdate(), "effective_to": data.get("effective_to") or "2099-12-31", "active": 1})
    doc.save() if doc.name else doc.insert()
    return doc.name


@frappe.whitelist()
def create_product(payload: str | dict) -> dict:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    item_name = cstr(data.get("item_name")).strip()
    uom = cstr(data.get("uom")).strip()
    price = data.get("price")
    if not item_name or not uom:
        frappe.throw(_("Product name and sales unit are required."))
    if not frappe.db.exists("UOM", uom):
        frappe.throw(_("Sales unit {0} does not exist in ERPNext.").format(uom))
    item = frappe.get_doc("Item", data["name"]) if data.get("name") else frappe.get_doc({"doctype": "Item", "item_code": item_name})
    if data.get("name"):
        _assert_company_master(tenant.company, "Item", item.name)
    item.update({"item_code": item_name, "item_name": item_name, "stock_uom": uom, "is_stock_item": 1})
    item.save(ignore_permissions=True) if item.name else item.insert(ignore_permissions=True)
    _scope(tenant.company, "Item", item.name)
    if price not in (None, ""):
        price_list = data.get("price_list") or _default_price_list(tenant.company)
        if not price_list:
            price_list_doc = frappe.get_doc({"doctype": "Price List", "price_list_name": f"{tenant.company} Sales", "selling": 1, "buying": 0, "currency": "BDT"})
            price_list_doc.insert(ignore_permissions=True)
            price_list = price_list_doc.name
        item_price_name = frappe.db.exists("Item Price", {"item_code": item.name, "price_list": price_list, "uom": uom, "selling": 1})
        item_price = frappe.get_doc("Item Price", item_price_name) if item_price_name else frappe.get_doc({"doctype": "Item Price"})
        item_price.update({"item_code": item.name, "price_list": price_list, "uom": uom, "price_list_rate": price, "selling": 1})
        item_price.save(ignore_permissions=True) if item_price.name else item_price.insert(ignore_permissions=True)
        _scope(tenant.company, "Price List", price_list)
        _scope(tenant.company, "Item Price", item_price.name)
    return {"item": item.name}


@frappe.whitelist()
def create_price(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    _require_manager()
    item = cstr(data.get("item")).strip()
    price_list = cstr(data.get("price_list")).strip()
    uom = cstr(data.get("uom")).strip()
    if not item or not price_list or not uom or data.get("rate") in (None, ""):
        frappe.throw(_("Product, price list, sales unit and selling price are required."))
    _assert_company_master(tenant.company, "Item", item)
    _scope(tenant.company, "Price List", price_list)
    _assert_company_master(tenant.company, "Price List", price_list)
    item_price_name = frappe.db.exists("Item Price", {"item_code": item, "price_list": price_list, "uom": uom, "selling": 1})
    item_price = frappe.get_doc("Item Price", item_price_name) if item_price_name else frappe.get_doc({"doctype": "Item Price"})
    item_price.update({"item_code": item, "price_list": price_list, "uom": uom, "price_list_rate": data["rate"], "selling": 1})
    item_price.save(ignore_permissions=True) if item_price.name else item_price.insert(ignore_permissions=True)
    _scope(tenant.company, "Item Price", item_price.name)
    return item_price.name


@frappe.whitelist()
def remove_setup_entry(company: str, entry_type: str, name: str) -> str:
    tenant = require_tenant(company=company)
    _require_manager()
    if entry_type == "route":
        doc = frappe.get_doc("Distribution Route", name)
        if doc.company != tenant.company:
            frappe.throw(_("This route belongs to another Company."), frappe.PermissionError)
        doc.delete()
    elif entry_type == "assignment":
        doc = frappe.get_doc("Retailer Route Assignment", name)
        if doc.company != tenant.company:
            frappe.throw(_("This assignment belongs to another Company."), frappe.PermissionError)
        doc.delete()
    elif entry_type in {"retailer", "product"}:
        master_type = "Customer" if entry_type == "retailer" else "Item"
        scope = frappe.db.exists("Distribution Master Scope", {"company": tenant.company, "master_type": master_type, "master_name": name})
        if scope:
            frappe.delete_doc("Distribution Master Scope", scope)
    else:
        frappe.throw(_("Unsupported setup record."))
    return name


def _scope(company: str, master_type: str, master_name: str) -> None:
    if not frappe.db.exists("Distribution Master Scope", {"company": company, "master_type": master_type, "master_name": master_name}):
        frappe.get_doc({"doctype": "Distribution Master Scope", "company": company, "master_type": master_type, "master_name": master_name, "access_scope": "Read", "active": 1}).insert(ignore_permissions=True)


def _assert_exclusive_master(company: str, master_type: str, master_name: str) -> None:
    companies = frappe.db.count("Distribution Master Scope", {"master_type": master_type, "master_name": master_name, "active": 1})
    if companies > 1:
        frappe.throw(_("This shared {0} is used by more than one Company. Create a new master instead of editing it here.").format(master_type), frappe.PermissionError)


def _assert_company_master(company: str, master_type: str, master_name: str) -> None:
    if not frappe.db.exists("Distribution Master Scope", {"company": company, "master_type": master_type, "master_name": master_name, "active": 1}):
        frappe.throw(_("This {0} is not enabled for the selected Company.").format(master_type), frappe.PermissionError)
    _assert_exclusive_master(company, master_type, master_name)


def _default_price_list(company: str) -> str | None:
    return frappe.db.get_value("Distribution Settings", {"company": company}, "default_price_list")


def _payload(payload: str | dict) -> dict:
    return frappe.parse_json(payload) if isinstance(payload, str) else payload


def _require_manager() -> None:
    if user_can_bypass_tenant() or {"Reckon Distribution Admin", "Reckon Distribution Manager"}.intersection(frappe.get_roles()):
        return
    frappe.throw(_("Company Admin or Company Manager access is required."), frappe.PermissionError)
