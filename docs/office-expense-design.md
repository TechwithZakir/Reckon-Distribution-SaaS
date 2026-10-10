# Office Expense Design

## Purpose

`Office Expense` is a compact, Company-scoped entry form for ordinary expenses
already paid from cash or a bank account. Users work only with friendly expense
categories and payment labels. The accounting accounts are configured by an
administrator and are never entered by the operational user.

## Configuration

Each Company has one `Office Expense Settings` record containing:

- default expense category;
- default payment method;
- default cost center;
- enabled expense-category to expense-account mappings; and
- enabled payment-method to cash or bank-account mappings.

An administrator maintains this record. A manager may read it but cannot alter
the mappings. All configured accounts and cost centers must be active,
non-group records owned by that Company. Expense category accounts must have
the `Expense` root type and payment accounts must have the `Cash` or `Bank`
account type.

During installation and tenant provisioning, the app creates an additive
Company-owned default setup. It seeds Direct Expenses and Indirect Expenses
groups with Freight & Delivery, Loading & Unloading, Vehicle Fuel, Office Rent,
Utilities, Telephone & Internet, Office Supplies, Travel & Conveyance, Repairs
& Maintenance, and Miscellaneous Office Expense. It reuses an existing Cash
account and active Cost Center when available; otherwise it creates Office Cash
and Main for that Company. Cash is the default payment method, and Bank is
added when the Company already has an active bank ledger. Existing Office
Expense Setup records are never overwritten.

## User Workflow

The Office Expenses form exposes only:

- expense date;
- paid by;
- paid to;
- reference/receipt details and attachment;
- a table of expense category, description, and amount; and
- a calculated total.

Saving a draft creates no accounting entry. On submit, the server resolves all
configured accounts again and creates one native ERPNext `Journal Entry`:

- every expense line is debited to its configured expense account; and
- the total is credited to the configured cash or bank account.

The generated Journal Entry remains a hidden system link on the Office Expense
record. Cancelling the Office Expense first cancels that linked Journal Entry,
preserving a complete and reversible audit trail.

## Access

`Reckon Distribution Admin`, `Reckon Distribution Manager`, `Company Admin`,
and `Company Manager` can create, submit, cancel, print, and report on Office
Expenses. Only the two admin roles can change Office Expense Settings. SR, DSR,
and the standard Distribution User role have no Office Expense access.
