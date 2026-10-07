from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.van_loading import validate_van_loading_challan


class VanLoadingChallan(Document):
    def validate(self) -> None:
        validate_van_loading_challan(self)
