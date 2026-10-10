#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 --site <dedicated-test-site>"
    echo "Runs the Distribution SR/DSR transaction regression suite."
}

if [[ "${1:-}" != "--site" || -z "${2:-}" || -n "${3:-}" ]]; then
    usage >&2
    exit 2
fi

site_name="$2"
case "$site_name" in
    *test*|*staging*|localhost) ;;
    *)
        echo "Refusing to run transaction fixtures on non-test-looking site: $site_name" >&2
        exit 2
        ;;
esac

if ! command -v bench >/dev/null 2>&1; then
    echo "bench was not found on PATH" >&2
    exit 127
fi

modules=(
    reckon_distribution.tests.test_field_sales
    reckon_distribution.tests.test_collection
    reckon_distribution.tests.test_due_assignment
    reckon_distribution.tests.test_settlement
    reckon_distribution.tests.test_delivery
    reckon_distribution.tests.test_van_loading
    reckon_distribution.tests.test_purchase_receipt
)

for module in "${modules[@]}"; do
    echo "=== Running $module ==="
    bench --site "$site_name" run-tests --app reckon_distribution --module "$module"
done

echo "SR/DSR transaction regression suite passed."
