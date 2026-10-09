from __future__ import annotations

import frappe
from frappe.model.document import Document

from reckon_distribution.master_data import validate_master_scope
from reckon_distribution.tenant_security import user_can_bypass_tenant, validate_tenant_owned_doc


class DistributionSettings(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
        if self.supplier_goods_policy != "Supplier Provided Goods Only":
            self.supplier_goods_policy = "Supplier Provided Goods Only"

        if not user_can_bypass_tenant():
            for fieldname, master_type in (
                ("default_price_list", "Price List"),
                ("default_payment_terms_template", "Payment Terms Template"),
            ):
                master_name = self.get(fieldname)
                if master_name:
                    validate_master_scope(self.company, master_type, master_name)

            for fieldname, doctype in (
                ("default_warehouse", "Warehouse"),
                ("default_receivable_account", "Account"),
                ("default_cash_account", "Account"),
            ):
                master_name = self.get(fieldname)
                if not master_name:
                    continue
                linked_company = frappe.db.get_value(doctype, master_name, "company")
                if linked_company != self.company:
                    frappe.throw(
                        frappe._("{0} {1} belongs to Company {2}, not {3}.").format(
                            doctype, master_name, linked_company or frappe._("another Company"), self.company
                        )
                    )

        if self.default_uom_profile:
            profile_company = frappe.db.get_value(
                "Company UOM Profile", self.default_uom_profile, "company"
            )
            if profile_company != self.company:
                frappe.throw(
                    frappe._("UOM Profile {0} is not assigned to Company {1}.").format(
                        self.default_uom_profile, self.company
                    )
                )
