from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.van_loading import (
    on_van_loading_acknowledgement_submit,
    validate_van_loading_acknowledgement,
)


class VanLoadingAcknowledgement(Document):
    def validate(self) -> None:
        validate_van_loading_acknowledgement(self)

    def on_submit(self) -> None:
        on_van_loading_acknowledgement_submit(self)
