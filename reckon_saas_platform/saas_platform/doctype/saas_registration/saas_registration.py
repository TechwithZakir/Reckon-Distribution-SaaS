from __future__ import annotations

import frappe
from frappe.model.document import Document


class SaaSRegistration(Document):
    def autoname(self) -> None:
        self.name = frappe.model.naming.make_autoname("REG-.#####")
