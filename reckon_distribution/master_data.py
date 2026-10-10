from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _

from reckon_distribution.tenant_security import (
    require_tenant,
    user_can_bypass_tenant,
    validate_tenant_owned_doc,
)

SUPPORTED_MASTER_TYPES = frozenset(
    {
        "Item",
        "Item Group",
        "Brand",
        "Price List",
        "Item Price",
        "Supplier",
        "Customer",
        "Warehouse",
        "Payment Terms Template",
        "Account",
    }
)

SHARED_MASTER_TYPES = {
    "Item": "Item",
    "Supplier": "Supplier",
    "Customer": "Customer",
    "Item Price": "Item Price",
    "Price List": "Price List",
}

COMPANY_OWNED_MASTER_TYPES = frozenset(SHARED_MASTER_TYPES)
MASTER_COMPANY_FIELD = "rd_company"


def get_company_owned_master_registry() -> dict[str, dict[str, str]]:
    """Return the single ownership contract used by migration and validation."""
    return {
        doctype: {"ownership": "company-owned", "company_field": MASTER_COMPANY_FIELD}
        for doctype in sorted(COMPANY_OWNED_MASTER_TYPES)
    }


def get_shared_master_query(user: str | None = None, doctype: str | None = None) -> str:
    """Restrict native ERPNext master lists and link searches to tenant scope."""
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return ""
    master_type = SHARED_MASTER_TYPES.get(doctype or "")
    if not master_type:
        return ""
    tenant = require_tenant(user=user)
    if master_type in COMPANY_OWNED_MASTER_TYPES:
        if not frappe.db.has_column(doctype, MASTER_COMPANY_FIELD):
            return "1=0"
        return f"`tab{doctype}`.`{MASTER_COMPANY_FIELD}` = {frappe.db.escape(tenant.company)}"

    field = "name"
    return (
        f"`tab{doctype}`.`{field}` in ("
        "select master_name from `tabDistribution Master Scope` "
        f"where company = {frappe.db.escape(tenant.company)} "
        f"and master_type = {frappe.db.escape(master_type)} and active = 1)"
    )


def has_shared_master_permission(
    doc,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
    debug: bool = False,
) -> bool:
    """Apply tenant scope to native master reads and mutations."""
    user = user or frappe.session.user
    permission_type = ptype or permission_type
    if user_can_bypass_tenant(user):
        return True
    master_type = SHARED_MASTER_TYPES.get(doc.doctype)
    if not master_type:
        return False
    tenant = require_tenant(user=user)
    if doc.is_new() and permission_type in {"create", "write"}:
        return doc.get(MASTER_COMPANY_FIELD) in (None, "", tenant.company)
    if master_type in COMPANY_OWNED_MASTER_TYPES:
        return (
            frappe.db.get_value(doc.doctype, doc.name, MASTER_COMPANY_FIELD) == tenant.company
            and doc.get(MASTER_COMPANY_FIELD) == tenant.company
        )
    if not frappe.db.exists(
        "Distribution Master Scope",
        {"company": tenant.company, "master_type": master_type, "master_name": doc.name, "active": 1},
    ):
        return False
    if permission_type in {"write", "delete", "submit", "cancel", "amend"}:
        other_company_scope = frappe.db.exists(
            "Distribution Master Scope",
            {
                "master_type": master_type,
                "master_name": doc.name,
                "company": ["!=", tenant.company],
                "active": 1,
            },
        )
        return not other_company_scope
    return True


def auto_scope_shared_master(doc, method=None) -> None:
    """Bind a native master created by a tenant user to that user's Company."""
    if user_can_bypass_tenant() or not doc.is_new() and frappe.db.exists(
        "Distribution Master Scope", {"master_type": SHARED_MASTER_TYPES.get(doc.doctype), "master_name": doc.name}
    ):
        return
    master_type = SHARED_MASTER_TYPES.get(doc.doctype)
    if not master_type:
        return
    tenant = require_tenant()
    if master_type in COMPANY_OWNED_MASTER_TYPES:
        other_company = frappe.db.exists(
            "Distribution Master Scope",
            {
                "master_type": master_type,
                "master_name": doc.name,
                "company": ["!=", tenant.company],
                "active": 1,
            },
        )
        if other_company:
            frappe.throw(
                _("{0} {1} is already owned by another Company.").format(master_type, doc.name),
                frappe.PermissionError,
            )
    scope_name = frappe.db.exists(
        "Distribution Master Scope",
        {"company": tenant.company, "master_type": master_type, "master_name": doc.name},
    )
    if not scope_name:
        frappe.get_doc(
            {
                "doctype": "Distribution Master Scope",
                "company": tenant.company,
                "master_type": master_type,
                "master_name": doc.name,
                "access_scope": "Manage",
                "active": 1,
            }
        ).insert()


def normalize_item_code(doc, method=None) -> None:
    """Use the business-facing Item Name as the unique ERPNext Item Code."""
    if doc.doctype != "Item" or user_can_bypass_tenant() or not doc.get("item_name"):
        return
    desired_code = doc.item_name.strip()
    if not frappe.db.has_column("Item", MASTER_COMPANY_FIELD):
        doc.item_code = desired_code
        return
    existing = frappe.db.get_value(
        "Item", desired_code, ["name", MASTER_COMPANY_FIELD], as_dict=True
    )
    if not existing or existing.name == doc.name:
        doc.item_code = desired_code
        return

    # ERPNext Item Code is globally unique. Keep the same business name while
    # giving a second Company's item a deterministic native code.
    tenant = require_tenant()
    abbr = frappe.db.get_value("Company", tenant.company, "abbr") or tenant.company
    base_code = f"{abbr}-{desired_code}"
    candidate = base_code
    suffix = 2
    while frappe.db.exists("Item", candidate) and candidate != doc.name:
        candidate = f"{base_code}-{suffix}"
        suffix += 1
    doc.item_code = candidate


def validate_shared_master_change(doc, method=None) -> None:
    if user_can_bypass_tenant():
        return
    if doc.doctype in COMPANY_OWNED_MASTER_TYPES:
        tenant = require_tenant()
        if not doc.is_new():
            stored_company = frappe.db.get_value(doc.doctype, doc.name, MASTER_COMPANY_FIELD)
            if stored_company != tenant.company:
                frappe.throw(_("This master is not owned by your Company."), frappe.PermissionError)
        if not doc.get(MASTER_COMPANY_FIELD):
            doc.set(MASTER_COMPANY_FIELD, tenant.company)
        elif doc.get(MASTER_COMPANY_FIELD) != tenant.company:
            frappe.throw(
                _("This {0} belongs to Company {1}, not {2}.").format(
                    doc.doctype, doc.get(MASTER_COMPANY_FIELD), tenant.company
                ),
                frappe.PermissionError,
            )
        if doc.doctype == "Item Price":
            if doc.get("item_code"):
                validate_master_scope(tenant.company, "Item", doc.item_code)
            if doc.get("price_list"):
                validate_master_scope(tenant.company, "Price List", doc.price_list)
        return
    if not doc.is_new() and not has_shared_master_permission(doc, permission_type="write"):
        frappe.throw(_("This master is not editable for your Company."), frappe.PermissionError)


def validate_master_reference(doc) -> None:
    validate_tenant_owned_doc(doc)
    if doc.master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(doc.master_type))
    if not frappe.db.exists(doc.master_type, doc.master_name):
        frappe.throw(_("{0} {1} does not exist.").format(doc.master_type, doc.master_name))
    if (
        doc.master_type in COMPANY_OWNED_MASTER_TYPES
        and frappe.db.has_column(doc.master_type, MASTER_COMPANY_FIELD)
    ):
        linked_company = frappe.db.get_value(doc.master_type, doc.master_name, MASTER_COMPANY_FIELD)
        if linked_company != doc.company:
            frappe.throw(
                _("{0} {1} belongs to Company {2}, not {3}.").format(
                    doc.master_type, doc.master_name, linked_company, doc.company
                ),
                frappe.PermissionError,
            )
    duplicate = frappe.db.exists(
        "Distribution Master Scope",
        {
            "company": doc.company,
            "master_type": doc.master_type,
            "master_name": doc.master_name,
            "name": ["!=", doc.name],
        },
    )
    if duplicate:
        frappe.throw(
            _("{0} {1} is already enabled for company {2}.").format(
                doc.master_type, doc.master_name, doc.company
            )
        )


def validate_master_scope(
    company: str, master_type: str, master_name: str, user: str | None = None
) -> None:
    tenant = require_tenant(user=user, company=company)
    if master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(master_type))
    if not frappe.db.exists(master_type, master_name):
        frappe.throw(_("{0} {1} does not exist.").format(master_type, master_name))
    if master_type in COMPANY_OWNED_MASTER_TYPES and frappe.db.has_column(master_type, MASTER_COMPANY_FIELD):
        linked_company = frappe.db.get_value(master_type, master_name, MASTER_COMPANY_FIELD)
        if linked_company == tenant.company:
            return
        frappe.throw(
            _("{0} {1} belongs to Company {2}, not {3}.").format(
                master_type, master_name, linked_company or _("another Company"), tenant.company
            )
        )
    if not frappe.db.exists(
        "Distribution Master Scope",
        {
            "company": tenant.company,
            "master_type": master_type,
            "master_name": master_name,
            "active": 1,
        },
    ):
        frappe.throw(
            _("{0} {1} is not enabled for company {2}.").format(
                master_type, master_name, tenant.company
            )
        )


@frappe.whitelist()
def search_company_master(
    master_type: str,
    txt: str = "",
    user: str | None = None,
    fields: Iterable[str] | None = None,
) -> list[dict]:
    if user and user != frappe.session.user and not user_can_bypass_tenant():
        frappe.throw(_("You cannot search masters as another user."), frappe.PermissionError)
    tenant = require_tenant(user=user)
    if master_type not in SUPPORTED_MASTER_TYPES:
        frappe.throw(_("Unsupported distribution master type: {0}").format(master_type))
    selected_fields = list(fields or ["company", "master_name", "master_type", "access_scope"])
    if "company" not in selected_fields:
        selected_fields.insert(0, "company")
    if "master_name" not in selected_fields:
        selected_fields.insert(0, "master_name")
    if master_type in COMPANY_OWNED_MASTER_TYPES and frappe.db.has_column(master_type, MASTER_COMPANY_FIELD):
        rows = frappe.get_all(
            master_type,
            filters={MASTER_COMPANY_FIELD: tenant.company, "name": ["like", f"%{txt}%"]},
            fields=["name as master_name"],
            order_by="name asc",
        )
        for row in rows:
            row.update({"company": tenant.company, "master_type": master_type, "access_scope": "Manage"})
        return rows

    return frappe.get_all(
        "Distribution Master Scope",
        filters={
            "company": tenant.company,
            "master_type": master_type,
            "active": 1,
            "master_name": ["like", f"%{txt}%"],
        },
        fields=selected_fields,
        order_by="master_name asc",
    )


@frappe.whitelist()
def assert_company_master(company: str, master_type: str, master_name: str) -> dict:
    validate_master_scope(company, master_type, master_name)
    return {"company": company, "master_type": master_type, "master_name": master_name}


@frappe.whitelist()
def get_master_ownership_conflicts() -> list[dict]:
    """Return unresolved native-master ownership for administrator diagnostics."""
    if not user_can_bypass_tenant():
        frappe.throw(_("Only a system administrator can inspect ownership conflicts."), frappe.PermissionError)

    conflicts = []
    for doctype, master_type in SHARED_MASTER_TYPES.items():
        if not frappe.db.exists("DocType", doctype) or not frappe.db.has_column(
            doctype, MASTER_COMPANY_FIELD
        ):
            continue
        for record in frappe.get_all(doctype, fields=["name", MASTER_COMPANY_FIELD]):
            companies = sorted(
                set(
                    frappe.get_all(
                        "Distribution Master Scope",
                        filters={
                            "master_type": master_type,
                            "master_name": record.name,
                            "active": 1,
                        },
                        pluck="company",
                    )
                )
            )
            if not record.get(MASTER_COMPANY_FIELD) or len(companies) > 1:
                conflicts.append(
                    {
                        "doctype": doctype,
                        "name": record.name,
                        "company": record.get(MASTER_COMPANY_FIELD),
                        "scoped_companies": ", ".join(companies),
                        "reason": "multiple scope companies" if len(companies) > 1 else "missing Company owner",
                    }
                )
    return conflicts
