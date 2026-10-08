from __future__ import annotations

import frappe
from frappe import _
from werkzeug.exceptions import HTTPException

from reckon_distribution.constants import OPERATIONAL_ROLES


class DistributionRedirect(HTTPException):
    """Version-independent HTTP redirect for Frappe's before-request hook."""

    code = 302
    description = "Redirecting to the Distribution workspace."

    def __init__(self, location: str):
        super().__init__()
        self.location = location

    def get_headers(self, environ=None):
        headers = super().get_headers(environ)
        headers.append(("Location", self.location))
        return headers

DISTRIBUTION_DESK_ROUTE = "desk/distribution"
DISTRIBUTION_PAGE = "distribution"
ALLOWED_DISTRIBUTION_PAGES = {
    "distribution",
    "distribution-master-setup",
    "distribution-team-access",
    "distribution-settings",
    "company-uom-profile",
    "distribution-route",
    "distribution-master-scope",
    "customer",
    "supplier",
    "item",
    "item-price",
    "price-list",
    "purchase-receipt",
    "van-loading",
    "van-loading-challan",
    "van-loading-acknowledgement",
    "dsr-collection-receipt",
    "sr-order",
    "outlet-visit",
    "field-sales",
    "delivery-note",
    "return-inspection",
    "dsr-day-settlement",
    "user-profile",
    "user",
    "home",
}
DESK_BYPASS_ROLES = {"Administrator", "System Manager", "Reckon Vendor Superuser"}
ALLOWED_DESK_PREFIXES = (
    "/app/distribution",
    "/app/distribution-master-setup",
    "/app/distribution-settings",
    "/app/company-uom-profile",
    "/app/distribution-route",
    "/app/distribution-master-scope",
    "/app/customer",
    "/app/supplier",
    "/app/item",
    "/app/item-price",
    "/app/price-list",
    "/app/purchase-receipt",
    "/app/van-loading",
    "/app/van-loading-challan",
    "/app/van-loading-acknowledgement",
    "/app/dsr-collection-receipt",
    "/app/sr-order",
    "/app/outlet-visit",
    "/app/field-sales",
    "/app/delivery-note",
    "/app/return-inspection",
    "/app/dsr-day-settlement",
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

    if path.startswith("/desk/") and path.removeprefix("/desk/") not in ALLOWED_DISTRIBUTION_PAGES:
        _redirect_to_distribution()


@frappe.whitelist()
def getpage(page: str | None = None, name: str | None = None):
    page_name = page or name
    if _is_distribution_only_user() and page_name not in ALLOWED_DISTRIBUTION_PAGES:
        frappe.throw(_("Page {0} not found").format(page_name), frappe.DoesNotExistError)

    from frappe.desk.desk_page import getpage as frappe_getpage

    return frappe_getpage(page_name)


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
    raise DistributionRedirect(f"/{DISTRIBUTION_DESK_ROUTE}")
