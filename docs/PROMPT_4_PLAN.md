# Prompt 4 implementation plan

Prompt 4 will be delivered in small, migration-safe slices. The parent `reckon_saas_platform` app remains generic; all distribution-specific masters and workflows stay in `reckon_distribution`.

## 1. Company-scoped master setup

- Add Company-owned distribution settings, UOM profile, route/territory records, warehouse policy, payment mappings, and terms.
- Reuse ERPNext `Item`, `Item Group`, `Brand`, `Price List`, `Item Price`, `Supplier`, `Customer`, `Warehouse`, and `UOM` wherever their standard fields are sufficient.
- Keep ERPNext UOM definitions shared and read-only to tenant users. Company UOM Profile controls enabled units and conversion usage.
- Add server-side Company ownership/validation for every custom record and every link to a tenant-owned record. Same names across companies remain valid.
- Company Admin and authorized Company Manager may maintain allowed master categories. SR/DSR roles get assigned-scope read-only catalogue access.

## 2. Safe lookup and permissions

- Implement Company-aware `permission_query_conditions`, `has_permission`, document validation, link search, reports, imports, exports, and API methods.
- Treat ERPNext Company Restrictions as an optional v17+ extra check only; never depend on them for v15/v16.
- Add adversarial fixtures for identical Item, Supplier, Customer, Price List, and Item Price names in Company A/B.

## 3. Supplier receipt and free goods

- Extend ERPNext Purchase Receipt through app hooks/custom fields for promotion source, supplier reference, terms, and physically received paid/free quantities.
- Use standard Purchase Receipt Item rows, Item UOM, conversion factors, batch/expiry, and warehouse fields. Add a small provenance child table only for data standard rows cannot represent.
- Validate that free quantities are actual supplier-provided SKU quantities, never distributor-authored offers. Shortages and disputes remain explicitly unresolved and are not marked received.
- Verify submitted receipts reconcile to Stock Ledger quantities and the source supplier reference.

## 4. Delivery order

1. DocTypes, custom fields, fixtures, and tenant permission tests.
2. Master setup screens and server APIs.
3. Purchase Receipt validation and free-goods reconciliation.
4. Cross-company adversarial tests for reads, links, submit, reports, imports, exports, and stock effects.
5. v15/v16 CI matrix, migration test, and deployment runbook.

No sales scheme builder or distributor-authored promotion engine is included in this phase.
