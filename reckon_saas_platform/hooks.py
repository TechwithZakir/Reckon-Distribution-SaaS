app_name = "reckon_saas_platform"
app_title = "Reckon SaaS Platform"
app_publisher = "Reckon Technologies Ltd."
app_description = "Reusable SaaS tenant, plan, subscription, payment, and provisioning platform"
app_email = "support@reckon.tech"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

after_install = "reckon_saas_platform.install.after_install"
after_migrate = "reckon_saas_platform.install.after_migrate"
get_website_user_home_page = "reckon_saas_platform.saas.get_user_home_page"

website_route_rules = [
    {"from_route": "/reckonerp-signup", "to_route": "reckonerp_signup"},
    {"from_route": "/reckon-saas-admin", "to_route": "reckon_saas_admin"},
    {"from_route": "/reckonerp-subscription", "to_route": "reckonerp_subscription"},
]

permission_query_conditions = {
    "SaaS Payment": "reckon_saas_platform.saas_security.get_vendor_only_query",
    "SaaS Plan": "reckon_saas_platform.saas_security.get_vendor_only_query",
    "SaaS Registration": "reckon_saas_platform.saas_security.get_vendor_only_query",
    "SaaS Subscription": "reckon_saas_platform.saas_security.get_vendor_only_query",
    "Tenant Provisioning Job": "reckon_saas_platform.saas_security.get_vendor_only_query",
    "Tenant User Assignment": "reckon_saas_platform.tenant_security.get_tenant_user_assignment_query",
}

has_permission = {
    "SaaS Payment": "reckon_saas_platform.saas_security.has_vendor_only_permission",
    "SaaS Plan": "reckon_saas_platform.saas_security.has_vendor_only_permission",
    "SaaS Registration": "reckon_saas_platform.saas_security.has_vendor_only_permission",
    "SaaS Subscription": "reckon_saas_platform.saas_security.has_vendor_only_permission",
    "Tenant Provisioning Job": "reckon_saas_platform.saas_security.has_vendor_only_permission",
    "Tenant User Assignment": "reckon_saas_platform.tenant_security.has_tenant_user_assignment_permission",
}

role_home_page = {
    "Reckon Vendor Superuser": "reckon-saas-admin",
}

fixtures = [
    {
        "dt": "Role",
        "filters": [["name", "in", ["Reckon Vendor Superuser"]]],
    },
    {
        "dt": "Workspace",
        "filters": [["name", "=", "Reckon SaaS Admin"]],
    },
]
