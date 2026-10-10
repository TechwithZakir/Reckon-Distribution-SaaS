#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 --site <dedicated-test-site>"
    echo "Runs the Frappe multi-company isolation integration class."
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

exec bench --site "$site_name" run-tests \
    --app reckon_distribution \
    --module reckon_distribution.tests.test_multi_company_isolation
