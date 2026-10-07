from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.field_sales import validate_sr_order


class SROrder(Document):
    def validate(self) -> None:
        validate_sr_order(self)
        for row in self.items:
            row.amount = row.qty * row.rate
