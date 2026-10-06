from __future__ import annotations

from frappe.model.document import Document

from reckon_saas_platform.tenant_security import validate_tenant_owned_doc


class TenantSecurityTestRecord(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
