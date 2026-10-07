from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.settlement import validate_day_settlement


class DSRDaySettlement(Document):
    def validate(self) -> None:
        validate_day_settlement(self)
