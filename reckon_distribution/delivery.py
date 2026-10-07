from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

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
    if doc.condition in {"Damaged", "Disputed"} and doc.disposition == "Restock":
        frappe.throw(_("Damaged or disputed goods cannot be restocked directly."))
    if flt(doc.qty) <= 0:
        frappe.throw(_("Return quantity must be greater than zero."))


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
