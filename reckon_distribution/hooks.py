"""Frappe app registration for Reckon Distribution.

This foundation intentionally avoids operational transaction logic. ERPNext remains
the stock and accounting system of record; this app adds distribution navigation,
roles, compatibility helpers, and later company-isolated workflows.
"""

app_name = "reckon_distribution"
app_title = "Reckon Distribution"
app_publisher = "Reckon Technologies Ltd."
app_description = "Bangla-first SR/DSR FMCG distribution workflows for ERPNext"
app_email = "support@reckon.tech"
app_license = "MIT"
app_logo_url = "/assets/reckon_distribution/images/reckon-distribution-icon.svg"
app_icon_url = app_logo_url
app_icon_title = app_title
app_icon_route = "/desk/distribution"

required_apps = ["erpnext", "reckon_saas_platform"]

add_to_apps_screen = [
    {
        "name": app_name,
        "logo": app_logo_url,
        "title": app_title,
        "route": app_icon_route,
        "desk_route": app_icon_route,
        "has_permission": "reckon_distribution.api.check_app_permission",
        "sequence_id": 25,
    }
]

after_install = "reckon_distribution.install.after_install"
after_migrate = "reckon_distribution.install.after_migrate"
doc_events = {
    "Purchase Receipt": {
        "validate": "reckon_distribution.purchase_receipt.validate_purchase_receipt",
        "before_submit": "reckon_distribution.purchase_receipt.validate_purchase_receipt",
    },
    "Van Loading Acknowledgement": {
        "validate": "reckon_distribution.van_loading.validate_van_loading_acknowledgement",
        "on_submit": "reckon_distribution.van_loading.on_van_loading_acknowledgement_submit",
    },
    "Stock Entry": {
        "validate": "reckon_distribution.van_loading.validate_van_loading_stock_entry",
    },
    "DSR Collection Receipt": {
        "validate": "reckon_distribution.collection.validate_collection_receipt",
    },
    "DSR Due Assignment": {
        "validate": "reckon_distribution.due_assignment.validate_due_assignment",
    },
    "Retailer Route Assignment": {
        "validate": "reckon_distribution.route_assignment.validate_route_assignment",
    },
    "Outlet Visit": {
        "validate": "reckon_distribution.field_sales.validate_outlet_visit",
    },
    "SR Order": {
        "validate": "reckon_distribution.field_sales.validate_sr_order",
    },
    "Delivery Note": {
        "validate": "reckon_distribution.delivery.validate_delivery_note",
        "before_submit": "reckon_distribution.delivery.validate_delivery_note",
    },
    "Return Inspection": {
        "validate": "reckon_distribution.delivery.validate_return_inspection",
    },
    "DSR Day Settlement": {
        "validate": "reckon_distribution.settlement.validate_day_settlement",
    },
    "Customer": {
        "validate": "reckon_distribution.master_data.validate_shared_master_change",
        "after_insert": "reckon_distribution.master_data.auto_scope_shared_master",
    },
    "Supplier": {
        "validate": "reckon_distribution.master_data.validate_shared_master_change",
        "after_insert": "reckon_distribution.master_data.auto_scope_shared_master",
    },
    "Item": {
        "before_insert": "reckon_distribution.master_data.normalize_item_code",
        "validate": "reckon_distribution.master_data.validate_shared_master_change",
        "after_insert": "reckon_distribution.master_data.auto_scope_shared_master",
    },
    "Item Price": {
        "validate": "reckon_distribution.master_data.validate_shared_master_change",
        "after_insert": "reckon_distribution.master_data.auto_scope_shared_master",
    },
    "Price List": {
        "validate": "reckon_distribution.master_data.validate_shared_master_change",
        "after_insert": "reckon_distribution.master_data.auto_scope_shared_master",
    },
    "Warehouse": {
        "validate": "reckon_distribution.warehouse.validate_warehouse",
    },
    "Tenant User Assignment": {
        "validate": "reckon_distribution.warehouse.validate_tenant_assignment",
        "after_insert": "reckon_distribution.warehouse.sync_tenant_user_permission",
        "on_update": "reckon_distribution.warehouse.sync_tenant_user_permission",
    },
}
get_website_user_home_page = "reckon_distribution.desk_guard.get_user_home_page"
before_request = ["reckon_distribution.desk_guard.restrict_distribution_desk_request"]
reckon_saas_modules = [
    "reckon_distribution.saas_module.get_module_definition",
]

website_route_rules = [
]

permission_query_conditions = {
    "Tenant Security Test Record": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Purchase Receipt": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Van Loading Challan": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Van Loading Acknowledgement": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Stock Entry": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "DSR Collection Receipt": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "DSR Due Assignment": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Retailer Route Assignment": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Outlet Visit": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "SR Order": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Delivery Note": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Return Inspection": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "DSR Day Settlement": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Distribution Settings": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Company UOM Profile": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Distribution Route": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Distribution Master Scope": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Warehouse": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Company": "reckon_distribution.warehouse.get_company_query",
    "Customer": "reckon_distribution.master_data.get_shared_master_query",
    "Supplier": "reckon_distribution.master_data.get_shared_master_query",
    "Item": "reckon_distribution.master_data.get_shared_master_query",
    "Item Price": "reckon_distribution.master_data.get_shared_master_query",
    "Price List": "reckon_distribution.master_data.get_shared_master_query",
}

has_permission = {
    "Tenant Security Test Record": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Purchase Receipt": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Van Loading Challan": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Van Loading Acknowledgement": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Stock Entry": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "DSR Collection Receipt": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "DSR Due Assignment": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Retailer Route Assignment": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Outlet Visit": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "SR Order": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Delivery Note": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Return Inspection": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "DSR Day Settlement": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Settings": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Company UOM Profile": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Route": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Master Scope": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Warehouse": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Company": "reckon_distribution.warehouse.has_company_permission",
    "Customer": "reckon_distribution.master_data.has_shared_master_permission",
    "Supplier": "reckon_distribution.master_data.has_shared_master_permission",
    "Item": "reckon_distribution.master_data.has_shared_master_permission",
    "Item Price": "reckon_distribution.master_data.has_shared_master_permission",
    "Price List": "reckon_distribution.master_data.has_shared_master_permission",
}

override_whitelisted_methods = {
    "frappe.desk.desk_page.getpage": "reckon_distribution.desk_guard.getpage",
    "erpnext.stock.doctype.warehouse.warehouse.get_children": "reckon_distribution.warehouse.get_children",
}

fixtures = [
    {
        "dt": "Role",
        "filters": [
            [
                "name",
                "in",
                [
                    "Reckon Distribution Admin",
                    "Reckon Distribution Manager",
                    "Reckon Distribution User",
                    "Reckon Vendor Superuser",
                    "Reckon Master Data Manager",
                ],
            ]
        ],
    },
    {
        "dt": "Workspace",
        "filters": [["name", "=", "Distribution Workspace"]],
    },
]
