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

required_apps = ["erpnext"]

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

permission_query_conditions = {
    "SaaS Payment": "reckon_distribution.saas_security.get_vendor_only_query",
    "SaaS Plan": "reckon_distribution.saas_security.get_vendor_only_query",
    "SaaS Registration": "reckon_distribution.saas_security.get_vendor_only_query",
    "SaaS Subscription": "reckon_distribution.saas_security.get_vendor_only_query",
    "Tenant Provisioning Job": "reckon_distribution.saas_security.get_vendor_only_query",
    "Tenant User Assignment": "reckon_distribution.tenant_security.get_tenant_user_assignment_query",
    "Tenant Security Test Record": "reckon_distribution.tenant_security.get_tenant_owned_query",
}

has_permission = {
    "SaaS Payment": "reckon_distribution.saas_security.has_vendor_only_permission",
    "SaaS Plan": "reckon_distribution.saas_security.has_vendor_only_permission",
    "SaaS Registration": "reckon_distribution.saas_security.has_vendor_only_permission",
    "SaaS Subscription": "reckon_distribution.saas_security.has_vendor_only_permission",
    "Tenant Provisioning Job": "reckon_distribution.saas_security.has_vendor_only_permission",
    "Tenant User Assignment": "reckon_distribution.tenant_security.has_tenant_user_assignment_permission",
    "Tenant Security Test Record": "reckon_distribution.tenant_security.has_tenant_owned_permission",
}

role_home_page = {
    "Reckon Distribution User": "app/distribution",
    "Reckon Distribution Manager": "app/distribution",
    "Reckon Distribution Admin": "app/distribution",
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
