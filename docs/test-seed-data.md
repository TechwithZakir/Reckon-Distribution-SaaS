# Distribution Test Seed Data

`reckon_distribution.demo_data.seed_distribution_test_data` creates exactly 100
idempotent, company-isolated operational records for a training, QA, or staging
tenant. It covers the workflows implemented in the app, rather than inserting
unlinked report rows:

| Workflow | Records |
| --- | ---: |
| Purchase orders | 10 |
| Submitted purchase receipts | 10 |
| Submitted DSR challans | 10 |
| Submitted delivery notes | 20 |
| Confirmed DSR cash collections | 10 |
| Submitted DSR day settlements | 10 |
| Submitted office expenses | 10 |
| Outlet visits | 10 |
| SR sales orders | 10 |
| **Total** | **100** |

Each Purchase Receipt is mapped from its submitted Purchase Order and uses its
native Supplier Delivery Note reference as the repeat-safe seed marker. The seed
submits one linked Purchase Invoice per receipt and one linked Sales Invoice per
Delivery Note. Purchase receipts create the stock used by the challans. Challans
transfer stock to an `RD Demo Van`, delivery notes issue that stock, and
settlements return each closing balance to the source warehouse. Collections and
office expenses create the normal Payment Entry postings.

The 100 operational records therefore produce these additional ERPNext accounting
documents without changing the published 100-record total:

| Generated document | Records | Reports populated |
| --- | ---: | --- |
| Submitted Purchase Invoice | 10 | Purchase Register, Supplier Ledger, Supplier Aging |
| Submitted Sales Invoice | 20 | Sales Register, Customer Aging, Profit & Loss |
| Payment Entry / stock postings | workflow-driven | Cash Book, Day Book, Accounting Ledger, Stock Ledger |

Every seeded transaction uses an explicit daily posting sequence: receipt at
08:00, challan stock transfer at 08:45, deliveries at 12:00 and 13:00, and the
settlement stock reconciliation and return at the end of the day. Before each
delivery, the seed verifies the actual van stock ledger balance. It fails with a
precise diagnostic if the linked challan transfer was not posted; it never masks
an invalid lifecycle by adding unlinked stock movements.

The dates are distributed from six months before today through today. The script
uses a company-derived `RDDEMO-...` marker in masters, references, and idempotency
keys. A repeat run reuses existing records and only creates records missing from a
partially completed run. It never deletes or modifies normal tenant transactions.

Before posting transactions, the script verifies fiscal-year coverage for every
sample date. If the Company is missing an upcoming period, it creates or attaches
only the period needed, using the start month and day from the existing fiscal
calendar. A Company with no Fiscal Year at all is left unchanged and receives a
clear setup error instead of an invented accounting calendar.

Run the read-only preflight first. It verifies migrations, Company receivable and
payable defaults, and the fixed 100-record plan without changing data:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.preflight_distribution_test_data \
  --kwargs '{"company":"Horizon"}'
```

Then run it as a System Manager or with Bench, against a training, QA, or staging
site:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.seed_distribution_test_data \
  --kwargs '{"company":"Horizon"}'
```

The selected company must already have ERPNext chart-of-accounts defaults, one
leaf warehouse, and leaf Item Group, Customer Group, Supplier Group, and Territory
records. The normal Distribution installation seed supplies the office-expense
account mappings; the test seed ensures they are present before transactions are
created. Run `bench --site <site> migrate` before the seed: it checks all required
ERPNext and Distribution fields before writing any transaction and reports an
actionable migration error when the schema is outdated.

After a seed or an interrupted-run recovery, run the read-only integrity audit.
It checks document counts, submitted statuses, stock-ledger postings, GL entries,
and every native link that makes the operational and accounting reports usable:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.audit_distribution_test_data \
  --kwargs '{"company":"Horizon"}'
```

## Roll Back the RD Demo Dataset

The rollback keeps shared setup, Fiscal Years, and `RDDEMO-...` master records,
but reverses and removes the test transactions. Submitted documents are cancelled
in dependency order so ERPNext reverses stock and accounting entries correctly.

Preview exactly what will be affected first. This makes no changes:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.rollback_distribution_test_data \
  --kwargs '{"company":"Horizon"}'
```

Run the rollback only after reviewing the preview:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.rollback_distribution_test_data \
  --kwargs '{"company":"Horizon","dry_run":false,"confirm_rollback":true}'
```

## Reset Transactions and Demo Masters

Use the full reset before recreating the sample data with the current Bangladesh
FMCG labels. It removes only records carrying this Company's `RDDEMO` marker:
the linked transactions, their marker-scoped stock/accounting ledger rows, item
prices, route assignments, tenant master scopes, demo route, items, customers,
and supplier. Demo warehouses with stock history are retained but disabled, so
the replacement active warehouses are the only ones available to workflows. It
retains Company settings, accounts, fiscal years, and non-demo records.

Preview the reset first:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.reset_distribution_test_data \
  --kwargs "{'company':'Horizon'}"
```

Then confirm the reset:

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.reset_distribution_test_data \
  --kwargs "{'company':'Horizon','dry_run':False,'confirm_reset':True}"
```

The recreated dataset uses `Dhaka North FMCG Distribution Hub - Tejgaon`, a
`Mirpur 10 DSR Sales Van`, and the Mirpur 10 - Kazipara retail route. It creates
five named Dhaka retailers, `Sundarban FMCG Distributors Ltd.`, and recognizable
Bangladesh FMCG packs: soybean oil, iodized salt, biscuits, mango bars, and
washing powder. Each visible master also carries a small `RD Demo` suffix so it
is clearly test data and can be selected safely by a later reset.

## Lifecycle Test

For QA, run a complete seed, audit, and rollback exercise. It refuses to run if
an RD Demo dataset is already present, and it removes every created transaction
after the audit passes. It retains shared demo masters and fiscal years.

```bash
bench --site distribution-test.localhost execute \
  reckon_distribution.demo_data.test_distribution_demo_data_lifecycle \
  --kwargs '{"company":"Horizon","confirm_cleanup":true}'
```
