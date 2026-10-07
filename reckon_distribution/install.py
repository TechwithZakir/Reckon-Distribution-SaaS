from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.constants import DISTRIBUTION_WORKSPACE, OPERATIONAL_ROLES


def after_install() -> None:
    setup_roles()
    setup_workspace()
    ensure_purchase_receipt_fields()
    ensure_master_quick_entry()


def after_migrate() -> None:
    setup_roles()
    setup_workspace()
    ensure_purchase_receipt_fields()
    ensure_master_quick_entry()


def ensure_master_quick_entry() -> None:
    """Keep native ERPNext master creation compact for distribution users."""
    configurations = {
        "Customer": {"customer_name", "customer_type", "customer_group", "territory"},
        "Supplier": {"supplier_name", "supplier_type", "supplier_group"},
        "Item": {"item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item"},
        "Item Price": {"item_code", "price_list", "price_list_rate", "uom", "selling"},
    }
    for doctype, allowed_fields in configurations.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        _set_property(doctype, None, "quick_entry", "1", "Check")
        for field in frappe.get_meta(doctype).fields:
            if not field.fieldname:
                continue
            _set_property(
                doctype,
                field.fieldname,
                "allow_in_quick_entry",
                "1" if field.fieldname in allowed_fields else "0",
                "Check",
            )
        frappe.clear_cache(doctype=doctype)


def _set_property(doctype: str, fieldname: str | None, property_name: str, value: str, property_type: str) -> None:
    filters = {
        "doc_type": doctype,
        "doctype_or_field": "DocType" if fieldname is None else "DocField",
        "property": property_name,
    }
    if fieldname is not None:
        filters["field_name"] = fieldname
    name = frappe.db.exists("Property Setter", filters)
    values = {
        "doctype": "Property Setter",
        "doc_type": doctype,
        "doctype_or_field": filters["doctype_or_field"],
        "property": property_name,
        "value": value,
        "property_type": property_type,
        "is_system_generated": 1,
    }
    if fieldname is not None:
        values["field_name"] = fieldname
    setter = frappe.get_doc("Property Setter", name) if name else frappe.get_doc(values)
    setter.update(values)
    setter.save(ignore_permissions=True) if setter.name else setter.insert(ignore_permissions=True)


def ensure_purchase_receipt_fields() -> None:
    fields = [
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_source",
            "label": "Supplier Promotion Source",
            "fieldtype": "Data",
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_reference",
            "label": "Supplier Promotion Reference",
            "fieldtype": "Data",
            "insert_after": "rd_promotion_source",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_terms",
            "label": "Supplier Promotion Terms",
            "fieldtype": "Small Text",
            "insert_after": "rd_promotion_reference",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_paid_qty",
            "label": "Paid Quantity",
            "fieldtype": "Float",
            "insert_after": "qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_free_qty",
            "label": "Supplier Free Quantity",
            "fieldtype": "Float",
            "insert_after": "rd_paid_qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_shortage_qty",
            "label": "Shortage Quantity",
            "fieldtype": "Float",
            "insert_after": "rd_free_qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_dispute_note",
            "label": "Shortage / Dispute Note",
            "fieldtype": "Small Text",
            "insert_after": "rd_shortage_qty",
        },
        {
            "dt": "Stock Entry",
            "fieldname": "rd_van_loading_challan",
            "label": "Van Loading Challan",
            "fieldtype": "Link",
            "options": "Van Loading Challan",
            "read_only": 1,
            "insert_after": "stock_entry_type",
        },
        {
            "dt": "Payment Entry",
            "fieldname": "rd_collection_receipt",
            "label": "DSR Collection Receipt",
            "fieldtype": "Link",
            "options": "DSR Collection Receipt",
            "read_only": 1,
            "insert_after": "payment_type",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_route",
            "label": "Distribution Route",
            "fieldtype": "Link",
            "options": "Distribution Route",
            "insert_after": "customer",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_dsr",
            "label": "Delivery DSR",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "rd_route",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_outlet_visit",
            "label": "Outlet Visit",
            "fieldtype": "Link",
            "options": "Outlet Visit",
            "insert_after": "rd_dsr",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_idempotency_key",
            "label": "Distribution Idempotency Key",
            "fieldtype": "Data",
            "read_only": 1,
            "unique": 1,
            "insert_after": "rd_outlet_visit",
        },
        {
            "dt": "Delivery Note Item",
            "fieldname": "rd_stock_category",
            "label": "Stock Category",
            "fieldtype": "Select",
            "options": "Saleable\nSupplier Free",
            "reqd": 1,
            "insert_after": "item_code",
        },
        {
            "dt": "Delivery Note Item",
            "fieldname": "rd_supplier_free_source",
            "label": "Supplier Free Source Receipt",
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "insert_after": "rd_stock_category",
        },
    ]
    for field in fields:
        if frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}):
            continue
        frappe.get_doc({"doctype": "Custom Field", **field}).insert(ignore_permissions=True)


def setup_roles() -> None:
    for role in OPERATIONAL_ROLES:
        if not frappe.db.exists("Role", role.name):
            doc = frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role.name,
                    "desk_access": 1,
                    "is_custom": 1,
                }
            )
            doc.insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Role", role.name, "desk_access", 1)
            frappe.db.set_value("Role", role.name, "home_page", "")


def setup_workspace() -> None:
    if not frappe.db.exists("Workspace", DISTRIBUTION_WORKSPACE):
        workspace = frappe.get_doc(_workspace_doc())
        workspace.insert(ignore_permissions=True)
    else:
        workspace = frappe.get_doc("Workspace", DISTRIBUTION_WORKSPACE)
        workspace.update(_workspace_doc(update=True))
        workspace.save(ignore_permissions=True)


def _workspace_doc(update: bool = False) -> dict:
    data = {
        "doctype": "Workspace",
        "label": DISTRIBUTION_WORKSPACE,
        "title": _("Distribution"),
        "module": "Distribution",
        "category": "Modules",
        "public": 0,
        "is_hidden": 0,
        "icon": "organization",
        "roles": [{"role": role.name} for role in OPERATIONAL_ROLES],
        "content": _workspace_content(),
        "shortcuts": [
            {"label": "Master Setup", "link_to": "distribution-master-setup", "type": "Page"},
            {"label": "Van Loading", "link_to": "van-loading", "type": "Page"},
            {"label": "DSR Collection Receipt", "link_to": "DSR Collection Receipt", "type": "DocType"},
            {"label": "DSR Due Assignment", "link_to": "DSR Due Assignment", "type": "DocType"},
            {"label": "SR Orders", "link_to": "SR Order", "type": "DocType"},
            {"label": "Outlet Visits", "link_to": "Outlet Visit", "type": "DocType"},
            {"label": "Field Sales", "link_to": "field-sales", "type": "Page"},
            {"label": "Delivery Notes", "link_to": "Delivery Note", "type": "DocType"},
            {"label": "Return Inspections", "link_to": "Return Inspection", "type": "DocType"},
            {"label": "DSR Day Settlement", "link_to": "DSR Day Settlement", "type": "DocType"},
            {"label": "DSR Delivery & Collection", "link_to": "dsr-delivery", "type": "Page"},
            {"label": "Company Team & Access", "link_to": "distribution-team-access", "type": "Page"},
            {"label": "Distribution Settings", "link_to": "Distribution Settings", "type": "DocType"},
            {"label": "Purchase Receipt", "link_to": "Purchase Receipt", "type": "DocType"},
        ],
        "links": [],
        "charts": [],
        "number_cards": [],
    }
    if not update:
        data["name"] = DISTRIBUTION_WORKSPACE
    return data


def _workspace_content() -> str:
    return """[
 {"id":"intro","type":"header","data":{"text":"Distribution"}},
 {"id":"summary","type":"paragraph","data":{"text":"Bangla-first SR/DSR distribution workspace. Transaction workflows will be added in later phases after tenant isolation is enforced."}},
 {"id":"foundation","type":"shortcut","data":{"shortcut_name":"Distribution Shell","col":3}}
]"""
