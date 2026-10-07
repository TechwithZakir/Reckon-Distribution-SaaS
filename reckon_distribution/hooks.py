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
app_icon_route = "/app/distribution"

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
}
get_website_user_home_page = "reckon_distribution.desk_guard.get_user_home_page"
before_request = ["reckon_distribution.desk_guard.restrict_distribution_desk_request"]
app_include_js = ["/assets/reckon_distribution/js/desk_guard.js"]

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
    "Distribution Settings": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Company UOM Profile": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Distribution Route": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
    "Distribution Master Scope": "reckon_saas_platform.tenant_security.get_tenant_owned_query",
}

has_permission = {
    "Tenant Security Test Record": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Purchase Receipt": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Van Loading Challan": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Van Loading Acknowledgement": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Stock Entry": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Settings": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Company UOM Profile": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Route": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
    "Distribution Master Scope": "reckon_saas_platform.tenant_security.has_tenant_owned_permission",
}

override_whitelisted_methods = {
    "frappe.desk.desk_page.getpage": "reckon_distribution.desk_guard.getpage",
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
        "filters": [["name", "=", "Distribution"]],
    },
]
