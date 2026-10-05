from __future__ import annotations

from dataclasses import dataclass

DISTRIBUTION_WORKSPACE = "Distribution"


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

HRMS_APP_NAME = "hrms"
