from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import validate_tenant_owned_doc

PROFILE_MASTERS = {
    "Company Item Profile": "Item",
    "Company Retailer Profile": "Customer",
    "Company Supplier Profile": "Supplier",
    "Company Item Price Profile": "Item",
}


def validate_profile(doc, method=None) -> None:
    validate_tenant_owned_doc(doc)
    master_type = PROFILE_MASTERS.get(doc.doctype)
    if not master_type:
        frappe.throw(_("Unsupported Company profile type."))
    master_name = doc.item if master_type == "Item" else doc.customer if master_type == "Customer" else doc.supplier
    if not master_name or not frappe.db.exists(master_type, master_name):
        frappe.throw(_("Select a valid ERPNext {0}.").format(master_type))
    validate_master_scope(doc.company, master_type, master_name)
    if doc.doctype == "Company Retailer Profile" and doc.route:
        route_company = frappe.db.get_value("Distribution Route", doc.route, "company")
        if route_company != doc.company:
            frappe.throw(_("The selected Route must belong to the same Company."), frappe.PermissionError)
    duplicate_filters = {"company": doc.company, "name": ["!=", doc.name]}
    if master_type == "Item":
        duplicate_filters["item"] = master_name
    elif master_type == "Customer":
        duplicate_filters["customer"] = master_name
    else:
        duplicate_filters["supplier"] = master_name
    if doc.doctype == "Company Item Price Profile":
        duplicate_filters.update({"price_list": doc.price_list, "uom": doc.uom})
    if frappe.db.exists(doc.doctype, duplicate_filters):
        frappe.throw(_("This ERPNext master already has a Company profile."))


def validate_company_item_price_profile(doc, method=None) -> None:
    validate_profile(doc, method)
    if not doc.price_list or not frappe.db.exists("Price List", doc.price_list):
        frappe.throw(_("Select a valid Price List."))
    if not doc.uom or not frappe.db.exists("UOM", doc.uom):
        frappe.throw(_("Select a valid UOM."))
    validate_master_scope(doc.company, "Price List", doc.price_list)
