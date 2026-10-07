from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.collection import validate_collection_receipt


class DSRCollectionReceipt(Document):
    def validate(self) -> None:
        validate_collection_receipt(self)
