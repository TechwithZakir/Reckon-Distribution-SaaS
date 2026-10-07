from __future__ import annotations

from frappe.model.document import Document

from reckon_distribution.route_assignment import validate_route_assignment


class RetailerRouteAssignment(Document):
    def validate(self) -> None:
        validate_route_assignment(self)
