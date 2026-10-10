# Distribution Tenant Isolation and Master Ownership

## Status

**Approved design; implementation is being delivered in security-first stages.**

This document finalizes the decisions from the current discussion before code changes continue.

## 1. Tenant model

Each normal tenant user has one active Company. The Company is determined on the server from the user's active tenant assignment; it is never trusted from a browser field or URL.

The system has two supported user-creation flows:

| Flow | Actor | Source record | Required result |
| --- | --- | --- | --- |
| SaaS onboarding | SaaS platform administrator | `Tenant User Assignment` | User, role, active Company assignment, and standard Company User Permission |
| Company team access | Company Admin inside Distribution | `Tenant User Assignment` | User, role, active Company assignment, and standard Company User Permission |

Both flows must converge on the same assignment service. They must not implement separate permission rules.

## 2. Standard User Permission

For every active assignment, the server creates or updates exactly one standard Frappe record:

```text
User Permission
  User: <user>
  Allow: Company
  For Value: <assigned Company>
  Apply to All Document Types: Yes
  Is Default: Yes
```

When an assignment is deactivated, the Company User Permission is removed. When an assignment changes Company, the old permission is removed and the new one is materialized. A normal user with two active Companies is rejected and must not receive ambiguous access.

This synchronization must run on:

- SaaS tenant-admin creation and assignment update.
- Distribution Company Team & Access creation, update, and deactivation.
- Assignment migration/backfill.

The operation must be idempotent and safe to retry.

## 3. Roles and access

The Company Admin role may manage only the assigned Company and the Distribution workflows. It may create and maintain team users, routes, warehouses, and Company-owned masters through the guided/native Distribution entry points.

Operational roles remain narrower:

- Company Manager: operational setup and management allowed by the role profile.
- Master Data Manager: Company-owned master maintenance.
- SR/DSR: only field and delivery workflows allowed by the role profile.

The server must continue to enforce Company ownership even if a role, route, direct URL, list filter, or browser request is manipulated. User Permission is the standard Frappe visibility layer; app validation and permission-query hooks are the defense-in-depth layer.

## 4. Company-owned master records

The following records are separate records per Company. The same record must never be used by two Companies:

- `Item`
- `Customer` (Retailer)
- `Supplier`
- `Item Price`
- `Price List`

Each record receives an app-managed Link field to `Company`, for example `rd_company`, labelled **Company**. The field is server-managed and read-only for tenant users. It is populated from the authenticated tenant context during create and cannot be changed to another Company during update.

The standard Company User Permission can then filter these native doctypes because they contain a real Company link. The app must also provide permission-query conditions and controller validation so direct API calls cannot bypass the restriction.

### Item rules

- Item Name is the business-facing required value.
- Item Code is read-only in the guided/quick entry experience and is normally generated from Item Name.
- ERPNext Item Code is globally unique. If the same Item Name is created for another Company and the generated code collides, the backend must generate a deterministic Company-specific Item Code while preserving the same Item Name.
- Item Group, Stock UOM, sales/purchase flags, and conversion rows remain authoritative in ERPNext.
- The Item Company is assigned automatically and cannot be selected by a tenant user.

### Customer and Supplier rules

- Native ERPNext Customer and Supplier remain authoritative.
- Their Company link is maintained by the Distribution app.
- Retailer/Supplier profile information remains app-specific and is not used as a substitute for ownership.
- A tenant user can see, create, edit, and deactivate only records owned by the active Company.

### Item Price and Price List rules

- `Item Price` and `Price List` also carry Company ownership.
- Price records cannot point to an Item or Price List owned by another Company.
- Effective dates, selling/purchase flags, UOM, and rates remain ERPNext-authoritative.
- The setup UI may provide friendly price setup, but the backend writes the native ERPNext records.

## 5. Distribution Master Scope

`Distribution Master Scope` remains a compatibility and audit binding for the guided setup and existing data. It is not the primary ownership authority for the five Company-owned native masters after migration.

For the five master doctypes:

1. The native record's Company field is authoritative.
2. Scope rows may be maintained for existing guided workflows and audit history.
3. New cross-Company scope rows must be rejected.
4. A native record with no unambiguous Company owner must not be exposed to a tenant until an administrator resolves it.

## 6. Future DocType security contract

This model applies to every future Distribution master, global record, custom object, and custom DocType. A new DocType must not be added to the application until its ownership class is declared:

- **Company-owned:** the record contains an app-managed Link to `Company`, is automatically assigned to the authenticated Company, participates in standard User Permission filtering, and has server-side query, create, update, delete, and link validation.
- **Child of a Company-owned record:** the record carries a validated parent or Company reference and cannot cross the parent's Company boundary.
- **System-global:** the record is intentionally shared across tenants, is read-only to tenant users unless explicitly approved, and is excluded from Company-specific setup writes.

The default is **Company-owned**. A developer must not rely on a scope table, browser-selected Company, list filter, role name, or UI visibility alone to protect a new record.

For every new Company-owned DocType, the implementation checklist is mandatory:

1. Add the Company link or validated Company parent reference.
2. Register a permission query condition for tenant list and link searches.
3. Register controller validation for automatic Company assignment and cross-Company rejection.
4. Confirm standard User Permission filtering works through the Company link.
5. Add role permissions for each Distribution role that needs access.
6. Add migration/backfill logic for existing records.
7. Add cross-Company API, list, link, create, update, and delete tests.
8. Add the DocType to the Distribution workspace only when its security contract is complete.

The application should maintain a central ownership registry so new objects are reviewed consistently rather than relying on scattered one-off hooks.

## 7. Automatic Company context

When a tenant user logs in, the active Company is resolved from the user's single active assignment and its standard Company User Permission. Distribution pages, native master lists, link fields, quick entry, and API methods must use that Company automatically.

Tenant users must not repeatedly select a Company in every page or document. Company fields should be hidden or read-only in guided forms and native forms where possible. If a Company field is technically required by ERPNext, the server sets it from the authenticated tenant context and rejects a different submitted value.

If there is no active Company assignment, the user sees a clear setup/access message and cannot enter Company-owned operations. If multiple active Companies are detected, the system blocks operational access until the assignment conflict is resolved; it must not present an arbitrary Company selector as a workaround.

System administrators may retain explicit Company selection for administration and migration tasks, but tenant users must remain restricted to their assigned Company.

## 8. Migration and conflict handling

The migration must:

1. Add the Company link field to each of the five native doctypes.
2. Backfill ownership from existing active scope rows only when exactly one Company owns the record.
3. Mark or log records with no owner.
4. Mark or log records scoped to multiple Companies as conflicts; never choose an owner silently.
5. Backfill standard User Permission records from active `Tenant User Assignment` rows.
6. Validate that Item, Customer, Supplier, Item Price, and Price List references do not cross Companies.
7. Provide an administrator report/list of unresolved master ownership conflicts before tenant operations are unlocked.

## 9. User-facing behaviour

Tenant users must not enter or edit an internal Company, master type, access scope, or profile binding in native setup forms. The UI should show friendly labels such as:

- Product setup
- Retailer setup
- Supplier setup
- Sales price
- Enabled for this Company
- Warehouse setup

The Company may be displayed as read-only context where useful, but the server remains authoritative.

## 10. Required implementation order

1. Add the Company fields and ownership migration for the five native master doctypes.
2. Centralize User Permission synchronization for both SaaS and Distribution assignment flows.
3. Add native-master controller validation and permission-query isolation.
4. Update guided setup methods and link searches to use Company-owned records.
5. Make Item quick entry use Item Name as the primary entry and keep Item Code read-only.
6. Add conflict reporting and migration diagnostics.
7. Add role and User Permission backfill for existing users.
8. Run automated tests and a live-site migration dry run.
9. Deploy only after the acceptance checks below pass.

## 11. Acceptance tests

### User permissions

- SaaS-created tenant admin gets exactly one active Company User Permission.
- Distribution-created team user gets exactly one active Company User Permission.
- Assignment update changes the permission without leaving the old Company permission.
- Assignment deactivation removes the permission.
- A user cannot receive two active Company assignments.

### Master isolation

- Company A cannot list, search, open, edit, delete, or link to Company B's Item, Customer, Supplier, Item Price, or Price List.
- Company A cannot create a record with Company B ownership.
- Native forms and quick entry automatically assign the authenticated Company.
- Direct API calls fail on cross-Company links and mutations.
- A shared legacy record is reported as a migration conflict and is not silently reused.

### Item setup

- Item Name is required.
- Item Code is not an entry requirement for tenant users.
- Item Code is generated and remains globally unique.
- Same Item Name may exist as separate Company-owned records, subject to ERPNext's global Item Code constraint.

### Future DocTypes and automatic context

- A newly registered Company-owned custom DocType automatically receives Company assignment and tenant query filtering.
- A child record cannot reference a parent owned by another Company.
- Tenant list views, link fields, quick entry, and API calls use the assigned Company without repeated Company selection.
- A tenant user with no assignment is blocked from Company-owned operations.
- A user with conflicting active assignments is blocked until the conflict is resolved.

## 12. Approval gate

The first implementation stage is the migration and tests for Company-owned native masters plus the shared User Permission synchronization service. UI refinements come after those security invariants are passing.

## 13. Operational Navigation and Reporting

The Distribution shell groups work by operational purpose: **Sales & Delivery**,
**Procurement**, **Inventory & Stock**, **Reports**, and **Administration**. This
layout is navigation only; it does not introduce parallel transaction records.

`Field Sales` remains the guided field-work page. Its history is stored in the
native `SR Order` and `Outlet Visit` lists. `DSR Delivery & Collection` remains
the guided execution page, with native `Delivery Note` and `DSR Collection
Receipt` lists as its history and audit trail. These lists are available in the
Distribution Home without cluttering the left navigation.

Stock movement is represented by ERPNext `Stock Ledger Entry`; no custom stock
ledger is maintained. Distribution users may read, print, export, and report on
only entries in their resolved Company. The Reports menu exposes native Stock
Ledger directly to operational roles. Managers and administrators additionally
receive Accounts Payable; field roles remain limited to reports required to run
routes and reconcile stock.

The Distribution Home dashboard gets its Company only from the authenticated
tenant context. It displays server-calculated KPI totals and recent records for
that Company and period. Browsers never provide a Company identifier for
dashboard, ledger, or report data.

## 14. Next Development: Tenant Transaction IDs

Add an immutable, user-facing `rd_transaction_id` to each approved transaction
DocType. This is a business identifier only; Frappe's native `name` remains the
technical primary key for links, amendments, accounting references, and routes.
The native identifier is hidden from normal form, list, print, and user-facing
message layouts.

The visible format is:

```text
<DOCTYPE>-<DDMMYY>-<SEQUENCE>
```

Examples:

```text
DN-101026-000023
DCR-101026-000023
PR-101026-000023
```

The required database rule is:

```text
Company + rd_transaction_id = unique
```

The sequence is therefore independent for each Company, DocType, and document
date. Two tenants may legitimately use the same visible transaction ID; one
tenant may not create the same ID twice. The server resolves Company from the
authenticated tenant, validates the document party and date, atomically
allocates the next sequence, and never accepts a browser-supplied identifier.

Initial scope: `Delivery Note`, `DSR Collection Receipt`, `SR Order`,
`Purchase Receipt`, and `Purchase Invoice`. DSR Challan does not contain a
Customer, so it requires a separate route/DSR-based identifier rule if included.
Supplier transactions use the same Company-scoped uniqueness rule but do not
embed customer information.

Identifiers are allocated on submission using the final posting date. They are
never edited, reused after cancellation, or copied unchanged to amendments.
Retries must resolve an existing idempotency key before a new identifier is
allocated. The implementation requires an internal, lock-protected counter
keyed by Company, DocType, and document date, plus an explicit composite unique
database index.
