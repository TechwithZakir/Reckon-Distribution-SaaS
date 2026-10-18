from __future__ import annotations

import json
from urllib.parse import quote, unquote

import frappe
from frappe import _
from reckon_saas_platform.saas_gate import is_user_gated

from reckon_distribution.constants import (
    OPERATIONAL_ROLES,
    TENANT_PROFILE_ROLE_MAP,
    TENANT_ROLE_NAMES,
)

DISTRIBUTION_DESK_ROUTE = "desk/distribution"
DISTRIBUTION_PAGE = "distribution"
DISTRIBUTION_USER_ROLES = frozenset(
    {role.name for role in OPERATIONAL_ROLES} | set(TENANT_ROLE_NAMES)
)
DISTRIBUTION_QUERY_REPORTS = frozenset(
    {
        "Stock Ledger",
        "Stock Balance",
        "Distribution Sales Register",
        "Distribution Purchase Register",
        "Accounting Ledger",
        "Day Book",
        "Cash Book",
        "Supplier Ledger",
        "Supplier Aging Report",
        "Customer Aging Report",
        "DSR Wise Ledger",
        "Ledger Summary",
        "Profit & Loss",
    }
)
DISTRIBUTION_MANAGEMENT_ROLES = frozenset(
    {
        "Reckon Distribution Admin",
        "Reckon Distribution Manager",
        "Company Admin",
        "Company Manager",
    }
)
DISTRIBUTION_MANAGEMENT_QUERY_REPORTS = frozenset(
    {
        "Distribution Sales Register",
        "Distribution Purchase Register",
        "Accounting Ledger",
        "Day Book",
        "Cash Book",
        "Supplier Ledger",
        "Supplier Aging Report",
        "Customer Aging Report",
        "DSR Wise Ledger",
        "Ledger Summary",
        "Profit & Loss",
    }
)
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
    "office-expense",
    "office-expense-settings",
    "query-report",
    "user-profile",
    "home",
}
DESK_BYPASS_ROLES = {"Administrator", "Reckon Vendor Superuser"}
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
    "/app/office-expense",
    "/app/office-expense-settings",
    "/app/query-report",
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
        # These accounting records are report dependencies only. Their report
        # and generic API access is tenant-scoped by the hooks in hooks.py;
        # the corresponding Desk pages remain outside the allowed page list.
        "GL Entry",
        "Payment Ledger Entry",
        "Sales Invoice",
        "Journal Entry",
        "Delivery Note",
        "Stock Entry",
        "Stock Reconciliation",
        "Stock Ledger Entry",
        "Report",
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
        "DSR Day Settlement Payment",
        "Office Expense",
        "Office Expense Item",
        "Office Expense Settings",
        "Office Expense Category Setup",
        "Office Expense Payment Setup",
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
        if is_user_gated(user):
            return "reckonerp-subscription"
        return "desk/distribution"
    return None


def restrict_distribution_desk_request() -> None:
    """Read-only Desk boundary for tenant users; it must not write or clear caches."""
    if getattr(frappe.flags, "saas_gate_blocked", False):
        # The SaaS subscription gate has already rejected or redirected this request.
        return
    if not _is_distribution_only_user():
        return

    from reckon_distribution.warehouse import assert_single_company_assignment

    assert_single_company_assignment()

    path = _request_path()
    if path.startswith("/api/"):
        _guard_distribution_api_request(path)
        return

    if not path or path.rstrip("/") in {"", "/app", "/desk"}:
        _redirect_to_distribution()

    if path.startswith("/app/"):
        app_route = path.removeprefix("/app/").split("/", 1)[0]
        if app_route not in ALLOWED_DISTRIBUTION_PAGES:
            _redirect_to_distribution()

    if path.startswith("/desk/"):
        desk_path = path.removeprefix("/desk/")
        desk_route = desk_path.split("/", 1)[0]
        if desk_route not in ALLOWED_DISTRIBUTION_PAGES:
            _redirect_to_distribution()
        if desk_route == "query-report":
            report_name = unquote(desk_path.removeprefix("query-report/")).strip("/")
            if report_name == "Sales Register":
                _redirect_to_distribution_report("Distribution Sales Register")
                return
            if report_name == "Purchase Register":
                _redirect_to_distribution_report("Distribution Purchase Register")
                return
            if not _can_access_distribution_report(report_name):
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

    if method.startswith("frappe.desk.query_report."):
        _assert_distribution_report()
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


def _assert_distribution_report() -> None:
    report_name = frappe.local.form_dict.get("report_name") or frappe.local.form_dict.get("report")
    if not report_name:
        args = frappe.local.form_dict.get("args")
        if isinstance(args, str):
            try:
                values = json.loads(args)
                report_name = values.get("report_name") or values.get("report")
            except (TypeError, ValueError, AttributeError):
                report_name = None
    if not _can_access_distribution_report(report_name):
        frappe.throw(
            _("Report {0} is not available in the Distribution workspace.").format(
                report_name or _("requested report")
            ),
            frappe.PermissionError,
        )


def _can_access_distribution_report(report_name: str | None) -> bool:
    if report_name not in DISTRIBUTION_QUERY_REPORTS:
        return False
    if report_name not in DISTRIBUTION_MANAGEMENT_QUERY_REPORTS:
        return True
    roles = set(frappe.get_roles())
    return bool(roles.intersection(DISTRIBUTION_MANAGEMENT_ROLES | DESK_BYPASS_ROLES))


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
    # A Distribution tenant admin may also have System Manager for operational
    # setup. Their tenant role must take precedence for root and Desk routing.
    if roles.intersection(DISTRIBUTION_USER_ROLES):
        return True
    if "System Manager" in roles:
        return False

    # Login can route a user before the Tenant User Assignment role sync has
    # reached Frappe's cached User roles. Read the assignment directly so the
    # first request still enters the Distribution workspace.
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return False
    profile = frappe.db.get_value(
        "Tenant User Assignment",
        {"user": user, "active": 1, "is_default": 1},
        "role_profile",
    ) or frappe.db.get_value(
        "Tenant User Assignment", {"user": user, "active": 1}, "role_profile"
    )
    return profile in TENANT_ROLE_NAMES


def sync_tenant_user_access(doc, method=None) -> None:
    """Grant the Frappe role and DocType metadata access for a tenant assignment.

    Runs from the Tenant User Assignment ``on_update`` hook; ``after_migrate``
    backfills existing users. Requests never repair access themselves, so they do
    not write to ``tabDocPerm``/``tabHas Role`` or clear caches.
    """
    user = doc.get("user")
    if not doc.get("active") or not user or user in {"Guest", "Administrator"}:
        return
    profile = doc.get("role_profile")
    role = TENANT_PROFILE_ROLE_MAP.get(profile)
    distribution_roles = {row.name for row in OPERATIONAL_ROLES} | set(TENANT_ROLE_NAMES)

    from reckon_distribution.install import ensure_standard_doc_type_read_permission

    metadata_changed = False
    for name in {profile, role}.intersection(distribution_roles):
        metadata_changed = ensure_standard_doc_type_read_permission(name) or metadata_changed
    if metadata_changed:
        frappe.clear_cache(doctype="DocType")

    if role and frappe.db.exists("User", user) and role not in frappe.get_roles(user):
        # add_roles saves the User, which clears that user's cache.
        frappe.get_doc("User", user).add_roles(role)


def _request_path() -> str:
    request = getattr(frappe.local, "request", None)
    if not request:
        return ""
    return request.path or ""


def _redirect_to_distribution() -> None:
    """Schedule a redirect after Frappe has built the website/Desk response.

    Frappe executes ``before_request`` before its web response handler is
    active. Raising a redirect there is therefore rendered as a 500. An
    after-request hook can safely replace the completed response with a 302.
    """
    frappe.flags.distribution_redirect = f"/{DISTRIBUTION_DESK_ROUTE}"


def _redirect_to_distribution_report(report_name: str) -> None:
    """Redirect replaced native report routes to their Distribution equivalent."""
    frappe.flags.distribution_redirect = f"/desk/query-report/{quote(report_name)}"


def redirect_distribution_desk_response(response, request) -> None:
    """Turn a scheduled tenant-entry redirect into a normal HTTP response."""
    location = getattr(frappe.flags, "distribution_redirect", None)
    if getattr(frappe.flags, "saas_gate_redirect", None):
        # The subscription gate's redirect wins over workspace routing.
        return
    if not location or response is None:
        return
    response.status_code = 302
    response.headers["Location"] = location
    response.set_data(b"")
