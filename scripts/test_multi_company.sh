#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 --site <dedicated-test-site>"
    echo "Runs the tenant-isolation release gate: multi-company isolation, the P0"
    echo "go-live blocker tests (signup, subscription gate, desk guard, platform"
    echo "roles, seed job) and the SaaS onboarding tests."
}

if [[ "${1:-}" != "--site" || -z "${2:-}" || -n "${3:-}" ]]; then
    usage >&2
    exit 2
fi

site_name="$2"
case "$site_name" in
    *test*|*staging*|localhost) ;;
    *)
        echo "Refusing to run destructive fixtures on non-test-looking site: $site_name" >&2
        echo "Use a dedicated site name containing 'test' or 'staging'." >&2
        exit 2
        ;;
esac

if ! command -v bench >/dev/null 2>&1; then
    echo "bench was not found on PATH" >&2
    exit 127
fi

modules=(
    reckon_distribution.tests.test_multi_company_isolation
    reckon_distribution.tests.test_go_live_blockers
    reckon_distribution.tests.test_saas
    reckon_distribution.tests.test_saas_pages
)

for module in "${modules[@]}"; do
    echo "==> $module"
    bench --site "$site_name" run-tests --app reckon_distribution --module "$module"
done
