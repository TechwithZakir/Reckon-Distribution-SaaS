from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.constants import DISTRIBUTION_WORKSPACE, OPERATIONAL_ROLES


def after_install() -> None:
    setup_roles()
    setup_workspace()
    ensure_purchase_receipt_fields()


def after_migrate() -> None:
    setup_roles()
    setup_workspace()
    ensure_purchase_receipt_fields()


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
            {"label": "Distribution Settings", "link_to": "Distribution Settings", "type": "DocType"},
            {"label": "Master Scope", "link_to": "Distribution Master Scope", "type": "DocType"},
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
