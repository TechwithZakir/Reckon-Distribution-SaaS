from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TenantUserAssignment(Document):
    def autoname(self) -> None:
        self.name = frappe.model.naming.make_autoname("TUA-.#####")

    def validate(self) -> None:
        self._set_defaults()
        self._validate_company_is_immutable()
        self._validate_unique_active_default()

    def _set_defaults(self) -> None:
        if not self.active:
            self.active = 0
        if not self.is_default:
            self.is_default = 0

    def _validate_company_is_immutable(self) -> None:
        if self.is_new():
            return

        previous_company = frappe.db.get_value(self.doctype, self.name, "company")
        if previous_company and previous_company != self.company:
            frappe.throw(_("Company cannot be changed after tenant assignment is created."))

    def _validate_unique_active_default(self) -> None:
        if not self.active or not self.is_default:
            return

        existing = frappe.db.exists(
            self.doctype,
            {
                "name": ["!=", self.name],
                "user": self.user,
                "active": 1,
                "is_default": 1,
            },
        )
        if existing:
            frappe.throw(_("Only one active default tenant assignment is allowed per user."))
