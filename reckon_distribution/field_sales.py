from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import nowdate

from reckon_distribution.master_data import (
    get_or_create_company_sales_price_list,
    validate_master_scope,
)
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    get_user_companies,
    require_tenant,
    user_can_bypass_tenant,
)


@frappe.whitelist()
def get_assigned_outlets(route: str | None = None, txt: str = "") -> list[dict]:
    if user_can_bypass_tenant() and len(get_user_companies()) != 1:
        return []
    tenant = require_tenant()
    filters = {
        "company": tenant.company,
        "assigned_user": frappe.session.user,
        "active": 1,
        "effective_from": ["<=", nowdate()],
        "effective_to": [">=", nowdate()],
    }
    if route:
        filters["route"] = route
    rows = frappe.get_all(
        "Retailer Route Assignment",
        filters=filters,
        fields=["name", "customer", "route", "assigned_user", "effective_to"],
        order_by="customer asc",
    )
    if txt:
        rows = [row for row in rows if txt.lower() in row.customer.lower()]
    return rows


@frappe.whitelist()
def get_dsr_delivery_context() -> dict:
    """Return company-scoped defaults for the DSR delivery workspace."""
    tenant = require_tenant()
    routes = frappe.get_all(
        "Distribution Route",
        filters={"company": tenant.company, "assigned_user": frappe.session.user, "active": 1},
        fields=["name", "route_name"],
        order_by="route_name asc",
    )
    default_warehouse = frappe.db.get_value(
        "Distribution Settings", {"company": tenant.company}, "default_warehouse"
    )
    if default_warehouse and frappe.db.get_value("Warehouse", default_warehouse, "company") != tenant.company:
        default_warehouse = None
    if not default_warehouse:
        fallback = frappe.get_all(
            "Warehouse",
            {"company": tenant.company, "is_group": 0, "disabled": 0},
            pluck="name",
            order_by="warehouse_name asc",
        )
        default_warehouse = fallback[0] if fallback else None
    default_account = frappe.db.get_value(
        "Distribution Settings", {"company": tenant.company}, "default_cash_account"
    )
    if default_account and frappe.db.get_value("Account", default_account, "company") != tenant.company:
        default_account = None
    return {
        "company": tenant.company,
        "routes": routes,
        "default_route": routes[0].name if routes else None,
        "default_warehouse": default_warehouse,
        "default_account": default_account,
    }


@frappe.whitelist()
def get_retailer_summary(customer: str, route: str | None = None) -> dict:
    tenant = require_tenant()
    _assert_assigned_customer(tenant.company, customer, route)
    from erpnext.accounts.utils import get_balance_on

    balance = get_balance_on(
        party_type="Customer",
        party=customer,
        company=tenant.company,
    )
    return {
        "company": tenant.company,
        "customer": customer,
        "net_due": balance,
        "overdue": balance,
        "unapplied_credit": 0,
    }


@frappe.whitelist()
def get_supplier_free_availability(warehouse: str, route: str | None = None) -> list[dict]:
    tenant = require_tenant()
    _assert_warehouse(tenant.company, warehouse)
    if route:
        _assert_assigned_route(tenant.company, route)

    from erpnext.stock.utils import get_stock_balance

    item_names = frappe.get_all(
        "Purchase Receipt Item",
        filters={"rd_free_qty": [">", 0], "docstatus": 1},
        pluck="item_code",
    )
    results = []
    for item_code in sorted(set(item_names)):
        validate_master_scope(tenant.company, "Item", item_code)
        available = get_stock_balance(item_code, warehouse, nowdate())
        if available > 0:
            results.append({"item_code": item_code, "warehouse": warehouse, "available_qty": available})
    return results


@frappe.whitelist()
def get_sales_catalog(price_list: str | None = None) -> list[dict]:
    tenant = require_tenant()
    price_list = price_list or get_or_create_company_sales_price_list(tenant.company)
    validate_master_scope(tenant.company, "Price List", price_list)
    item_codes = frappe.get_all(
        "Distribution Master Scope",
        filters={"company": tenant.company, "master_type": "Item", "active": 1},
        pluck="master_name",
        order_by="master_name asc",
    )
    catalog = []
    for item_code in item_codes:
        item = frappe.get_doc("Item", item_code)
        prices = frappe.get_all(
            "Item Price",
            filters={"item_code": item_code, "price_list": price_list, "selling": 1},
            fields=["uom", "price_list_rate"],
        )
        price_by_uom = {row.uom or item.stock_uom: row.price_list_rate for row in prices}
        rate = price_by_uom.get(item.stock_uom) or next(iter(price_by_uom.values()), None)
        if rate is None:
            continue
        catalog.append(
            {
                "item_code": item_code,
                "item_name": item.item_name,
                "stock_uom": item.stock_uom,
                "uoms": [{"uom": row.uom, "conversion_factor": row.conversion_factor} for row in item.get("uoms") or []],
                "rate": rate,
                "prices": [{"uom": uom, "rate": item_rate} for uom, item_rate in price_by_uom.items()],
                "price_list": price_list,
            }
        )
    return catalog


@frappe.whitelist()
def record_outlet_visit(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    key = _required(data, "idempotency_key")
    existing = frappe.db.get_value("Outlet Visit", {"company": tenant.company, "idempotency_key": key}, "name")
    if existing:
        return existing
    _assert_assigned_customer(tenant.company, data["customer"], data.get("route"))
    _validate_gps(data)
    doc = frappe.get_doc(
        {
            "doctype": "Outlet Visit",
            "company": tenant.company,
            "customer": data["customer"],
            "route": data.get("route"),
            "field_user": frappe.session.user,
            "visited_on": data.get("visited_on") or nowdate(),
            "visit_status": data.get("visit_status") or "Started",
            "idempotency_key": key,
            "gps_latitude": data.get("gps_latitude"),
            "gps_longitude": data.get("gps_longitude"),
            "gps_accuracy": data.get("gps_accuracy"),
            "gps_captured_on": data.get("gps_captured_on"),
        }
    )
    doc.insert()
    return doc.name


@frappe.whitelist()
def save_sr_order(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    key = _required(data, "idempotency_key")
    existing = frappe.db.get_value("SR Order", {"company": tenant.company, "idempotency_key": key}, "name")
    if existing:
        return existing
    _assert_assigned_customer(tenant.company, data["customer"], data.get("route"))
    _validate_gps(data)
    validate_master_scope(tenant.company, "Price List", _required(data, "price_list"))
    if not data.get("items"):
        frappe.throw(_("An order must contain at least one item."))

    item_rows = []
    for row in data["items"]:
        if any(key in row for key in ("free_qty", "promotion_terms", "promotion_source")):
            frappe.throw(_("Promotional terms and free quantities are server-controlled."))
        item_rows.append(_order_item(tenant.company, row, data.get("price_list")))

    doc = frappe.get_doc(
        {
            "doctype": "SR Order",
            "company": tenant.company,
            "customer": data["customer"],
            "route": data.get("route"),
            "field_user": frappe.session.user,
            "order_date": data.get("order_date") or nowdate(),
            "price_list": data.get("price_list"),
            "status": "Draft",
            "idempotency_key": key,
            "outlet_visit": data.get("outlet_visit"),
            "gps_latitude": data.get("gps_latitude"),
            "gps_longitude": data.get("gps_longitude"),
            "gps_accuracy": data.get("gps_accuracy"),
            "gps_captured_on": data.get("gps_captured_on"),
            "items": item_rows,
        }
    )
    doc.insert()
    return doc.name


@frappe.whitelist()
def submit_distribution_delivery(payload: str | dict) -> str:
    data = _payload(payload)
    tenant = require_tenant(company=data.get("company"))
    key = _required(data, "idempotency_key")
    existing = frappe.db.get_value("Delivery Note", {"rd_idempotency_key": key}, "name")
    if existing:
        return existing
    _assert_assigned_customer(tenant.company, data["customer"], data.get("route"))
    _validate_gps(data)
    if not data.get("items"):
        frappe.throw(_("A delivery must contain at least one item."))
    if not data.get("warehouse"):
        frappe.throw(_("A delivery source warehouse is required."))
    _assert_warehouse(tenant.company, data["warehouse"])

    item_rows = []
    for row in data["items"]:
        item = _order_item(tenant.company, row, data.get("price_list"))
        item.update(
            {
                "warehouse": data["warehouse"],
                "rd_stock_category": row.get("rd_stock_category") or "Saleable",
                "rd_supplier_free_source": row.get("rd_supplier_free_source"),
            }
        )
        item_rows.append(item)

    delivery = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "company": tenant.company,
            "customer": data["customer"],
            "posting_date": data.get("delivery_date") or nowdate(),
            "set_warehouse": data["warehouse"],
            "rd_route": data.get("route"),
            "rd_dsr": frappe.session.user,
            "rd_outlet_visit": data.get("outlet_visit"),
            "rd_idempotency_key": key,
            "items": item_rows,
        }
    )
    delivery.insert()
    delivery.submit()
    return delivery.name


def validate_sr_order(doc, method=None) -> None:
    require_tenant(company=doc.company)
    _assert_assigned_customer(doc.company, doc.customer, doc.route, doc.field_user)
    validate_master_scope(doc.company, "Customer", doc.customer)
    validate_master_scope(doc.company, "Price List", doc.price_list)
    _validate_gps(doc)
    for row in doc.get("items") or []:
        _order_item(doc.company, row, doc.price_list)


def validate_outlet_visit(doc, method=None) -> None:
    require_tenant(company=doc.company)
    _assert_assigned_customer(doc.company, doc.customer, doc.route, doc.field_user)
    _validate_gps(doc)


@frappe.whitelist()
def sync_field_sales_queue(events: str | list) -> list[dict]:
    payloads = json.loads(events) if isinstance(events, str) else events
    results = []
    for event in payloads or []:
        if event.get("type") == "visit":
            name = record_outlet_visit(event.get("payload") or {})
        elif event.get("type") == "order":
            name = save_sr_order(event.get("payload") or {})
        elif event.get("type") == "delivery":
            name = submit_distribution_delivery(event.get("payload") or {})
        elif event.get("type") == "collection":
            from reckon_distribution.collection import record_collection

            name = record_collection(event.get("payload") or {})
        else:
            frappe.throw(_("Unsupported field sync event."))
        results.append({"type": event.get("type"), "idempotency_key": (event.get("payload") or {}).get("idempotency_key"), "name": name})
    return results


def _order_item(company: str, row: dict, price_list: str | None) -> dict:
    item_code = _required(row, "item_code")
    validate_master_scope(company, "Item", item_code)
    item = frappe.get_doc("Item", item_code)
    uom = row.get("uom") or item.stock_uom
    conversion = 1
    for item_uom in item.get("uoms") or []:
        if item_uom.uom == uom:
            conversion = item_uom.conversion_factor
            break
    if uom != item.stock_uom and conversion == 1:
        frappe.throw(_("UOM {0} is not configured for Item {1}.").format(uom, item_code))
    qty = float(row.get("qty") or 0)
    if qty <= 0:
        frappe.throw(_("Order quantity must be greater than zero."))
    rate = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "uom": uom, "selling": 1},
        "price_list_rate",
    )
    if rate is None:
        rate = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": price_list, "selling": 1},
            "price_list_rate",
        )
    if rate is None:
        frappe.throw(_("No selling price is configured for Item {0}.").format(item_code))
    return {
        "item_code": item_code,
        "uom": uom,
        "qty": qty,
        "conversion_factor": conversion,
        "stock_qty": qty * conversion,
        "rate": rate,
    }


def _assert_assigned_customer(company: str, customer: str, route: str | None, user: str | None = None) -> None:
    filters = {"company": company, "customer": customer, "active": 1}
    if route:
        filters["route"] = route
    if user and not user_can_bypass_tenant():
        filters["assigned_user"] = user
    if not frappe.db.exists("Retailer Route Assignment", filters):
        frappe.throw(_("Retailer is not assigned to this user and route."), frappe.PermissionError)


def _assert_assigned_route(company: str, route: str) -> None:
    route_doc = get_tenant_doc("Distribution Route", route)
    if route_doc.company != company or not route_doc.active:
        frappe.throw(_("Route is not active for this Company."))


def _assert_warehouse(company: str, warehouse: str) -> None:
    warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company")
    if warehouse_company != company:
        frappe.throw(_("Warehouse does not belong to this Company."))


def _validate_gps(data) -> None:
    latitude = data.get("gps_latitude")
    longitude = data.get("gps_longitude")
    accuracy = data.get("gps_accuracy")
    if latitude is None and longitude is None and accuracy is None:
        return
    if latitude is None or longitude is None:
        frappe.throw(_("Both GPS latitude and longitude are required when location is captured."))
    if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
        frappe.throw(_("GPS coordinates are outside the valid range."))
    if accuracy is not None and float(accuracy) < 0:
        frappe.throw(_("GPS accuracy cannot be negative."))


def _payload(payload: str | dict) -> dict:
    return json.loads(payload) if isinstance(payload, str) else payload


def _required(data: dict, fieldname: str):
    value = data.get(fieldname)
    if not value:
        frappe.throw(_("{0} is required.").format(fieldname))
    return value
