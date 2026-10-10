from __future__ import annotations

import json
from urllib.parse import unquote

import frappe
from frappe import _
from werkzeug.exceptions import HTTPException

from reckon_distribution.constants import OPERATIONAL_ROLES, TENANT_ROLE_NAMES


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
    "warehouse",
    "distribution-route",
    "customer",
    "supplier",
    "item",
    "item-price",
    "distribution-item-uom-setup",
    "price-list",
    "purchase-receipt",
    "purchase-order",
    "purchase-invoice",
    "payment-entry",
    "dsr-challan",
    "print",
    "dsr-collection-receipt",
    "sr-order",
    "outlet-visit",
    "field-sales",
    "dsr-delivery",
    "delivery-note",
    "return-inspection",
    "dsr-day-settlement",
    "user-profile",
    "home",
}
DESK_BYPASS_ROLES = {"Administrator", "System Manager", "Reckon Vendor Superuser"}
ALLOWED_DESK_PREFIXES = (
    "/app/distribution",
    "/app/distribution-master-setup",
    "/app/distribution-settings",
    "/app/warehouse",
    "/app/distribution-route",
    "/app/customer",
    "/app/supplier",
    "/app/item",
    "/app/item-price",
    "/app/distribution-item-uom-setup",
    "/app/price-list",
    "/app/purchase-receipt",
    "/app/purchase-order",
    "/app/purchase-invoice",
    "/app/payment-entry",
    "/app/dsr-challan",
    "/app/print",
    "/app/dsr-collection-receipt",
    "/app/sr-order",
    "/app/outlet-visit",
    "/app/field-sales",
    "/app/dsr-delivery",
    "/app/delivery-note",
    "/app/return-inspection",
    "/app/dsr-day-settlement",
    "/app/user-profile",
    "/app/home",
)

# These are the records a tenant user can reach through generic Frappe list,
# form, link-search, and resource endpoints. Everything else stays behind the
# Distribution workspace boundary, even when a user guesses an API URL.
ALLOWED_DISTRIBUTION_DOCTYPES = frozenset(
    {
        "Company",
        # Native document printing resolves the selected Company letter head.
        "Letter Head",
        "Print Format",
        # Native purchase forms read this singleton while calculating item rates.
        "Buying Settings",
        "Customer",
        "Supplier",
        "Item",
        "Item Price",
        "Price List",
        "UOM",
        "Item Group",
        "Brand",
        "Customer Group",
        "Supplier Group",
        "Territory",
        "Warehouse",
        "Payment Terms Template",
        "Account",
        "Mode of Payment",
        "Bank Account",
        "Currency",
        "Cost Center",
        "Project",
        "Tax Category",
        "Purchase Taxes and Charges Template",
        # Native list/form bootstrapping reads DocType metadata before it
        # loads the requested Distribution document.
        "DocType",
        "Purchase Receipt",
        "Purchase Order",
        "Purchase Invoice",
        "Payment Entry",
        "Purchase Order Item",
        "Purchase Receipt Item",
        "Purchase Invoice Item",
        "Payment Entry Reference",
        "Delivery Note",
        "Stock Entry",
        # Frappe stores saved list filters in this user-scoped metadata DocType.
        # It is required by every native list view and contains no tenant data.
        "List Filter",
        # Link-title lookup uses Language while rendering native forms.
        "Language",
        "User",
        "Distribution Settings",
        "Distribution Route",
        "Company UOM Profile",
        "Company UOM Profile Item",
        "DSR Challan",
        "DSR Challan Item",
        "Van Loading Acknowledgement",
        "Van Loading Acknowledgement Item",
        "DSR Collection Receipt",
        "DSR Due Assignment",
        "Retailer Route Assignment",
        "Outlet Visit",
        "SR Order",
        "SR Order Item",
        "Return Inspection",
        "DSR Day Settlement",
        "DSR Day Settlement Item",
    }
)

GENERIC_DESK_API_PREFIXES = (
    "frappe.client.",
    "frappe.desk.reportview.",
    "frappe.desk.form.",
    "frappe.desk.search.",
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
        return "desk/distribution"
    return None


def restrict_distribution_desk_request() -> None:
    _ensure_current_distribution_role()
    _ensure_current_user_metadata_access()
    if not _is_distribution_only_user():
        return

    from reckon_distribution.warehouse import ensure_current_user_company_permission

    ensure_current_user_company_permission()

    path = _request_path()
    if path.startswith("/api/"):
        _guard_distribution_api_request(path)
        return

    if not path or path in {"/", "/app", "/desk"}:
        _redirect_to_distribution()

    if path.startswith("/app/"):
        app_route = path.removeprefix("/app/").split("/", 1)[0]
        if app_route not in ALLOWED_DISTRIBUTION_PAGES:
            _redirect_to_distribution()

    if path.startswith("/desk/"):
        desk_route = path.removeprefix("/desk/").split("/", 1)[0]
        if desk_route not in ALLOWED_DISTRIBUTION_PAGES:
            _redirect_to_distribution()


def _guard_distribution_api_request(path: str) -> None:
    """Apply the same tenant navigation boundary to generic Desk APIs."""
    if path.startswith("/api/resource/"):
        doctype = unquote(path.removeprefix("/api/resource/").split("/", 1)[0])
        _assert_distribution_doctype(doctype)
        return

    if not path.startswith("/api/method/"):
        return

    method = path.removeprefix("/api/method/")
    if method == "frappe.desk.desk_page.getpage":
        page_name = frappe.local.form_dict.get("page") or frappe.local.form_dict.get("name")
        if page_name not in ALLOWED_DISTRIBUTION_PAGES:
            frappe.throw(_("Page {0} is outside the Distribution workspace.").format(page_name))
        return

    if not method.startswith(GENERIC_DESK_API_PREFIXES):
        return

    doctype = frappe.local.form_dict.get("doctype")
    if not doctype:
        args = frappe.local.form_dict.get("args")
        if isinstance(args, str):
            try:
                doctype = json.loads(args).get("doctype")
            except (TypeError, ValueError, AttributeError):
                doctype = None
    if doctype:
        _assert_distribution_doctype(doctype)


def _assert_distribution_doctype(doctype: str) -> None:
    if doctype not in ALLOWED_DISTRIBUTION_DOCTYPES:
        frappe.throw(
            _("{0} is not available in the Distribution workspace.").format(doctype),
            frappe.PermissionError,
        )


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


def _ensure_current_distribution_role() -> None:
    """Repair the Frappe role from the active tenant assignment before checks."""
    user = frappe.session.user
    if not user or user in {"Guest", "Administrator"}:
        return
    role_map = {
        "Company Admin": "Reckon Distribution Admin",
        "Company Manager": "Reckon Distribution Manager",
        "Master Data Manager": "Reckon Master Data Manager",
        "SR": "Reckon Distribution User",
        "DSR": "Reckon Distribution User",
    }
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return
    profile = frappe.db.get_value(
        "Tenant User Assignment",
        {"user": user, "active": 1, "is_default": 1},
        "role_profile",
    )
    if not profile:
        profile = frappe.db.get_value(
            "Tenant User Assignment",
            {"user": user, "active": 1},
            "role_profile",
        )
    role = role_map.get(profile)
    if not role or role in frappe.get_roles(user):
        return
    frappe.get_doc("User", user).add_roles(role)
    frappe.clear_cache(user=user)


def _ensure_current_user_metadata_access() -> None:
    """Repair the native metadata permission before Desk loads a Distribution list.

    Frappe's native list boot calls permission checks for the ``DocType`` metadata
    record before it can load the requested document. Older tenant users may have
    received their Distribution role before this permission was introduced, so a
    migration alone is not enough for an already-open production site. This is an
    idempotent backfill for the current Distribution role only.
    """
    user = frappe.session.user
    if not user or user in {"Guest", "Administrator"}:
        return
    if not frappe.db.exists("DocType", "DocType"):
        return

    roles = set(frappe.get_roles(user))
    # Resolve the assignment directly as well as the cached User roles. This
    # closes the first-request gap immediately after a tenant user is created
    # or after an older site receives the role backfill during migration.
    role_map = {
        "Company Admin": "Reckon Distribution Admin",
        "Company Manager": "Reckon Distribution Manager",
        "Master Data Manager": "Reckon Master Data Manager",
        "SR": "Reckon Distribution User",
        "DSR": "Reckon Distribution User",
    }
    profile = frappe.db.get_value(
        "Tenant User Assignment",
        {"user": user, "active": 1, "is_default": 1},
        "role_profile",
    )
    if not profile:
        profile = frappe.db.get_value(
            "Tenant User Assignment", {"user": user, "active": 1}, "role_profile"
        )
    if profile:
        roles.add(profile)
        if role_map.get(profile):
            roles.add(role_map[profile])

    distribution_roles = {role.name for role in OPERATIONAL_ROLES} | TENANT_ROLE_NAMES
    applicable_roles = roles.intersection(distribution_roles)
    if not applicable_roles:
        return

    from reckon_distribution.install import ensure_standard_doc_type_read_permission

    for role in applicable_roles:
        ensure_standard_doc_type_read_permission(role)

    frappe.clear_cache(doctype="DocType")
    frappe.clear_cache(user=user)


def _request_path() -> str:
    request = getattr(frappe.local, "request", None)
    if not request:
        return ""
    return request.path or ""


def _redirect_to_distribution() -> None:
    raise DistributionRedirect(f"/{DISTRIBUTION_DESK_ROUTE}")
