# Tenant isolation implementation audit

Reviewed 2026-10-10 against distribution-tenant-isolation-final-design.md.

## Changes in this review

- Team create/update verifies one matching standard Company User Permission before returning success.
- Permission synchronization preserves a correct record, removes stale permissions, checks the saved result, and clears the user's cache.
- Company permissions exclude descendant Companies, consistent with the one-Company design.
- Company Team & Access selects and locks the tenant Company. Platform administrators retain selection.
- Existing masters are checked against their stored Company before update; submitted ownership cannot override it.
- Master search rejects another user's identity supplied by a tenant caller.
- Native master scope bindings require matching ownership, including rejection of unowned masters.
- Guided setup checks native master ownership rather than relying only on scope rows.
- Team management rejects unrelated existing users, platform administrators, and cross-company routes.
- Service regression tests run in CI without a bench installation.

## Acceptance still required

These changes do not establish that the complete design has been implemented or deployed.

- Run Frappe database integration tests for both SaaS onboarding and Company Team & Access, including transaction rollback and User Permission filtering.
- Verify the deployed revision, assignment, and permission for the reported missing-permission user. The screenshot establishes missing permission but not its cause.
- Replace request-time write repair with a tested lifecycle that persists correctly across GET/POST requests without committing unrelated work.
- Complete assignment deletion, reassignment, expiry, concurrency, and role-removal lifecycle tests.
- Extend the ownership registry to cover custom parents, child records, and shared reference records; verify that registration installs all required hooks.
- Provide the administrator-facing conflict report and gate operational access for unresolved ownership conflicts.
- Verify automatic Company context across every native form and page, including quick entry and both supported Frappe versions.
- Perform migration dry run, conflict review, and live acceptance tests before declaring the design complete.

No live migration or production repair was performed in this review.
