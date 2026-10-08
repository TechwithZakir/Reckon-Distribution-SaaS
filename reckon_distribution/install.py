from __future__ import annotations

import frappe
from frappe import _, permissions

from reckon_distribution.constants import DISTRIBUTION_WORKSPACE, OPERATIONAL_ROLES


def after_install() -> None:
    setup_roles()
    ensure_distribution_permissions()
    setup_workspace()
    ensure_purchase_receipt_fields()
    ensure_master_quick_entry()


def after_migrate() -> None:
    setup_roles()
    ensure_distribution_permissions()
    setup_workspace()
    ensure_purchase_receipt_fields()
    ensure_master_quick_entry()


def ensure_master_quick_entry() -> None:
    """Keep native ERPNext master creation compact for distribution users."""
    configurations = {
        "Customer": {"customer_name", "customer_type", "customer_group", "territory"},
        "Supplier": {"supplier_name", "supplier_type", "supplier_group"},
        "Item": {"item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item"},
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
        if doctype == "Item":
            _set_property("Item", "item_code", "read_only", "1", "Check")
            _set_property("Item", "item_code", "reqd", "0", "Check")
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


def ensure_distribution_permissions() -> None:
    """Grant navigation and native-master access to Distribution roles."""
    ensure_assigned_user_roles()
    ensure_distribution_page_roles()
    ensure_native_master_permissions()


def ensure_assigned_user_roles() -> None:
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return
    role_map = {
        "Company Admin": "Reckon Distribution Admin",
        "Company Manager": "Reckon Distribution Manager",
        "Master Data Manager": "Reckon Master Data Manager",
        "SR": "Reckon Distribution User",
        "DSR": "Reckon Distribution User",
    }
    assignments = frappe.get_all(
        "Tenant User Assignment",
        filters={"active": 1},
        fields=["user", "role_profile"],
    )
    for assignment in assignments:
        role = role_map.get(assignment.role_profile)
        if not role or not frappe.db.exists("User", assignment.user):
            continue
        user = frappe.get_doc("User", assignment.user)
        if role not in frappe.get_roles(assignment.user):
            user.add_roles(role)
        frappe.clear_cache(user=assignment.user)


def ensure_distribution_page_roles() -> None:
    page_names = {
        "distribution",
        "distribution-master-setup",
        "distribution-item-uom-setup",
        "distribution-team-access",
        "van-loading",
        "field-sales",
        "dsr-delivery",
        "dsr-day-settlement",
    }
    roles = [role.name for role in OPERATIONAL_ROLES]
    for page_name in page_names:
        if not frappe.db.exists("Page", page_name):
            continue
        for role in roles:
            if frappe.db.exists(
                "Has Role",
                {"parent": page_name, "parenttype": "Page", "parentfield": "roles", "role": role},
            ):
                continue
            next_idx = frappe.db.sql(
                """
                select coalesce(max(idx), 0) + 1
                from `tabHas Role`
                where parent = %s and parenttype = 'Page' and parentfield = 'roles'
                """,
                page_name,
            )[0][0]
            frappe.db.sql(
                """
                insert into `tabHas Role`
                    (name, creation, modified, modified_by, owner, docstatus,
                     parent, parentfield, parenttype, idx, role)
                values (%s, now(), now(), %s, %s, 0, %s, 'roles', 'Page', %s, %s)
                """,
                (frappe.generate_hash(length=10), frappe.session.user, frappe.session.user, page_name, next_idx, role),
            )


def ensure_native_master_permissions() -> None:
    master_permissions = {
        "Page": {"read"},
        "Customer": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Supplier": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Item": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Item Price": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Price List": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "UOM": {"read"},
        # Supporting link masters are shared ERPNext references. Distribution users
        # may select them, but must not edit the global definitions.
        "Item Group": {"read"},
        "Brand": {"read"},
        "Customer Group": {"read"},
        "Supplier Group": {"read"},
        "Territory": {"read"},
        "Warehouse": {"read"},
        "Payment Terms Template": {"read"},
        "Account": {"read"},
    }
    full_access_roles = {"Reckon Distribution Admin", "Reckon Distribution Manager", "Reckon Master Data Manager"}
    read_only_roles = {"Reckon Distribution User"}
    for doctype, full_rights in master_permissions.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        permissions.setup_custom_perms(doctype)
        for role in full_access_roles | read_only_roles:
            existing = frappe.db.exists(
                "Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
            )
            if existing:
                perm = frappe.get_doc("Custom DocPerm", existing)
            else:
                perm = frappe.get_doc(
                    {
                        "doctype": "Custom DocPerm",
                        "parent": doctype,
                        "parenttype": "DocType",
                        "parentfield": "permissions",
                        "role": role,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                )
                perm.insert(ignore_permissions=True)
            rights = full_rights if role in full_access_roles else {"read"}
            for right in full_rights:
                enabled = right in rights
                perm.db_set(right, 1 if enabled else 0)
                # Keep Frappe's native permission resolver in sync. Some v16
                # installations do not immediately include Custom DocPerm rows
                # in the cached role permission map after migration.
                if enabled and hasattr(permissions, "add_permission"):
                    if not frappe.db.exists(
                        "DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
                    ):
                        permissions.add_permission(doctype, role, 0)
                    if hasattr(permissions, "update_permission_property"):
                        permissions.update_permission_property(doctype, role, 0, right, 1)
        frappe.clear_cache(doctype=doctype)


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
            {"color": "Blue", "label": "Master Setup", "link_to": "distribution-master-setup", "type": "Page"},
            {"color": "Purple", "label": "Team & Access", "link_to": "distribution-team-access", "type": "Page"},
            {"color": "Green", "label": "Field Sales", "link_to": "field-sales", "type": "Page"},
            {"color": "Orange", "label": "Van Loading", "link_to": "van-loading", "type": "Page"},
            {"color": "Green", "label": "Deliver & Collect", "link_to": "dsr-delivery", "type": "Page"},
            {"color": "Red", "label": "Day Settlement", "link_to": "dsr-day-settlement", "type": "Page"},
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
