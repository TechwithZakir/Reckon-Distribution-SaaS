# Reckon Distribution SaaS

Reckon Distribution SaaS is a Bangla-first SR/DSR, FMCG distribution, and retailer
operations app for Frappe/ERPNext v15 and v16+.

This repository contains a reusable SaaS platform app plus the Distribution
business module. ERPNext remains the stock and accounting system of record. The
apps must stay independent of Frappe HRMS.

## Initial Scope

- SaaS platform package: `reckon_saas_platform`
- Distribution module package: `reckon_distribution`
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
