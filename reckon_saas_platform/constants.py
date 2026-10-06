from __future__ import annotations

from dataclasses import dataclass

SAAS_PLATFORM_WORKSPACE = "Reckon SaaS Admin"


@dataclass(frozen=True)
class PlatformRole:
    name: str
    purpose: str


PLATFORM_ROLES = (
    PlatformRole("Reckon Vendor Superuser", "Vendor SaaS plan and tenant support control"),
)

TENANT_BYPASS_ROLES = frozenset({"Administrator", "System Manager", "Reckon Vendor Superuser"})

SAAS_ACTIVE_STATUSES = frozenset({"Active", "Trial", "Grace"})
SAAS_BLOCKED_STATUSES = frozenset({"Pending", "Due", "Expired", "Suspended", "Cancelled"})
CURRENT_SEED_VERSION = "2026.10.06"
