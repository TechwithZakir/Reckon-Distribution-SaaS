from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.constants import DISTRIBUTION_WORKSPACE, OPERATIONAL_ROLES


def after_install() -> None:
    setup_roles()
    setup_workspace()


def after_migrate() -> None:
    setup_roles()
    setup_workspace()


def setup_roles() -> None:
    for role in OPERATIONAL_ROLES:
        if not frappe.db.exists("Role", role.name):
            doc = frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role.name,
                    "desk_access": 1,
                    "is_custom": 1,
                    "home_page": "app/distribution",
                }
            )
            doc.insert(ignore_permissions=True)
        else:
            frappe.db.set_value(
                "Role",
                role.name,
                {
                    "desk_access": 1,
                    "home_page": "app/distribution",
                },
            )


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
        "shortcuts": [],
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
