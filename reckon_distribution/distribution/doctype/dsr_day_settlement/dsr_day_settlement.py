from __future__ import annotations

import frappe
from frappe.model.document import Document

from reckon_distribution.settlement import (
    cancel_day_settlement_postings,
    clear_day_settlement_link,
    post_day_settlement,
    prepare_day_settlement_submission,
    validate_day_settlement,
)


class DSRDaySettlement(Document):
    def validate(self) -> None:
        validate_day_settlement(self)

    def before_submit(self) -> None:
        prepare_day_settlement_submission(self)

    def on_submit(self) -> None:
        post_day_settlement(self)

    def on_cancel(self) -> None:
        cancel_day_settlement_postings(self)

    def after_insert(self) -> None:
        frappe.db.set_value(
            "DSR Challan", self.challan, "day_settlement", self.name, update_modified=False
        )

    def on_trash(self) -> None:
        clear_day_settlement_link(self)
