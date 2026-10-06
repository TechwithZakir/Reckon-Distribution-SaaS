from __future__ import annotations

import frappe
from frappe.model.document import Document


class SaaSSubscription(Document):
    def autoname(self) -> None:
        self.name = frappe.model.naming.make_autoname("SUB-.#####")

    def validate(self) -> None:
        if not self.is_new():
            previous_price = frappe.db.get_value(self.doctype, self.name, "price")
            previous_plan_version = frappe.db.get_value(self.doctype, self.name, "plan_version")
            if previous_price is not None and float(previous_price) != float(self.price or 0):
                frappe.throw("Subscription price is preserved for the billing period.")
            if previous_plan_version and previous_plan_version != self.plan_version:
                frappe.throw("Subscription plan version is preserved for the billing period.")
