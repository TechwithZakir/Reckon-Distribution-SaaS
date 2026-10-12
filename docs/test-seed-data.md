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
native Supplier Delivery Note reference as the repeat-safe seed marker. Purchase
receipts create the stock used by the challans. Challans transfer stock to an
`RD Demo Van`, delivery notes issue that stock, and settlements return each
closing balance to the source warehouse. Collections and office expenses create
the normal Payment Entry postings, so cash, ledger, profit and loss, stock, sales,
and purchase reports have representative history.

The dates are distributed from six months before today through today. The script
uses a company-derived `RDDEMO-...` marker in masters, references, and idempotency
keys. A repeat run reuses existing records and only creates records missing from a
partially completed run. It never deletes or modifies normal tenant transactions.

Before posting transactions, the script verifies fiscal-year coverage for every
sample date. If the Company is missing an upcoming period, it creates or attaches
only the period needed, using the start month and day from the existing fiscal
calendar. A Company with no Fiscal Year at all is left unchanged and receives a
clear setup error instead of an invented accounting calendar.

Run it as a System Manager or with Bench, against a training, QA, or staging site:

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
