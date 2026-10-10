# Reckon Distribution SaaS

Reckon Distribution SaaS is a Bangla-first SR/DSR, FMCG distribution, and retailer
operations app for Frappe/ERPNext v15 and v16+.

This repository contains the Distribution business module. It depends on the
separate parent `reckon_saas_platform` app for tenant identity, subscription,
payment, provisioning, and SaaS route gates. ERPNext remains the stock and
accounting system of record. The apps must stay independent of Frappe HRMS.

## Initial Scope

- Distribution module package: `reckon_distribution`
- Required parent app: `reckon_saas_platform`
- Supported dependencies: Frappe `>=15,<17` and ERPNext `>=15,<17`
- Distribution workspace and navigation shell
- App roles and home-page routing for operational users
- Version compatibility helpers for Frappe/ERPNext v15/v16
- Bangladesh Bangla translation and glossary seed
- CI matrix for Frappe/ERPNext v15 and v16
- Tenant User Assignment and server-side tenant resolver foundation
- SaaS plan, registration, subscription, payment, tenant assignment, and
  provisioning gate foundation
- Distribution registers as the first SaaS module through `reckon_saas_modules`

Business transactions, stock postings, accounting postings, offline sync, and PWA
workflows are intentionally deferred to later phases.

## Bench Install Order

Install the separate parent platform app before the Distribution module:

```bash
bench get-app reckon_saas_platform <platform-repo-url>
bench get-app reckon_distribution <distribution-repo-url>
bench --site distribution.reckon.tech install-app reckon_saas_platform
bench --site distribution.reckon.tech install-app reckon_distribution
```

For an existing site that already has `reckon_distribution`, pull the code first,
install `reckon_saas_platform`, then migrate. The SaaS DocTypes are owned by the
platform app; `reckon_distribution` depends on it and registers itself as a SaaS
module.

## Multi-company integration test

Run the end-to-end isolation class only against a dedicated test or staging site.
The runner creates uniquely named fixtures and cleans them up; it refuses ordinary
production-looking site names:

```bash
./scripts/test_multi_company.sh --site distribution-test.localhost
```

The class verifies SaaS onboarding, Company Team & Access, standard Company User
Permission materialization, assignment changes, native master list/link filtering,
automatic company context, item-code generation, and cross-company mutation/link
rejection. It requires the `reckon_saas_platform` and `erpnext` apps to be installed
on the selected site.
