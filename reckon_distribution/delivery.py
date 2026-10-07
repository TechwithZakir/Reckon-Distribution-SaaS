from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import (
    get_tenant_doc,
    require_tenant,
    validate_tenant_owned_doc,
)


def validate_delivery_note(doc, method=None) -> None:
    if not doc.company or not doc.customer:
        frappe.throw(_("Delivery Note Company and Customer are required."))
    require_tenant(company=doc.company)
    validate_master_scope(doc.company, "Customer", doc.customer)
    if not doc.get("rd_route") or not doc.get("rd_dsr"):
        frappe.throw(_("Route and DSR are required for distribution delivery."))
    _validate_assignment(doc.company, doc.customer, doc.rd_route, doc.rd_dsr)
    for row in doc.get("items") or []:
        validate_master_scope(doc.company, "Item", row.item_code)
        if row.get("rd_stock_category") not in {"Saleable", "Supplier Free"}:
            frappe.throw(_("Row {0}: select Saleable or Supplier Free stock.").format(row.idx))
        if row.get("rd_stock_category") == "Supplier Free":
            _validate_free_source(doc.company, row)


def validate_return_inspection(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    require_tenant(company=doc.company)
    validate_master_scope(doc.company, "Customer", doc.customer)
    delivery = get_tenant_doc("Delivery Note", doc.delivery_note)
    if delivery.company != doc.company or delivery.customer != doc.customer:
        frappe.throw(_("Return inspection must belong to the Delivery Note Company and Customer."))
    if delivery.get("rd_route") != doc.route or delivery.get("rd_dsr") != doc.dsr:
        frappe.throw(_("Return inspection route and DSR must match the Delivery Note."))
    delivery_row = next((row for row in delivery.get("items") or [] if row.item_code == doc.item_code), None)
    if not delivery_row or flt(doc.qty) > flt(delivery_row.qty) + 0.000001:
        frappe.throw(_("Return quantity exceeds the delivered quantity for this Item."))
    if doc.condition in {"Damaged", "Disputed"} and doc.disposition == "Restock":
        frappe.throw(_("Damaged or disputed goods cannot be restocked directly."))
    warehouse_company = frappe.db.get_value("Warehouse", doc.warehouse, "company")
    if warehouse_company != doc.company:
        frappe.throw(_("Return warehouse must belong to the inspection Company."))
    if flt(doc.qty) <= 0:
        frappe.throw(_("Return quantity must be greater than zero."))


@frappe.whitelist()
def approve_return_inspection(inspection: str) -> str:
    doc = get_tenant_doc("Return Inspection", inspection)
    if not _is_manager():
        frappe.throw(_("Manager approval is required."), frappe.PermissionError)
    if doc.stock_entry and doc.status == "Approved":
        return doc.stock_entry
    if doc.status != "Draft":
        frappe.throw(_("Only a Draft return inspection can be approved."))
    target = doc.warehouse
    stock_entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": doc.company,
            "posting_date": nowdate(),
            "items": [
                {
                    "item_code": doc.item_code,
                    "qty": doc.qty,
                    "uom": doc.uom,
                    "t_warehouse": target,
                    "batch_no": doc.batch_no,
                }
            ],
        }
    )
    stock_entry.insert()
    stock_entry.submit()
    doc.stock_entry = stock_entry.name
    doc.status = "Approved"
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    doc.save()
    return stock_entry.name


@frappe.whitelist()
def cancel_return_inspection(inspection: str) -> str:
    doc = get_tenant_doc("Return Inspection", inspection)
    if not _is_manager():
        frappe.throw(_("Manager approval is required."), frappe.PermissionError)
    if doc.status == "Cancelled":
        return doc.name
    if doc.status == "Approved" and doc.stock_entry:
        stock_entry = frappe.get_doc("Stock Entry", doc.stock_entry)
        if stock_entry.docstatus == 1:
            stock_entry.cancel()
    doc.status = "Cancelled"
    doc.save()
    return doc.name


def _is_manager() -> bool:
    return frappe.session.user == "Administrator" or {"System Manager", "Reckon Distribution Admin", "Reckon Distribution Manager"}.intersection(frappe.get_roles())


def _validate_assignment(company: str, customer: str, route: str, dsr: str) -> None:
    route_doc = get_tenant_doc("Distribution Route", route)
    if route_doc.company != company or route_doc.assigned_user != dsr:
        frappe.throw(_("The Delivery Note route and DSR assignment is invalid."))
    if not frappe.db.exists(
        "Retailer Route Assignment",
        {"company": company, "customer": customer, "route": route, "assigned_user": dsr, "active": 1},
    ):
        frappe.throw(_("The retailer is not assigned to this route and DSR."), frappe.PermissionError)


def _validate_free_source(company: str, row) -> None:
    source = row.get("rd_supplier_free_source")
    if not source:
        frappe.throw(_("Supplier Free delivery lines require their Purchase Receipt source."))
    receipt = get_tenant_doc("Purchase Receipt", source)
    if receipt.company != company or receipt.docstatus != 1:
        frappe.throw(_("Supplier Free source must be a submitted receipt in this Company."))
    source_row = next((item for item in receipt.get("items") or [] if item.item_code == row.item_code), None)
    if not source_row or flt(source_row.get("rd_free_qty")) <= 0:
        frappe.throw(_("Item {0} is not backed by supplier-provided free goods on the source receipt.").format(row.item_code))
