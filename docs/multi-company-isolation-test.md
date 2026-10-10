# Multi-company isolation test

## Purpose

This test verifies the approved Distribution tenant-isolation design on a real
Frappe/ERPNext test site. It is an integration test, not a production data
migration and not a browser-only permission check.

The test class is:

```text
reckon_distribution.tests.test_multi_company_isolation.TestMultiCompanyIsolation
```

The runner is:

```text
scripts/test_multi_company.sh
```

## Safety boundary

Run this only on a dedicated test or staging site. The runner accepts only site
names containing `test`, `staging`, or `localhost`. It must not be pointed at
`distribution.reckon.tech` because the class creates and removes temporary
companies, users, assignments, permissions, and native master records.

The fixtures use random suffixes, so repeated test runs do not reuse normal
business records. The class explicitly removes records it creates during
teardown. Frappe's test transaction handling also rolls back the test work when
the test runner supports transactional tests.

## Prerequisites

The selected bench site must have these apps installed:

- Frappe
- ERPNext
- `reckon_saas_platform`
- `reckon_distribution`

The app code must be updated before running the test:

```bash
cd ~/frappe-bench
git -C apps/reckon_distribution pull --ff-only origin main
bench --site distribution-test.localhost migrate
```

If the dedicated site has not been created yet, create it separately before
running the test:

```bash
bench new-site distribution-test.localhost
bench --site distribution-test.localhost install-app erpnext
bench --site distribution-test.localhost install-app reckon_saas_platform
bench --site distribution-test.localhost install-app reckon_distribution
bench --site distribution-test.localhost migrate
```

## Run command

From the bench root:

```bash
apps/reckon_distribution/scripts/test_multi_company.sh \
  --site distribution-test.localhost
```

The runner executes:

```bash
bench --site distribution-test.localhost run-tests \
  --app reckon_distribution \
  --module reckon_distribution.tests.test_multi_company_isolation
```

To run the class directly without the wrapper:

```bash
bench --site distribution-test.localhost run-tests \
  --module reckon_distribution.tests.test_multi_company_isolation
```

## What the test creates

For each test method, the class generates a random suffix and creates two
companies:

- `_RD Isolation A <suffix>`
- `_RD Isolation B <suffix>`

It creates two users and assigns one active Company to each user. The Company A
user receives the Company Admin role and the Company B user receives the Master
Data Manager role.

The setup provisions only missing ERPNext reference fixtures needed by a
minimal test site:

- Item Group
- UOM
- non-group Customer Group
- non-group Supplier Group
- non-group Territory

Existing reference records are reused and are not deleted. Only fixtures created
by this test are tracked for cleanup.

## Test coverage

### SaaS onboarding permission

`test_saas_onboarding_creates_one_company_permission` calls the same SaaS
registration service used by tenant onboarding. It verifies that onboarding
creates:

- the tenant Company;
- the tenant User;
- the active `Tenant User Assignment`;
- exactly one `User Permission` with `Allow = Company`;
- `For Value` equal to the tenant Company;
- `Apply to All Document Types = Yes`;
- `Is Default = Yes`.

The temporary SaaS plan, registration, subscription, payment, provisioning job,
user, assignment, permission, and Company are removed afterward.

### Company Team & Access permission

`test_company_team_access_creates_user_assignment_and_permission` logs in as
the Company A admin and calls `create_team_access` with a DSR profile. It
verifies that the Distribution flow creates the team User and assignment, then
materializes exactly the same standard Company User Permission as SaaS
onboarding.

This proves that the two user-creation flows converge on the same assignment
and permission service.

### Native master list and link isolation

`test_company_a_lists_only_its_native_masters` creates separate records for
Company A and Company B for all five company-owned ERPNext masters:

- Item
- Customer
- Supplier
- Price List
- Item Price

It then verifies that Company A's application-level master search returns its
own record but not Company B's record. It also checks the registered permission
query condition contains Company A and not Company B.

### Cross-company read, edit, delete, and link denial

`test_cross_company_open_edit_and_link_are_denied` loads Company B records and
checks, while acting as the Company A user, that:

- Frappe read permission is denied;
- Frappe delete permission is denied;
- Distribution master write permission is denied;
- controller validation rejects mutation;
- an Item Price cannot be validated when its Item and Price List belong to the
  other Company.

This checks defense in depth. User Permission is not treated as the only
security layer.

### Automatic Company context and Item Code behavior

`test_new_forms_bind_company_and_item_code_is_name_based` verifies that a new
native form receives the authenticated user's Company automatically. The test
also verifies that tenant Item Code normalization uses Item Name as the normal
business-facing code.

### Assignment lifecycle

`test_assignment_change_removes_old_permission_and_materializes_new_one`
deactivates the Company A assignment, creates a replacement Company B
assignment, and verifies that only the Company B User Permission remains.

The test intentionally does not edit the Company field on an existing active
assignment. Company ownership is immutable after assignment creation; a move is
performed as deactivate-old plus create-new.

`test_two_active_company_assignments_are_rejected` verifies that a normal user
cannot receive two active Company assignments.

## Fixture problems found and fixed

The first run failed before security assertions because ERPNext company
creation tried to bootstrap default warehouses and the minimal test site did
not contain `Warehouse Type: Transit`. That warehouse setup is unrelated to
tenant isolation, so the tests now bypass ERPNext's Company `on_update`
warehouse bootstrap while creating temporary test companies. Production
company creation is not changed, and no global ERPNext asset is modified.

The second run exposed missing default Item Group and UOM records. The test now
creates temporary reference records when required.

The next run selected group-type Customer/Supplier groups. ERPNext correctly
rejects group nodes as transaction master groups, so the test now selects or
creates non-group references.

An assignment lifecycle assertion initially attempted to change the Company on
an existing assignment. The application correctly rejected that mutation. The
test now models the approved immutable-assignment lifecycle.

These failures were test-environment and test-fixture issues. They did not
indicate a bypass of tenant isolation.

The transaction suite also exposed two Frappe 16 test-mocking issues. Delivery
approval and Van Loading approval tests patched `frappe.get_doc` with mock
objects containing local lambdas; Frappe's timezone cache then attempted to
pickle those objects. Those tests now mock the module-local `now_datetime`
dependency instead. The Purchase Receipt test had its own direct Company
fixture and now uses the same test-only Company bootstrap isolation.

## Expected result

A successful run ends with a passing unittest summary and no traceback. The
important acceptance result is that all tests in
`TestMultiCompanyIsolation` pass, including the five native master isolation
checks and both user-creation paths.

If a test fails, preserve the first traceback and inspect the first exception;
later failures may be cascading fixture failures. Do not run the suite on the
production site to investigate.

## Local repository checks

The integration class requires a Frappe bench and cannot run in the lightweight
Windows checkout without Frappe/ERPNext installed. The repository checks that
can run without a bench are:

```powershell
uvx ruff check .
.\.venv\Scripts\python.exe -m compileall -q reckon_distribution
.\.venv\Scripts\python.exe -m unittest discover \
  -s tests -p test_company_permission_service.py -v
```

The standalone tests cover the permission synchronization and master ownership
service with mocked Frappe calls. The class documented here covers the real
database, hooks, roles, User Permission records, native masters, and tenant
context on a bench site.

## SR/DSR transaction regression suite

The tenant-isolation class is complemented by the transaction runner:

```bash
apps/reckon_distribution/scripts/test_distribution_transactions.sh \
  --site distribution-test.localhost
```

The runner accepts either form below and should be invoked from the bench
root:

```bash
bash apps/reckon_distribution/scripts/test_distribution_transactions.sh \
  --site distribution-test.localhost

bash apps/reckon_distribution/scripts/test_distribution_transactions.sh \
  --site=distribution-test.localhost
```

It rejects production-looking site names, requires `bench` on `PATH`, reports
the exact module that failed, and stops at the first failing module. Using
`bash` explicitly also avoids executable-bit problems after a server checkout.

It runs these transaction modules in order:

1. `test_field_sales`: SR outlet visits, SR orders, UOM conversion, GPS, and
   field queue validation.
2. `test_collection`: DSR cash, cheque, bank, and MFS collection states,
   confirmation, verification, cancellation, and idempotency.
3. `test_due_assignment`: DSR retailer due assignment approval, overlap, and
   cancellation rules.
4. `test_settlement`: DSR cash and stock reconciliation equations, variance
   explanations, submission, and approval.
5. `test_delivery`: distribution delivery assignment, saleable/supplier-free
   controls, return inspection, stock receipt approval, and cancellation.
6. `test_van_loading`: manager approval, stock transfer linkage, DSR loading
   acknowledgement, rejection reasons, cancellation, and amendment rules.
7. `test_purchase_receipt`: supplier-free stock and purchase-receipt
   reconciliation controls.

This suite is a transaction-controller regression suite. The multi-company
class above is the database-backed ownership and permission test. Both runners
must pass before a release is considered functionally verified.

## Latest verified workflow

The following sequence was used on ERPNext/Frappe 16:

```bash
cd ~/frappe-bench
git -C apps/reckon_distribution fetch origin main
git -C apps/reckon_distribution reset --hard origin/main

bench --site distribution-test.localhost run-tests \
  --app reckon_distribution \
  --module reckon_distribution.tests.test_multi_company_isolation

bash apps/reckon_distribution/scripts/test_distribution_transactions.sh \
  --site distribution-test.localhost
```

The multi-company suite completed with:

```text
Ran 7 tests
OK
```

The final test-runner fixes are represented by commits `665dc78`, `801a220`,
`5a09d51`, `d49fbd2`, `5c37cca`, and `6441cb0`. A later checkout should always
pull the current `origin/main` rather than cherry-picking these individually.
