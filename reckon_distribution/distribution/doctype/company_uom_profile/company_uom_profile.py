from __future__ import annotations

import frappe
from frappe.model.document import Document

from reckon_distribution.tenant_security import validate_tenant_owned_doc


class CompanyUOMProfile(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
        seen = set()
        for row in self.units:
            if row.uom in seen:
                frappe.throw(frappe._("UOM {0} is repeated in this profile.").format(row.uom))
            seen.add(row.uom)
