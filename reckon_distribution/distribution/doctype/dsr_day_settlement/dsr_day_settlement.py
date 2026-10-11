from __future__ import annotations

import frappe
from frappe.model.document import Document

from reckon_distribution.settlement import validate_day_settlement


class DSRDaySettlement(Document):
    def validate(self) -> None:
        validate_day_settlement(self)

    def after_insert(self) -> None:
        frappe.db.set_value(
            "DSR Challan", self.challan, "day_settlement", self.name, update_modified=False
        )
