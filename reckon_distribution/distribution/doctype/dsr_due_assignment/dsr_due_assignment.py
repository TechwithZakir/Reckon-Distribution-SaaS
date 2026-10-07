from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.due_assignment import validate_due_assignment


class DSRDueAssignment(Document):
    def validate(self) -> None:
        validate_due_assignment(self)
