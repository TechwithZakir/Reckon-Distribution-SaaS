from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.office_expense import validate_office_expense_settings
from reckon_distribution.tenant_security import validate_tenant_owned_doc


class OfficeExpenseSettings(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
        validate_office_expense_settings(self)
