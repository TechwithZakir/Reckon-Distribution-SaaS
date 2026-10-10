from __future__ import annotations

import frappe
from frappe import _, permissions

from reckon_distribution.constants import (
    DISTRIBUTION_SIDEBAR,
    DISTRIBUTION_WORKSPACE,
    OPERATIONAL_ROLES,
    TENANT_ROLE_NAMES,
)


def after_install() -> None:
    setup_roles()
    ensure_company_owned_master_fields()
    ensure_company_sales_price_lists()
    ensure_distribution_permissions()
    setup_workspace()
    remove_legacy_challan_pages()
    ensure_purchase_receipt_fields()
    ensure_procurement_setting_defaults()
    ensure_simplified_procurement_layout()
    reload_distribution_layout_doctypes()
    ensure_dense_layout_fields()
    ensure_master_quick_entry()


def after_migrate() -> None:
    setup_roles()
    ensure_company_owned_master_fields()
    ensure_company_sales_price_lists()
    ensure_distribution_permissions()
    setup_workspace()
    remove_legacy_challan_pages()
    ensure_purchase_receipt_fields()
    ensure_procurement_setting_defaults()
    ensure_simplified_procurement_layout()
    reload_distribution_layout_doctypes()
    ensure_dense_layout_fields()
    ensure_master_quick_entry()


def ensure_company_sales_price_lists() -> None:
    """Repair the selling Price List default for every configured tenant."""
    if not all(
        frappe.db.exists("DocType", doctype)
        for doctype in ("Distribution Settings", "Price List")
    ):
        return

    from reckon_distribution.master_data import get_or_create_company_sales_price_list

    for company in frappe.get_all("Distribution Settings", pluck="company"):
        get_or_create_company_sales_price_list(company)


def ensure_master_quick_entry() -> None:
    """Keep native ERPNext master creation compact for distribution users."""
    configurations = {
        "Customer": {"customer_name", "customer_type", "customer_group", "territory"},
        "Supplier": {"supplier_name", "supplier_type", "supplier_group"},
        "Item": {"item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item"},
        "Item Price": {"item_code", "price_list", "price_list_rate", "uom", "selling"},
    }
    for doctype, allowed_fields in configurations.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        _set_property(doctype, None, "quick_entry", "1", "Check")
        for field in frappe.get_meta(doctype).fields:
            if not field.fieldname:
                continue
            _set_property(
                doctype,
                field.fieldname,
                "allow_in_quick_entry",
                "1" if field.fieldname in allowed_fields else "0",
                "Check",
            )
        if doctype == "Item":
            _set_property("Item", "item_code", "read_only", "1", "Check")
            _set_property("Item", "item_code", "reqd", "0", "Check")
        frappe.clear_cache(doctype=doctype)


def _set_property(doctype: str, fieldname: str | None, property_name: str, value: str, property_type: str) -> None:
    filters = {
        "doc_type": doctype,
        "doctype_or_field": "DocType" if fieldname is None else "DocField",
        "property": property_name,
    }
    if fieldname is not None:
        filters["field_name"] = fieldname
    name = frappe.db.exists("Property Setter", filters)
    values = {
        "doctype": "Property Setter",
        "doc_type": doctype,
        "doctype_or_field": filters["doctype_or_field"],
        "property": property_name,
        "value": value,
        "property_type": property_type,
        "is_system_generated": 1,
    }
    if fieldname is not None:
        values["field_name"] = fieldname
    setter = frappe.get_doc("Property Setter", name) if name else frappe.get_doc(values)
    setter.update(values)
    setter.save(ignore_permissions=True) if setter.name else setter.insert(ignore_permissions=True)


def remove_legacy_challan_pages() -> None:
    """Remove obsolete challan launchers and references after the DSR rename."""
    removed = False
    for page_name in ("van-loading",):
        if frappe.db.exists("Page", page_name):
            frappe.delete_doc("Page", page_name, force=True, ignore_permissions=True)
            removed = True
    for setter_name in frappe.get_all(
        "Property Setter", filters={"doc_type": "Van Loading Challan"}, pluck="name"
    ):
        frappe.delete_doc("Property Setter", setter_name, force=True, ignore_permissions=True)
        removed = True
    for field_name in frappe.get_all(
        "Custom Field", filters={"options": "Van Loading Challan"}, pluck="name"
    ):
        frappe.delete_doc("Custom Field", field_name, force=True, ignore_permissions=True)
        removed = True
    for setter_name in frappe.get_all(
        "Property Setter", filters={"value": "Van Loading Challan"}, pluck="name"
    ):
        frappe.delete_doc("Property Setter", setter_name, force=True, ignore_permissions=True)
        removed = True
    if removed:
        frappe.clear_cache()


def ensure_purchase_receipt_fields() -> None:
    fields = [
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_source",
            "label": "Supplier Promotion Source",
            "fieldtype": "Data",
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_purchase_invoice",
            "label": "Generated Purchase Invoice",
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "read_only": 1,
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_invoice_status",
            "label": "Supplier Invoice Status",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "rd_purchase_invoice",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_invoice_created_on",
            "label": "Invoice Created On",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "rd_invoice_status",
        },
        {
            "dt": "Purchase Invoice",
            "fieldname": "rd_source_purchase_receipt",
            "label": "Source Purchase Receipt",
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "read_only": 1,
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_reference",
            "label": "Supplier Promotion Reference",
            "fieldtype": "Data",
            "insert_after": "rd_promotion_source",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "rd_promotion_terms",
            "label": "Supplier Promotion Terms",
            "fieldtype": "Small Text",
            "insert_after": "rd_promotion_reference",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_paid_qty",
            "label": "Paid Quantity",
            "fieldtype": "Float",
            "insert_after": "qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_free_qty",
            "label": "Supplier Free Quantity",
            "fieldtype": "Float",
            "insert_after": "rd_paid_qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_shortage_qty",
            "label": "Shortage Quantity",
            "fieldtype": "Float",
            "insert_after": "rd_free_qty",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "rd_dispute_note",
            "label": "Shortage / Dispute Note",
            "fieldtype": "Small Text",
            "insert_after": "rd_shortage_qty",
        },
        {
            "dt": "Stock Entry",
            "fieldname": "rd_van_loading_challan",
            "label": "DSR Challan",
            "fieldtype": "Link",
            "options": "DSR Challan",
            "read_only": 1,
            "insert_after": "stock_entry_type",
        },
        {
            "dt": "Payment Entry",
            "fieldname": "rd_collection_receipt",
            "label": "DSR Collection Receipt",
            "fieldtype": "Link",
            "options": "DSR Collection Receipt",
            "read_only": 1,
            "insert_after": "payment_type",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_route",
            "label": "Distribution Route",
            "fieldtype": "Link",
            "options": "Distribution Route",
            "insert_after": "customer",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_dsr",
            "label": "Delivery DSR",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "rd_route",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_outlet_visit",
            "label": "Outlet Visit",
            "fieldtype": "Link",
            "options": "Outlet Visit",
            "insert_after": "rd_dsr",
        },
        {
            "dt": "Delivery Note",
            "fieldname": "rd_idempotency_key",
            "label": "Distribution Idempotency Key",
            "fieldtype": "Data",
            "read_only": 1,
            "unique": 1,
            "insert_after": "rd_outlet_visit",
        },
        {
            "dt": "Delivery Note Item",
            "fieldname": "rd_stock_category",
            "label": "Stock Category",
            "fieldtype": "Select",
            "options": "Saleable\nSupplier Free",
            "reqd": 1,
            "insert_after": "item_code",
        },
        {
            "dt": "Delivery Note Item",
            "fieldname": "rd_supplier_free_source",
            "label": "Supplier Free Source Receipt",
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "insert_after": "rd_stock_category",
        },
    ]
    for field in fields:
        existing = frappe.db.exists(
            "Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}
        )
        if existing:
            custom_field = frappe.get_doc("Custom Field", existing)
            # Custom fields predate the DSR Challan rename on some sites. Update
            # their options instead of preserving a link to the removed DocType.
            if custom_field.options != field.get("options"):
                custom_field.options = field.get("options")
                custom_field.save(ignore_permissions=True)
            continue
        frappe.get_doc({"doctype": "Custom Field", **field}).insert(ignore_permissions=True)


def ensure_procurement_setting_defaults() -> None:
    """Backfill new procurement policy defaults on existing tenant settings."""
    if not frappe.db.exists("DocType", "Distribution Settings"):
        return
    for name in frappe.get_all("Distribution Settings", pluck="name"):
        values = {}
        if frappe.db.get_value("Distribution Settings", name, "supplier_invoice_policy") is None:
            values["supplier_invoice_policy"] = "Auto-create Draft"
        if frappe.db.get_value("Distribution Settings", name, "auto_invoice_requires_supplier_bill") is None:
            values["auto_invoice_requires_supplier_bill"] = 1
        if frappe.db.get_value(
            "Distribution Settings", name, "allow_supplier_advance_without_purchase_order"
        ) is None:
            values["allow_supplier_advance_without_purchase_order"] = 1
        if values:
            frappe.db.set_value("Distribution Settings", name, values, update_modified=False)


def ensure_simplified_procurement_layout() -> None:
    """Hide advanced ERPNext controls from the Distribution procurement workflow.

    The native documents still retain every field and validation rule. This only
    reduces the operational form layout to the supplier, warehouse, items,
    invoice, and payment details that the Distribution team uses day to day.
    """
    hidden_fields = {
        "Purchase Order": {
            "supplier_name",
            "order_confirmation_no",
            "order_confirmation_date",
            "amended_from",
            "customer",
            "customer_name",
            "customer_contact_person",
            "customer_contact_display",
            "customer_contact_mobile",
            "customer_contact_email",
            "supplier_address",
            "contact_person",
            "address_display",
            "contact_display",
            "contact_mobile",
            "contact_email",
            "shipping_address",
            "shipping_address_display",
            "currency",
            "conversion_rate",
            "buying_price_list",
            "price_list_currency",
            "plc_conversion_rate",
            "ignore_pricing_rule",
            "is_subcontracted",
            "supplier_warehouse",
            "scan_barcode",
            "pricing_rules",
            "supplied_items",
            "total_qty",
            "base_total",
            "base_net_total",
            "net_total",
            "total_net_weight",
            "shipping_rule",
            "taxes",
            "other_charges_calculation",
            "base_taxes_and_charges_added",
            "base_taxes_and_charges_deducted",
            "base_total_taxes_and_charges",
            "taxes_and_charges_added",
            "taxes_and_charges_deducted",
            "total_taxes_and_charges",
            "apply_discount_on",
            "base_discount_amount",
            "additional_discount_percentage",
            "discount_amount",
            "base_grand_total",
            "base_rounding_adjustment",
            "base_in_words",
            "base_rounded_total",
            "rounding_adjustment",
            "rounded_total",
            "disable_rounded_total",
            "in_words",
            "advance_paid",
            "payment_terms_template",
            "payment_schedule",
            "tc_name",
            "terms",
            "ref_sq",
            "party_account_currency",
            "inter_company_order_reference",
            "per_received",
            "per_billed",
            "letter_head",
            "select_print_heading",
            "group_same_items",
            "language",
            "from_date",
            "to_date",
            "auto_repeat",
            "update_auto_repeat_reference",
            "tax_category",
            "set_reserve_warehouse",
            "billing_address",
            "billing_address_display",
            "is_internal_supplier",
            "represents_company",
            "cost_center",
            "project",
            "is_old_subcontracting_flow",
            "set_from_warehouse",
            "incoterm",
            "named_place",
            "dispatch_address",
            "dispatch_address_display",
            "supplier_group",
            "mps",
            "item_wise_tax_details",
            "transaction_time",
            "title",
        },
        "Purchase Receipt": {
            "supplier_name",
            "posting_time",
            "set_posting_time",
            "is_return",
            "return_against",
            "supplier_address",
            "contact_person",
            "address_display",
            "contact_display",
            "contact_mobile",
            "contact_email",
            "shipping_address",
            "shipping_address_display",
            "currency",
            "conversion_rate",
            "buying_price_list",
            "price_list_currency",
            "plc_conversion_rate",
            "ignore_pricing_rule",
            "rejected_warehouse",
            "is_subcontracted",
            "supplier_warehouse",
            "pricing_rules",
            "get_current_stock",
            "supplied_items",
            "total_qty",
            "base_total",
            "base_net_total",
            "net_total",
            "total_net_weight",
            "tax_category",
            "shipping_rule",
            "taxes",
            "other_charges_calculation",
            "base_taxes_and_charges_added",
            "base_taxes_and_charges_deducted",
            "base_total_taxes_and_charges",
            "taxes_and_charges_added",
            "taxes_and_charges_deducted",
            "total_taxes_and_charges",
            "apply_discount_on",
            "base_discount_amount",
            "additional_discount_percentage",
            "discount_amount",
            "base_grand_total",
            "base_rounding_adjustment",
            "base_in_words",
            "base_rounded_total",
            "rounding_adjustment",
            "rounded_total",
            "in_words",
            "disable_rounded_total",
            "tc_name",
            "terms",
            "amended_from",
            "range",
            "project",
            "per_billed",
            "auto_repeat",
            "letter_head",
            "select_print_heading",
            "language",
            "group_same_items",
            "instructions",
            "remarks",
            "transporter_name",
            "lr_no",
            "lr_date",
            "is_internal_supplier",
            "inter_company_reference",
            "scan_barcode",
            "billing_address",
            "billing_address_display",
            "apply_putaway_rule",
            "per_returned",
            "set_from_warehouse",
            "represents_company",
            "cost_center",
            "is_old_subcontracting_flow",
            "incoterm",
            "named_place",
            "subcontracting_receipt",
            "dispatch_address",
            "dispatch_address_display",
            "item_wise_tax_details",
            "title",
        },
        "Purchase Invoice": {
            "supplier_name",
            "tax_id",
            "is_paid",
            "is_return",
            "apply_tds",
            "cost_center",
            "posting_time",
            "set_posting_time",
            "amended_from",
            "on_hold",
            "release_date",
            "hold_comment",
            "return_against",
            "update_billed_amount_in_purchase_order",
            "update_billed_amount_in_purchase_receipt",
            "supplier_address",
            "address_display",
            "contact_person",
            "contact_display",
            "contact_mobile",
            "contact_email",
            "shipping_address",
            "shipping_address_display",
            "currency",
            "conversion_rate",
            "buying_price_list",
            "price_list_currency",
            "plc_conversion_rate",
            "ignore_pricing_rule",
            "set_warehouse",
            "rejected_warehouse",
            "is_subcontracted",
            "update_stock",
            "scan_barcode",
            "pricing_rules",
            "supplied_items",
            "total_qty",
            "base_total",
            "base_net_total",
            "net_total",
            "total_net_weight",
            "tax_category",
            "shipping_rule",
            "taxes",
            "other_charges_calculation",
            "base_taxes_and_charges_added",
            "base_taxes_and_charges_deducted",
            "base_total_taxes_and_charges",
            "taxes_and_charges_added",
            "taxes_and_charges_deducted",
            "total_taxes_and_charges",
            "apply_discount_on",
            "base_discount_amount",
            "additional_discount_percentage",
            "discount_amount",
            "base_grand_total",
            "base_rounding_adjustment",
            "base_rounded_total",
            "base_in_words",
            "rounding_adjustment",
            "rounded_total",
            "in_words",
            "disable_rounded_total",
            "mode_of_payment",
            "cash_bank_account",
            "clearance_date",
            "paid_amount",
            "base_paid_amount",
            "write_off_amount",
            "base_write_off_amount",
            "write_off_account",
            "write_off_cost_center",
            "allocate_advances_automatically",
            "get_advances",
            "advances",
            "payment_terms_template",
            "payment_schedule",
            "tc_name",
            "terms",
            "letter_head",
            "group_same_items",
            "select_print_heading",
            "language",
            "is_internal_supplier",
            "credit_to",
            "party_account_currency",
            "is_opening",
            "against_expense_account",
            "inter_company_invoice_reference",
            "remarks",
            "auto_repeat",
            "update_auto_repeat_reference",
            "billing_address",
            "billing_address_display",
            "project",
            "unrealized_profit_loss_account",
            "represents_company",
            "set_from_warehouse",
            "supplier_warehouse",
            "per_received",
            "ignore_default_payment_terms_template",
            "subscription",
            "is_old_subcontracting_flow",
            "incoterm",
            "named_place",
            "only_include_allocated_payments",
            "use_company_roundoff_cost_center",
            "use_transaction_date_exchange_rate",
            "supplier_group",
            "update_outstanding_for_self",
            "sender",
            "dispatch_address",
            "dispatch_address_display",
            "last_scanned_warehouse",
            "claimed_landed_cost_amount",
            "item_wise_tax_details",
            "tax_withholding_group",
            "tax_withholding_entries",
            "ignore_tax_withholding_threshold",
            "override_tax_withholding_entries",
            "title",
        },
        "Payment Entry": {
            "cost_center",
            "party_name",
            "contact_person",
            "contact_email",
            "paid_from_account_currency",
            "paid_to_account_currency",
            "source_exchange_rate",
            "base_paid_amount",
            "received_amount",
            "target_exchange_rate",
            "base_received_amount",
            "total_allocated_amount",
            "base_total_allocated_amount",
            "difference_amount",
            "write_off_difference_amount",
            "deductions",
            "clearance_date",
            "project",
            "letter_head",
            "print_heading",
            "bank",
            "bank_account_no",
            "payment_order",
            "auto_repeat",
            "amended_from",
            "title",
            "bank_account",
            "party_bank_account",
            "payment_order_status",
            "custom_remarks",
            "tax_withholding_category",
            "purchase_taxes_and_charges_template",
            "sales_taxes_and_charges_template",
            "taxes",
            "base_total_taxes_and_charges",
            "total_taxes_and_charges",
            "paid_amount_after_tax",
            "base_paid_amount_after_tax",
            "received_amount_after_tax",
            "base_received_amount_after_tax",
            "paid_from_account_type",
            "paid_to_account_type",
            "get_outstanding_invoices",
            "get_outstanding_orders",
            "book_advance_payments_in_separate_party_account",
            "base_in_words",
            "in_words",
            "reconcile_on_advance_payment_date",
            "is_opening",
            "apply_tds",
            "tax_withholding_group",
            "ignore_tax_withholding_threshold",
            "tax_withholding_entries",
            "override_tax_withholding_entries",
        },
    }
    for doctype, fieldnames in hidden_fields.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        fields = {field.fieldname: field for field in frappe.get_meta(doctype).fields}
        for fieldname in fieldnames:
            field = fields.get(fieldname)
            if not field or field.reqd:
                continue
            _set_property(doctype, fieldname, "hidden", "1", "Check")
        frappe.clear_cache(doctype=doctype)


def ensure_company_owned_master_fields() -> None:
    """Install and backfill the Company owner on native Distribution masters."""
    from reckon_distribution.master_data import get_company_owned_master_registry

    insert_after = {
        "Item": "item_name",
        "Customer": "customer_name",
        "Supplier": "supplier_name",
        "Item Price": "item_code",
        "Price List": "price_list_name",
    }
    fields = [
        {"dt": doctype, "insert_after": insert_after[doctype]}
        for doctype in get_company_owned_master_registry()
    ]
    for field in fields:
        if not frappe.db.exists("DocType", field["dt"]):
            continue
        if not frappe.db.exists(
            "Custom Field", {"dt": field["dt"], "fieldname": "rd_company"}
        ):
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": field["dt"],
                    "fieldname": "rd_company",
                    "label": "Company",
                    "fieldtype": "Link",
                    "options": "Company",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": field["insert_after"],
                }
            ).insert(ignore_permissions=True)
        _set_property(field["dt"], "rd_company", "read_only", "1", "Check")
        frappe.clear_cache(doctype=field["dt"])

    _backfill_company_owned_masters()


def _backfill_company_owned_masters() -> None:
    from reckon_distribution.master_data import get_company_owned_master_registry

    mappings = {doctype: doctype for doctype in get_company_owned_master_registry()}
    for doctype, master_type in mappings.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for record in frappe.get_all(doctype, fields=["name", "rd_company"]):
            companies = set(
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
            if record.rd_company:
                if len(companies) > 1 or (companies and record.rd_company not in companies):
                    frappe.log_error(
                        title="Distribution Master Ownership Conflict",
                        message=f"{doctype} {record.name}: field={record.rd_company}, scopes={sorted(companies)}",
                    )
                continue
            if len(companies) == 1:
                frappe.db.set_value(doctype, record.name, "rd_company", next(iter(companies)))
            elif len(companies) > 1:
                frappe.log_error(
                    title="Distribution Master Ownership Conflict",
                    message=f"{doctype} {record.name} is scoped to multiple Companies: {sorted(companies)}",
                )
            else:
                frappe.log_error(
                    title="Distribution Master Ownership Missing",
                    message=f"{doctype} {record.name} has no unambiguous Company owner.",
                )


def reload_distribution_layout_doctypes() -> None:
    """Reload layout-owned DocTypes whose field order is part of app source."""
    # Frappe v16 can remove a child DocType during orphan cleanup when an older
    # site has lost its controller metadata. Reload it after cleanup so the
    # parent table field is immediately usable again.
    if frappe.db.exists("DocType", "DSR Challan Item") or frappe.db.exists(
        "DocType", "DSR Challan"
    ):
        frappe.reload_doc("distribution", "doctype", "dsr_challan_item")
    if frappe.db.exists("DocType", "DSR Day Settlement"):
        frappe.reload_doc("distribution", "doctype", "dsr_day_settlement")


def ensure_dense_layout_fields() -> None:
    """Add native layout markers when older sites missed DocType JSON sync.

    These fields contain no business data. They make the three-column layout
    explicit to Frappe's native form renderer and keep long table/reconciliation
    sections full width. The names are prefixed so they cannot collide with
    standard or previously exported DocFields.
    """
    layouts = {
        "Distribution Route": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "route_code"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "route_name"},
        ],
        "Distribution Settings": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "supplier_goods_policy"},
        ],
        "DSR Collection Receipt": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "customer"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "collection_date"},
            {"fieldname": "rd_layout_section_details", "fieldtype": "Section Break", "label": "Collection details", "insert_after": "reference_no"},
            {"fieldname": "rd_layout_column_3", "fieldtype": "Column Break", "insert_after": "note"},
            {"fieldname": "rd_layout_section_gps", "fieldtype": "Section Break", "label": "Location", "insert_after": "payment_entry"},
        ],
        "DSR Day Settlement": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "settlement_date"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "status"},
            {"fieldname": "rd_layout_section_cash", "fieldtype": "Section Break", "label": "Cash reconciliation", "insert_after": "approved_expenses"},
            {"fieldname": "rd_layout_column_3", "fieldtype": "Column Break", "insert_after": "cash_handover"},
            {"fieldname": "rd_layout_column_4", "fieldtype": "Column Break", "insert_after": "counted_cash"},
            {"fieldname": "rd_layout_section_stock", "fieldtype": "Section Break", "label": "Stock reconciliation", "insert_after": "cash_variance_reason"},
            {"fieldname": "rd_layout_section_approval", "fieldtype": "Section Break", "label": "Approval", "insert_after": "stock_items"},
        ],
        "DSR Due Assignment": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "customer"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "effective_from"},
            {"fieldname": "rd_layout_section_approval", "fieldtype": "Section Break", "label": "Approval", "insert_after": "opening_unapplied_credit"},
        ],
        "Outlet Visit": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "customer"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "visited_on"},
            {"fieldname": "rd_layout_section_gps", "fieldtype": "Section Break", "label": "Location", "insert_after": "idempotency_key"},
        ],
        "Retailer Route Assignment": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "customer"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "assigned_user"},
        ],
        "Return Inspection": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "delivery_note"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "dsr"},
            {"fieldname": "rd_layout_section_review", "fieldtype": "Section Break", "label": "Inspection", "insert_after": "uom"},
            {"fieldname": "rd_layout_column_3", "fieldtype": "Column Break", "insert_after": "condition"},
            {"fieldname": "rd_layout_section_approval", "fieldtype": "Section Break", "label": "Approval", "insert_after": "status"},
        ],
        "SR Order": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "customer"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "order_date"},
            {"fieldname": "rd_layout_section_gps", "fieldtype": "Section Break", "label": "Location", "insert_after": "idempotency_key"},
            {"fieldname": "rd_layout_section_items", "fieldtype": "Section Break", "label": "Order items", "insert_after": "gps_captured_on"},
        ],
        "DSR Challan": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "posting_date"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "van_warehouse"},
            {"fieldname": "rd_layout_section_items", "fieldtype": "Section Break", "label": "Loading items", "insert_after": "dsr"},
            {"fieldname": "rd_layout_section_audit", "fieldtype": "Section Break", "label": "Approval and audit", "insert_after": "items"},
        ],
        "Van Loading Acknowledgement": [
            {"fieldname": "rd_layout_column_1", "fieldtype": "Column Break", "insert_after": "challan"},
            {"fieldname": "rd_layout_column_2", "fieldtype": "Column Break", "insert_after": "acknowledged_on"},
            {"fieldname": "rd_layout_section_items", "fieldtype": "Section Break", "label": "Acknowledged items", "insert_after": "acknowledged_on"},
        ],
    }

    for doctype, fields in layouts.items():
        if not frappe.db.exists("DocType", doctype):
            continue

        if doctype == "Distribution Settings":
            obsolete = frappe.db.exists(
                "Custom Field", {"dt": doctype, "fieldname": "rd_layout_column_2"}
            )
            if obsolete:
                frappe.delete_doc("Custom Field", obsolete, ignore_permissions=True, force=True)
                frappe.clear_cache(doctype=doctype)

        if doctype == "DSR Day Settlement":
            # Older migrations created fallback Custom Fields before the native
            # DocType layout was reloaded. Remove only those layout-only fields.
            for fieldname in (
                "rd_layout_column_1",
                "rd_layout_column_2",
                "rd_layout_column_3",
                "rd_layout_column_4",
                "rd_layout_section_cash",
                "rd_layout_section_stock",
                "rd_layout_section_approval",
            ):
                custom_field = frappe.db.exists(
                    "Custom Field", {"dt": doctype, "fieldname": fieldname}
                )
                if custom_field:
                    frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)
            frappe.clear_cache(doctype=doctype)
            continue

        existing = {field.fieldname for field in frappe.get_meta(doctype).fields if field.fieldname}
        for field in fields:
            if field["fieldname"] in existing or frappe.db.exists(
                "Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}
            ):
                continue
            values = {
                "doctype": "Custom Field",
                "dt": doctype,
                "fieldname": field["fieldname"],
                "fieldtype": field["fieldtype"],
                "insert_after": field["insert_after"],
            }
            if field.get("label"):
                values["label"] = field["label"]
            frappe.get_doc(values).insert(ignore_permissions=True)
            existing.add(field["fieldname"])
        frappe.clear_cache(doctype=doctype)


def setup_roles() -> None:
    for role in OPERATIONAL_ROLES:
        if not frappe.db.exists("Role", role.name):
            doc = frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role.name,
                    "desk_access": 1,
                    "is_custom": 1,
                }
            )
            doc.insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Role", role.name, "desk_access", 1)
            frappe.db.set_value("Role", role.name, "home_page", "")


def ensure_distribution_permissions() -> None:
    """Grant navigation and native-master access to Distribution roles."""
    ensure_assigned_user_roles()
    ensure_tenant_user_permissions()
    ensure_distribution_page_roles()
    ensure_native_master_permissions()
    ensure_distribution_transaction_permissions()


def ensure_tenant_user_permissions() -> None:
    """Backfill standard Company User Permissions for existing assignments."""
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return
    from reckon_distribution.warehouse import sync_tenant_user_permission

    users = frappe.get_all("Tenant User Assignment", filters={"active": 1}, pluck="user")
    for user in set(users):
        companies = frappe.get_all(
            "Tenant User Assignment",
            filters={"user": user, "active": 1},
            pluck="company",
        )
        if len({company for company in companies if company}) != 1:
            frappe.log_error(
                title="Distribution Company Permission Conflict",
                message=f"User {user} has multiple active Company assignments: {companies}",
            )
            continue
        sync_tenant_user_permission(frappe._dict({"user": user}))


def ensure_assigned_user_roles() -> None:
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return
    role_map = {
        "Company Admin": "Reckon Distribution Admin",
        "Company Manager": "Reckon Distribution Manager",
        "Master Data Manager": "Reckon Master Data Manager",
        "SR": "Reckon Distribution User",
        "DSR": "Reckon Distribution User",
    }
    assignments = frappe.get_all(
        "Tenant User Assignment",
        filters={"active": 1},
        fields=["user", "role_profile"],
    )
    for assignment in assignments:
        role = role_map.get(assignment.role_profile)
        if not role or not frappe.db.exists("User", assignment.user):
            continue
        user = frappe.get_doc("User", assignment.user)
        if role not in frappe.get_roles(assignment.user):
            user.add_roles(role)
        frappe.clear_cache(user=assignment.user)


def ensure_distribution_page_roles() -> None:
    page_names = {
        "distribution",
        "distribution-master-setup",
        "distribution-item-uom-setup",
        "distribution-team-access",
        "field-sales",
        "dsr-delivery",
        "dsr-day-settlement",
        "distribution-reports",
    }
    roles = [role.name for role in OPERATIONAL_ROLES]
    for page_name in page_names:
        if not frappe.db.exists("Page", page_name):
            continue
        for role in roles:
            if frappe.db.exists(
                "Has Role",
                {"parent": page_name, "parenttype": "Page", "parentfield": "roles", "role": role},
            ):
                continue
            next_idx = frappe.db.sql(
                """
                select coalesce(max(idx), 0) + 1
                from `tabHas Role`
                where parent = %s and parenttype = 'Page' and parentfield = 'roles'
                """,
                page_name,
            )[0][0]
            frappe.db.sql(
                """
                insert into `tabHas Role`
                    (name, creation, modified, modified_by, owner, docstatus,
                     parent, parentfield, parenttype, idx, role)
                values (%s, now(), now(), %s, %s, 0, %s, 'roles', 'Page', %s, %s)
                """,
                (frappe.generate_hash(length=10), frappe.session.user, frappe.session.user, page_name, next_idx, role),
            )


def ensure_native_master_permissions() -> None:
    master_permissions = {
        "Page": {"read"},
        # Frappe's native list and form loaders read DocType metadata even
        # when the requested document itself is already role-permitted.
        "DocType": {"read"},
        # The native Purchase Order, Receipt, Invoice, and Payment Entry forms
        # fetch the selected Company's defaults before rendering.
        "Company": {"read"},
        # Native print preview resolves the selected Company letter head.
        "Letter Head": {"read"},
        "Print Format": {"read"},
        # ERPNext purchase controllers read maintain_same_rate from this
        # singleton during form boot.
        "Buying Settings": {"read"},
        "Customer": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Supplier": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Item": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Item Price": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "Price List": {"read", "write", "create", "delete", "report", "export", "print", "email"},
        "UOM": {"read"},
        # Supporting link masters are shared ERPNext references. Distribution users
        # may select them, but must not edit the global definitions.
        "Item Group": {"read"},
        "Brand": {"read"},
        "Customer Group": {"read"},
        "Supplier Group": {"read"},
        "Territory": {"read"},
        "Warehouse": {"read", "write", "create", "delete", "report", "export", "print"},
        "Payment Terms Template": {"read"},
        # Payment Entry resolves this Link master while loading its form.
        "Mode of Payment": {"read"},
        "Account": {"read"},
        "Report": {"read"},
        "Stock Ledger Entry": {"read", "report", "export", "print"},
        "Purchase Order": {"read", "write", "create", "delete", "report", "export", "print", "email", "submit", "cancel", "amend"},
        "Purchase Receipt": {"read", "write", "create", "delete", "report", "export", "print", "email", "submit", "cancel", "amend"},
        "Purchase Invoice": {"read", "write", "create", "delete", "report", "export", "print", "email", "submit", "cancel", "amend"},
        "Payment Entry": {"read", "write", "create", "delete", "report", "export", "print", "email", "submit", "cancel", "amend"},
    }
    full_access_roles = {
        "Reckon Distribution Admin",
        "Reckon Distribution Manager",
        "Reckon Master Data Manager",
        "Company Admin",
        "Company Manager",
        "Master Data Manager",
    }
    read_only_roles = {"Reckon Distribution User", "DSR", "SR"}
    procurement_doctypes = {"Purchase Order", "Purchase Receipt", "Purchase Invoice", "Payment Entry"}
    operational_report_doctypes = {"Stock Ledger Entry"}
    procurement_roles = {
        "Reckon Distribution Admin",
        "Reckon Distribution Manager",
        "Company Admin",
        "Company Manager",
    }
    permission_role_names = (
        full_access_roles
        | read_only_roles
        | {role.name for role in OPERATIONAL_ROLES}
        | set(TENANT_ROLE_NAMES)
    )
    permission_roles = {role for role in permission_role_names if frappe.db.exists("Role", role)}
    for doctype, full_rights in master_permissions.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        if doctype == "DocType":
            # Frappe deliberately excludes DocType from Meta.set_custom_permissions,
            # so Custom DocPerm rows are ignored for this metadata doctype. Seed the
            # real standard permission row instead.
            for role in permission_roles:
                ensure_standard_doc_type_read_permission(role)
            frappe.clear_cache(doctype=doctype)
            continue
        permissions.setup_custom_perms(doctype)
        for role in permission_roles:
            existing = frappe.db.exists(
                "Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
            )
            if existing:
                perm = frappe.get_doc("Custom DocPerm", existing)
            else:
                perm = frappe.get_doc(
                    {
                        "doctype": "Custom DocPerm",
                        "parent": doctype,
                        "parenttype": "DocType",
                        "parentfield": "permissions",
                        "role": role,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                )
                perm.insert(ignore_permissions=True)
            if doctype in procurement_doctypes and role not in procurement_roles:
                rights = set()
            elif doctype in operational_report_doctypes:
                rights = full_rights
            else:
                rights = full_rights if role in full_access_roles else {"read"}
            for right in full_rights:
                enabled = right in rights
                perm.db_set(right, 1 if enabled else 0)
                # Keep Frappe's native permission resolver in sync. Some v16
                # installations do not immediately include Custom DocPerm rows
                # in the cached role permission map after migration.
                if enabled and hasattr(permissions, "add_permission"):
                    if not frappe.db.exists(
                        "DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
                    ):
                        permissions.add_permission(doctype, role, 0)
                    if hasattr(permissions, "update_permission_property"):
                        permissions.update_permission_property(doctype, role, 0, right, 1)
        frappe.clear_cache(doctype=doctype)


def ensure_standard_doc_type_read_permission(role: str) -> None:
    """Grant metadata read access using DocPerm, not Custom DocPerm.

    ``DocType`` is one of the few doctypes for which Frappe ignores custom
    permission rows. Native Desk list/form boot therefore requires a standard
    ``tabDocPerm`` row for each Distribution role.
    """
    if not frappe.db.exists("Role", role):
        return

    existing = frappe.db.exists(
        "DocPerm", {"parent": "DocType", "role": role, "permlevel": 0, "if_owner": 0}
    )
    if existing:
        if not frappe.db.get_value("DocPerm", existing, "read"):
            frappe.db.set_value("DocPerm", existing, "read", 1, update_modified=False)
        return

    idx = frappe.db.sql(
        """
        select coalesce(max(idx), 0) + 1
        from `tabDocPerm`
        where parent = 'DocType' and parentfield = 'permissions' and parenttype = 'DocType'
        """
    )[0][0]
    now = frappe.utils.now()
    frappe.db.sql(
        """
        insert into `tabDocPerm`
            (name, creation, modified, modified_by, owner, docstatus, idx,
             parent, parentfield, parenttype, role, permlevel, if_owner, `read`)
        values (%s, %s, %s, %s, %s, 0, %s,
                'DocType', 'permissions', 'DocType', %s, 0, 0, 1)
        """,
        (frappe.generate_hash(length=10), now, now, frappe.session.user, frappe.session.user, idx, role),
    )


def ensure_distribution_transaction_permissions() -> None:
    """Give operational roles the transaction access used by custom pages."""
    transaction_permissions = {
        "DSR Challan": {"read", "write", "create", "submit", "print"},
        "Delivery Note": {"read", "write", "create", "submit", "print"},
        "DSR Collection Receipt": {"read", "write", "create"},
    }
    permission_flags = {
        "read",
        "write",
        "create",
        "delete",
        "submit",
        "cancel",
        "amend",
        "print",
        "email",
        "export",
        "report",
        "share",
    }
    operational_roles = {
        "Reckon Distribution Admin",
        "Reckon Distribution Manager",
        "Reckon Distribution User",
        "Company Admin",
        "Company Manager",
        "DSR",
        "SR",
    }
    operational_roles = {role for role in operational_roles if frappe.db.exists("Role", role)}
    for doctype, full_rights in transaction_permissions.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        if not frappe.get_meta(doctype).is_submittable:
            # Older installs may have copied submit/cancel flags onto this
            # non-submittable receipt. Clear both permission stores before
            # Frappe validates any subsequent permission update.
            frappe.db.sql(
                """
                update `tabDocPerm`
                set `submit` = 0, `cancel` = 0, `amend` = 0
                where parent = %s and permlevel = 0
                """,
                doctype,
            )
            frappe.db.sql(
                """
                update `tabCustom DocPerm`
                set `submit` = 0, `cancel` = 0, `amend` = 0
                where parent = %s and permlevel = 0
                """,
                doctype,
            )
        permissions.setup_custom_perms(doctype)
        for role in operational_roles:
            existing = frappe.db.exists(
                "Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
            )
            if existing:
                perm = frappe.get_doc("Custom DocPerm", existing)
            else:
                perm = frappe.get_doc(
                    {
                        "doctype": "Custom DocPerm",
                        "parent": doctype,
                        "parenttype": "DocType",
                        "parentfield": "permissions",
                        "role": role,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                )
                perm.insert(ignore_permissions=True)
            # DSR users submit Delivery Notes from the delivery page, while
            # delete/cancel rights remain absent from this permission row.
            rights = full_rights
            for right in permission_flags:
                enabled = right in rights
                perm.db_set(right, 1 if enabled else 0)
                if enabled and hasattr(permissions, "add_permission"):
                    if not frappe.db.exists(
                        "DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
                    ):
                        permissions.add_permission(doctype, role, 0)
                    if hasattr(permissions, "update_permission_property"):
                        permissions.update_permission_property(doctype, role, 0, right, 1)
        frappe.clear_cache(doctype=doctype)


def setup_workspace() -> None:
    if not frappe.db.exists("Workspace", DISTRIBUTION_WORKSPACE):
        workspace = frappe.get_doc(_workspace_doc())
        workspace.insert(ignore_permissions=True)
    else:
        workspace = frappe.get_doc("Workspace", DISTRIBUTION_WORKSPACE)
        workspace.update(_workspace_doc(update=True))
        workspace.save(ignore_permissions=True)
    ensure_workspace_sidebar()


def ensure_workspace_sidebar() -> None:
    """Keep the Distribution workspace's visible v16 navigation available."""
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return

    sidebar_name = DISTRIBUTION_SIDEBAR
    if not frappe.db.exists("Workspace Sidebar", sidebar_name):
        # Older installs briefly used the workspace label as the sidebar name.
        # Reuse that record if it exists; otherwise create the native sidebar name.
        sidebar_name = frappe.db.exists("Workspace Sidebar", DISTRIBUTION_WORKSPACE) or sidebar_name
    if not frappe.db.exists("Workspace Sidebar", sidebar_name):
        frappe.get_doc(_workspace_sidebar_doc(sidebar_name)).insert(
            ignore_permissions=True, ignore_links=True
        )
        return

    sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)
    # The Distribution sidebar is application-owned. Rebuild the rows so a
    # previous fixture cannot leave a Dynamic Link pointing at the wrong type.
    sidebar.set("items", _workspace_sidebar_doc(sidebar_name)["items"])
    sidebar.save(ignore_permissions=True)


def _workspace_sidebar_doc(sidebar_name: str = DISTRIBUTION_SIDEBAR) -> dict:
    """Return the native left-rail definition used by the active Desk shell."""
    def section(label: str, icon: str) -> dict:
        return {
            "label": label,
            "type": "Section Break",
            "icon": icon,
            "child": 0,
            "indent": 0,
            "collapsible": 1,
            "keep_closed": 0,
            "show_arrow": 0,
        }

    def link(label: str, link_to: str, link_type: str, icon: str) -> dict:
        return {
            "label": label,
            "link_to": link_to,
            "link_type": link_type,
            "type": "Link",
            "icon": icon,
            "child": 0,
            "indent": 0,
            "collapsible": 1,
            "show_arrow": 0,
        }

    items = [
        link("Distribution Home", "distribution", "Page", "house"),
        section("Sales & Delivery", "shopping-bag"),
        link("Field Sales", "field-sales", "Page", "map-pin"),
        link("SR Orders", "SR Order", "DocType", "clipboard-list"),
        link("Outlet Visits", "Outlet Visit", "DocType", "map-pinned"),
        link("DSR Delivery & Collection", "dsr-delivery", "Page", "truck"),
        link("Delivery Notes", "Delivery Note", "DocType", "file-check-2"),
        link("DSR Collections", "DSR Collection Receipt", "DocType", "wallet-cards"),
        link("DSR Day Settlement", "dsr-day-settlement", "Page", "calculator"),
        section("Procurement", "package-plus"),
        link("Purchase Orders", "Purchase Order", "DocType", "clipboard-list"),
        link("Purchase Received", "Purchase Receipt", "DocType", "package-check"),
        link("Purchase Invoices", "Purchase Invoice", "DocType", "file-text"),
        link("Supplier Advances & Payments", "Payment Entry", "DocType", "landmark"),
        section("Inventory & Stock", "boxes"),
        link("DSR Challan", "DSR Challan", "DocType", "package-check"),
        link("Stock Entries", "Stock Entry", "DocType", "arrow-right-left"),
        link("Stock Ledger", "Stock Ledger Entry", "DocType", "book-open"),
        link("Warehouses", "Warehouse", "DocType", "warehouse"),
        section("Reports", "chart-no-axes-combined"),
        link("Distribution Reports", "distribution-reports", "Page", "chart-column"),
        section("Administration", "settings"),
        link("Distribution Master Setup", "distribution-master-setup", "Page", "settings-2"),
        link("Item Units & Conversion", "distribution-item-uom-setup", "Page", "ruler"),
        link("Company Team & Access", "distribution-team-access", "Page", "users"),
    ]
    # ERPNext standard DocTypes can be unavailable during app installation
    # ordering. Do not make the whole install fail; after_migrate will append
    # the links once the native modules are present.
    items = [
        item
        for item in items
        if item.get("type") != "Link"
        or item.get("link_type") not in {"DocType", "Report"}
        or frappe.db.exists(item.get("link_type"), item.get("link_to"))
    ]
    return {
        "doctype": "Workspace Sidebar",
        "name": sidebar_name,
        "app": "reckon_distribution",
        "module": "Distribution",
        "title": "Distribution",
        "header_icon": "package-check",
        "standard": 1,
        "items": items,
    }


def _workspace_doc(update: bool = False) -> dict:
    data = {
        "doctype": "Workspace",
        "label": DISTRIBUTION_WORKSPACE,
        "title": _("Distribution Workspace"),
        "module": "Distribution",
        "category": "Modules",
        "public": 0,
        "is_hidden": 0,
        "icon": "organization",
        "roles": [{"role": role.name} for role in OPERATIONAL_ROLES],
        "content": _workspace_content(),
        "shortcuts": [
            {"color": "Blue", "label": "Master Setup", "link_to": "distribution-master-setup", "type": "Page"},
            {"color": "Blue", "label": "Distribution Warehouses", "link_to": "Warehouse", "type": "DocType"},
            {"color": "Purple", "label": "Team & Access", "link_to": "distribution-team-access", "type": "Page"},
            {"color": "Green", "label": "Field Sales", "link_to": "field-sales", "type": "Page"},
            {"color": "Orange", "label": "DSR Challan", "link_to": "DSR Challan", "type": "DocType"},
            {"color": "Green", "label": "Deliver & Collect", "link_to": "dsr-delivery", "type": "Page"},
            {"color": "Red", "label": "Day Settlement", "link_to": "dsr-day-settlement", "type": "Page"},
        ],
        "links": [
            {
                "label": "DSR Challan",
                "link_to": "DSR Challan",
                "link_type": "DocType",
                "type": "Link",
            },
        ],
        "charts": [],
        "number_cards": [],
    }
    if not update:
        data["name"] = DISTRIBUTION_WORKSPACE
    return data


def _workspace_content() -> str:
    return """[
 {"id":"intro","type":"header","data":{"text":"Distribution"}},
 {"id":"summary","type":"paragraph","data":{"text":"Bangla-first SR/DSR distribution workspace. Transaction workflows will be added in later phases after tenant isolation is enforced."}},
 {"id":"foundation","type":"shortcut","data":{"shortcut_name":"Distribution Shell","col":3}}
]"""
