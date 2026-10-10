from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.van_loading import (
    cancel_van_loading_stock_entry,
    create_van_loading_stock_entry,
    validate_van_loading_challan,
)


class DSRChallan(Document):
    def validate(self) -> None:
        validate_van_loading_challan(self)

    def on_submit(self) -> None:
        create_van_loading_stock_entry(self)

    def on_cancel(self) -> None:
        cancel_van_loading_stock_entry(self)
