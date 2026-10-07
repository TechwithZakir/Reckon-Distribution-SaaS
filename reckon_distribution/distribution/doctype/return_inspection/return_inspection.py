from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.delivery import validate_return_inspection


class ReturnInspection(Document):
    def validate(self) -> None:
        validate_return_inspection(self)
