from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.field_sales import validate_outlet_visit


class OutletVisit(Document):
    def validate(self) -> None:
        validate_outlet_visit(self)
