from __future__ import annotations

from dataclasses import dataclass

DISTRIBUTION_WORKSPACE = "Distribution Workspace"
DISTRIBUTION_SIDEBAR = "Distribution"


@dataclass(frozen=True)
class AppRole:
    name: str
    purpose: str


OPERATIONAL_ROLES = (
    AppRole("Reckon Distribution Admin", "Company-scoped setup and user administration"),
    AppRole("Reckon Distribution Manager", "Company-scoped operational management"),
    AppRole("Reckon Distribution User", "SR/DSR field operations"),
    AppRole("Reckon Vendor Superuser", "Vendor SaaS plan and tenant support control"),
    AppRole("Reckon Master Data Manager", "Scoped master-data maintenance"),
)

# Tenant-facing role profile names used by the SaaS/team-access flows. Some
# existing sites retain these names as actual Frappe Roles, while newer users
# receive the internal Reckon Distribution roles above.
TENANT_ROLE_NAMES = frozenset({"Company Admin", "Company Manager", "DSR", "SR", "Master Data Manager"})

HRMS_APP_NAME = "hrms"

TENANT_BYPASS_ROLES = frozenset({"Administrator", "System Manager", "Reckon Vendor Superuser"})

SAAS_ACTIVE_STATUSES = frozenset({"Active", "Trial", "Grace"})
SAAS_BLOCKED_STATUSES = frozenset({"Pending", "Due", "Expired", "Suspended", "Cancelled"})
CURRENT_SEED_VERSION = "2026.10.06"
