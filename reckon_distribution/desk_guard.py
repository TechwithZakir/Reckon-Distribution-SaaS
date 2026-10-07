from __future__ import annotations

import frappe
from frappe import _

from reckon_distribution.constants import OPERATIONAL_ROLES

DISTRIBUTION_DESK_ROUTE = "app/distribution"
DISTRIBUTION_PAGE = "distribution"
DESK_BYPASS_ROLES = {"Administrator", "System Manager", "Reckon Vendor Superuser"}
ALLOWED_DESK_PREFIXES = (
    "/app/distribution",
    "/app/user-profile",
    "/app/user",
    "/app/home",
)
ALLOWED_WEBSITE_PREFIXES = (
    "/reckonerp-subscription",
    "/reckonerp-signup",
    "/login",
    "/logout",
    "/api/",
    "/assets/",
    "/files/",
    "/private/",
)


def get_user_home_page(user: str):
    if _is_distribution_only_user(user):
        return DISTRIBUTION_DESK_ROUTE
    return None


def restrict_distribution_desk_request() -> None:
    if not _is_distribution_only_user():
        return

    path = _request_path()
    if not path or path == "/app":
        _redirect_to_distribution()

    if path.startswith("/app/") and not path.startswith(ALLOWED_DESK_PREFIXES):
        _redirect_to_distribution()

    if path.startswith("/desk/") and path != f"/desk/{DISTRIBUTION_PAGE}":
        _redirect_to_distribution()


@frappe.whitelist()
def getpage(page):
    if _is_distribution_only_user() and page != DISTRIBUTION_PAGE:
        frappe.throw(_("Page {0} not found").format(page), frappe.DoesNotExistError)

    from frappe.desk.desk_page import getpage as frappe_getpage

    return frappe_getpage(page)


@frappe.whitelist()
def get_restricted_desk_context() -> dict:
    return {
        "restricted": _is_distribution_only_user(),
        "route": DISTRIBUTION_DESK_ROUTE,
    }


def _is_distribution_only_user(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    roles = set(frappe.get_roles(user))
    if roles.intersection(DESK_BYPASS_ROLES):
        return False
    return any(role.name in roles for role in OPERATIONAL_ROLES)


def _request_path() -> str:
    request = getattr(frappe.local, "request", None)
    if not request:
        return ""
    return request.path or ""


def _redirect_to_distribution() -> None:
    frappe.local.flags.redirect_location = f"/{DISTRIBUTION_DESK_ROUTE}"
    raise frappe.Redirect
