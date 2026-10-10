# Supplier Receiving, Invoice, Advance, and Dues Design

## Status

Approved implementation baseline. The workflow uses ERPNext native Purchase Receipt,
Purchase Invoice, Payment Entry, Supplier Ledger, and Accounts Payable behavior.

## Objective

Define how a tenant company receives products from a supplier, posts stock, creates the supplier invoice, records supplier advances, and calculates outstanding dues without duplicating ERPNext accounting or bypassing company isolation.

The design follows the existing tenant-isolation rules in `docs/distribution-tenant-isolation-final-design.md`.

## ERPNext Standard Behavior

ERPNext's standard purchase flow is:

`Purchase Order -> Purchase Receipt -> Purchase Invoice -> Payment Entry`

- A **Purchase Receipt** records physical acceptance of goods. On submission it creates stock ledger entries for accepted quantities and records the temporary liability represented by Stock Received But Not Billed. See the [Purchase Receipt documentation](https://docs.frappe.io/erpnext/purchase-receipt).
- A **Purchase Invoice** records the supplier bill and payable. It can be created from a Purchase Order or Purchase Receipt. Submission updates the supplier balance and general ledger. See the [Purchase Invoice documentation](https://docs.frappe.io/erpnext/purchase-invoice).
- A **Payment Entry** records an advance or settlement with the supplier. A supplier advance can be submitted before the invoice and allocated later. See [Advance Payment Entry](https://docs.frappe.io/erpnext/advance-payment-entry).
- **Stock Entry is not the supplier receiving document.** It is used for internal stock movement, such as moving stock from a distributor warehouse to a van warehouse. Supplier receipt must remain a Purchase Receipt.

The standard accounting sequence is documented in [Purchase Cycle Ledger Impact](https://docs.frappe.io/erpnext/purchase-cycle-ledger-impact).

## Recommended Business Workflow

### 1. Receive supplier goods

1. The Company Admin or authorized warehouse user creates a Purchase Receipt from a Purchase Order, or creates it directly when no order exists.
2. The document contains the tenant Company, Supplier, accepted warehouse, posting date, items, quantities, UOM, batch/serial details, rejected quantities, and supplier bill details when available.
3. The application validates that Supplier, Item, Warehouse, UOM, and all linked records belong to the same Company scope.
4. On submit, ERPNext posts the accepted quantity to stock. The Purchase Receipt is the source of truth for physical receipt.
5. Free goods and shortages continue to follow the existing distribution Purchase Receipt validation rules. They must not be silently converted into payable quantity.

### 2. Create the supplier invoice

The app should not immediately submit a payable invoice merely because goods were received. A physical receipt can occur before the supplier sends a bill, and supplier invoice number, date, taxes, charges, and payment terms may not yet be known.

The recommended default is:

> On Purchase Receipt submission, create one linked **Draft Purchase Invoice** only when the required supplier billing information is available. Keep the invoice Draft until a finance-authorized user verifies and submits it.

The following policy belongs in the company-specific Distribution Settings:

| Setting | Meaning |
| --- | --- |
| `Manual` | No invoice is generated. Finance creates it later from the Purchase Receipt. |
| `Auto-create Draft` | Create one linked Draft Purchase Invoice after receipt submission. Recommended default. |
| `Auto-submit` | Create and submit the invoice automatically only when all strict prerequisites are satisfied. |

For every invoice created from a Purchase Receipt:

- Use the standard ERPNext Purchase Invoice mapping behavior.
- Set `Update Stock = 0`. The Purchase Receipt already posted stock; enabling Update Stock would risk double-posting inventory.
- Copy only quantities that are billable under the approved free-goods and shortage policy.
- Copy Company, Supplier, currency, warehouse references, taxes, charges, payment terms, and source references consistently.
- Store a link from Purchase Receipt to the generated Purchase Invoice for auditability and retry idempotency.
- Never create a second invoice when a previous attempt already created or linked one.
- Require Supplier invoice number and invoice date before auto-submit. Enforce uniqueness for the Supplier/Company invoice number according to ERPNext rules.

If the supplier bill is unavailable, the receipt may remain in `To Bill`, or the app may create a Draft invoice without submitting it. It must not invent invoice metadata.

### 3. Submit the Purchase Invoice

When a finance-authorized user verifies and submits the Purchase Invoice:

- Stock Received But Not Billed is cleared against the invoice.
- Supplier Accounts Payable is created.
- Taxes and charges are posted according to the invoice configuration.
- The supplier outstanding balance becomes available to the standard Accounts Payable, Supplier Ledger, and Payment Ledger reports.

Payment terms should use ERPNext Payment Terms Templates when installments or credit periods are required. See [Payment Terms Template](https://docs.frappe.io/erpnext/payment-terms-template).

### 4. Record supplier advance payment

Supplier advances must use the native ERPNext Payment Entry flow:

- `Payment Type = Pay`
- `Party Type = Supplier`
- `Party = Supplier`
- Same Company and currency as the intended purchase
- Bank or cash account as the paid-from account
- Supplier advance or payable account according to the Company's ERPNext account configuration
- Optional Purchase Order reference when the advance is tied to a specific order

The advance is submitted before the Purchase Invoice and remains unallocated until it is matched to an invoice. Allocation should use ERPNext's standard reconciliation/payment workflow, not a custom dues ledger. A partial allocation leaves the remaining amount available for later invoices.

The application must validate that the Supplier, Company, payable account, currency, and reference document are compatible. A supplier advance must not be posted to another Company's payable account.

### 5. Manage supplier dues

Supplier dues are derived from submitted ERPNext accounting documents, not stored as a manually maintained total:

`Supplier outstanding = submitted Purchase Invoice payable - allocated advances - supplier payments - credit notes`

The user-facing Distribution view may summarize dues, but its values must come from the standard Supplier Ledger, Accounts Payable, Payment Ledger, and invoice outstanding fields. It must support Company filtering and the current user's permitted Company scope.

## Accounting Sequence

| Event | Standard accounting/stock effect |
| --- | --- |
| Purchase Order submitted | No stock or GL posting. |
| Purchase Receipt submitted | Debit Stock In Hand; credit Stock Received But Not Billed. |
| Purchase Invoice submitted from receipt | Debit Stock Received But Not Billed, plus applicable taxes/charges; credit Supplier Payable. |
| Supplier advance Payment Entry submitted | Debit supplier advance/payable clearing; credit Bank/Cash, based on the configured accounts. |
| Advance allocated to invoice | Standard ERPNext reconciliation reduces the invoice outstanding and clears the advance. |
| Supplier payment against invoice | Debit Supplier Payable; credit Bank/Cash. |
| Internal Stock Entry submitted | Debit destination warehouse stock; credit source warehouse stock. No supplier payable is created. |

Account names can vary by Company. The app must use the Company's ERPNext account configuration rather than hard-coded account names.

## Proposed Data Model

Do not create a custom payable, stock, or supplier-dues ledger. Reuse ERPNext native documents and add only app-owned Custom Fields where auditability or policy is needed.

### Company-specific Distribution Settings

- `supplier_invoice_policy`: `Manual`, `Auto-create Draft`, or `Auto-submit`.
- `auto_invoice_requires_supplier_bill`: Check, default enabled.
- `allow_supplier_advance_without_purchase_order`: Check, subject to Company policy.
- Optional cancellation policy, defaulting to manual dependency handling.

### Purchase Receipt

- `rd_purchase_invoice`: Link to Purchase Invoice, when exactly one generated invoice exists.
- `rd_invoice_status`: Read-only status mirror for navigation and reporting.
- `rd_invoice_created_on`: Read-only audit timestamp, if required.
- Existing promotion, paid/free, shortage, and source fields remain governed by the current Purchase Receipt validation.

### Purchase Invoice

- `rd_source_purchase_receipt`: Link to Purchase Receipt when the invoice was generated by the Distribution workflow.
- Optional read-only source indicator for audit/reporting.

Use standard Purchase Invoice references and standard Payment Entry references wherever possible. Avoid adding duplicate Supplier, Company, due, payable, or payment fields.

## Auto-Invoice Safety Rules

The invoice creation service must be idempotent and safe to retry:

1. Confirm the Purchase Receipt is submitted and not cancelled.
2. Lock or re-check the receipt before creating the invoice.
3. Look for an existing linked invoice or existing invoice reference before creating anything.
4. Create the invoice with `Update Stock = 0`.
5. Save the link only after the invoice document is created successfully.
6. If a retry finds an existing Draft invoice, return that invoice instead of creating another.
7. If a submitted invoice exists, do not alter it automatically.
8. If auto-submit is enabled but a prerequisite is missing, fail with a clear native validation message or leave a Draft according to the selected policy.

The invoice must not be auto-submitted when any of the following is unresolved:

- Supplier invoice number or invoice date is required but missing.
- Supplier, Company, currency, or payable account does not match.
- Tax/charge information is incomplete.
- Billable quantity cannot be determined because of free goods, shortage, or return rules.
- The Purchase Receipt has already been invoiced or cancelled.
- The submitting user lacks Purchase Invoice and accounting permissions.

## Cancellation and Returns

- A submitted Purchase Receipt cannot silently invalidate a submitted Purchase Invoice.
- If the linked invoice is Draft, the system may cancel/remove the Draft link according to the approved policy.
- If the linked invoice is submitted, the user must cancel or reverse the invoice first, then cancel or return the Purchase Receipt according to ERPNext rules.
- A Purchase Return must reverse the physical stock and related accounting through native ERPNext documents.
- No automatic cascade should cancel financial documents without an explicit company policy and a complete audit trail.

## Permissions and Tenant Isolation

- Company Admin and authorized warehouse/finance roles receive only the document permissions needed for their duties.
- DSR/SR users may receive or move stock only where the distribution role design explicitly allows it. They must not receive supplier invoice submission or supplier advance permissions by default.
- Finance or Company Admin users may verify/submit Purchase Invoices and Payment Entries.
- Purchase Receipt, Purchase Invoice, Payment Entry, and Stock Entry must be filtered and validated by Company.
- Supplier, Item, Price List, Item Price, Warehouse, UOM, and all related masters must be resolved through the existing tenant-scope rules.
- A user with permission for Company A must not open, link, create, or update supplier documents for Company B.
- User Permission records remain the primary user-to-Company assignment mechanism. Server-side validation remains mandatory even when the UI auto-selects the permitted Company.
- New future supplier-related DocTypes must follow this same pattern: Company scope, User Permission filtering, link validation, role permissions, and multi-company tests.

## UI Behavior

- Company is assigned automatically from the user's permitted Company context and hidden or read-only according to the approved Distribution UI rule.
- Supplier, Purchase Receipt, Purchase Invoice, Warehouse, and Payment Entry link fields must show only records in the permitted Company scope.
- The Purchase Receipt should show the invoice status and a link to the generated Draft/Submitted invoice.
- Finance users should be able to open the Draft invoice from the receipt without re-entering items.
- Supplier advance entry should provide an optional Purchase Order reference and show the unallocated amount after save.
- Dues pages should link to native invoices, payments, advances, returns, and credit notes rather than showing an independently calculated balance.
- All validation errors should use native Frappe messages and preserve the server traceback in logs only.
- The Reports menu links managers to native Accounts Payable reporting; it does not create a separate supplier due ledger.

## Functional Test Matrix

### Receiving and invoicing

- Create a Purchase Receipt from a Purchase Order and submit it.
- Confirm accepted quantity appears in stock and Stock Received But Not Billed is created.
- Confirm Auto-create Draft creates exactly one linked Draft Purchase Invoice.
- Retry the same request and confirm no duplicate invoice is created.
- Submit the Draft invoice and confirm the supplier payable is posted.
- Confirm the generated invoice has `Update Stock = 0` and stock is not doubled.
- Confirm Manual policy does not create an invoice.
- Confirm Auto-submit is blocked when supplier invoice number/date is missing.
- Confirm free, shortage, rejected, batch, and serial quantities follow the approved billing policy.

### Advances and dues

- Create and submit a supplier advance before the invoice.
- Allocate the advance fully to a Purchase Invoice.
- Allocate an advance partially and confirm the remaining unallocated amount.
- Create a partial supplier payment and confirm the invoice outstanding amount.
- Verify payment terms and due dates, including overdue reporting.
- Verify Supplier Ledger, Accounts Payable, and Payment Ledger agree with the Distribution summary.

### Stock movement

- Receive supplier stock through Purchase Receipt.
- Move stock internally through Stock Entry or the DSR Challan process.
- Confirm internal transfer changes warehouse quantities only and does not create supplier payable.

### Isolation and permissions

- User assigned to Company A cannot search or link Company B Supplier, Purchase Receipt, Purchase Invoice, Payment Entry, Warehouse, or Stock Entry.
- Direct API attempts to save a Company B document are rejected.
- A DSR/SR user cannot submit Purchase Invoice or supplier advance without the required role permission.
- Company Admin-created users receive the correct Company User Permission automatically.
- A user with multiple permitted Companies sees only the permitted Company context and cannot accidentally post into another Company.
- Cancellation and return tests preserve the audit trail and do not leave orphaned invoice links.

## Implementation Phases

1. Add company-specific settings and document the approved policy defaults.
2. Add Purchase Receipt to Purchase Invoice links and native UI navigation.
3. Implement an idempotent Draft Purchase Invoice mapper with `Update Stock = 0`.
4. Add optional strict Auto-submit mode behind the Company setting and finance permission checks.
5. Add supplier advance navigation using native Payment Entry and reconciliation references.
6. Add dues summaries sourced from native outstanding and ledger data.
7. Add fixtures and the complete multi-company functional test class/script.
8. Run the test site workflow, update the test document, commit, push, and deploy only after all tests pass.

## Decisions Required Before Development

The recommended defaults are:

- Default invoice policy: **Auto-create Draft**.
- Auto-submit: disabled unless explicitly enabled per Company.
- Supplier bill required for auto-submit: enabled.
- Purchase Invoice `Update Stock`: always disabled when generated from Purchase Receipt.
- Supplier advances: native Payment Entry, optionally linked to Purchase Order.
- Dues: native ERPNext outstanding/ledger values, not a custom balance field.
- Cancellation: no silent cascade across submitted stock and accounting documents.

These defaults are now implemented:

1. Purchase Receipt submission creates one linked Draft Purchase Invoice by default; Manual policy disables generation.
2. Supplier-free quantities are received into stock but excluded from the supplier invoice.
3. Distribution Admin/Manager and Company Admin/Manager receive procurement permissions; DSR/SR do not receive Purchase Invoice or Payment Entry permissions.
4. Supplier advances without a Purchase Order are allowed by default through native Payment Entry.
5. Auto-submit is disabled by default and requires supplier bill number/date when enabled.
