from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.master_data import validate_master_reference


class DistributionMasterScope(Document):
    def validate(self) -> None:
        validate_master_reference(self)
