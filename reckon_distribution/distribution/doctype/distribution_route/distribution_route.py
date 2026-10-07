from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.tenant_security import validate_tenant_owned_doc


class DistributionRoute(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
