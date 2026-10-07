from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.tenant_security import validate_tenant_owned_doc


class DistributionSettings(Document):
    def validate(self) -> None:
        validate_tenant_owned_doc(self)
        if self.supplier_goods_policy != "Supplier Provided Goods Only":
            self.supplier_goods_policy = "Supplier Provided Goods Only"
