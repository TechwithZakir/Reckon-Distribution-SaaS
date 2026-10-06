from __future__ import annotations

import frappe
from frappe import _

from reckon_saas_platform.constants import PLATFORM_ROLES, SAAS_PLATFORM_WORKSPACE


def after_install() -> None:
    setup_roles()
    setup_workspace()


def after_migrate() -> None:
    setup_roles()
    setup_workspace()


def setup_roles() -> None:
    for role in PLATFORM_ROLES:
        if not frappe.db.exists("Role", role.name):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role.name,
                    "desk_access": 1,
                    "is_custom": 1,
                    "home_page": "reckon-saas-admin",
                }
            ).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Role", role.name, {"desk_access": 1, "home_page": "reckon-saas-admin"})


def setup_workspace() -> None:
    if not frappe.db.exists("Workspace", SAAS_PLATFORM_WORKSPACE):
        frappe.get_doc(_workspace_doc()).insert(ignore_permissions=True)
    else:
        workspace = frappe.get_doc("Workspace", SAAS_PLATFORM_WORKSPACE)
        workspace.update(_workspace_doc(update=True))
        workspace.save(ignore_permissions=True)


def _workspace_doc(update: bool = False) -> dict:
    data = {
        "doctype": "Workspace",
        "label": SAAS_PLATFORM_WORKSPACE,
        "title": _("Reckon SaaS Admin"),
        "module": "SaaS Platform",
        "category": "Modules",
        "public": 0,
        "is_hidden": 0,
        "icon": "settings",
        "roles": [{"role": role.name} for role in PLATFORM_ROLES],
        "content": """[
 {"id":"intro","type":"header","data":{"text":"Reckon SaaS Admin"}},
 {"id":"summary","type":"paragraph","data":{"text":"Plans, registrations, subscriptions, payments, and tenant provisioning."}}
]""",
        "shortcuts": [],
        "links": [],
        "charts": [],
        "number_cards": [],
    }
    if not update:
        data["name"] = SAAS_PLATFORM_WORKSPACE
    return data
