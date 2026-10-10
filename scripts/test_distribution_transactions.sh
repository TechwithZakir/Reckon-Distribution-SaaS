#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    cat <<'USAGE'
Usage:
  test_distribution_transactions.sh --site <dedicated-test-site>
  test_distribution_transactions.sh --site=<dedicated-test-site>

Runs the Distribution SR/DSR transaction regression suite.
USAGE
}

site_name=""
while (($#)); do
    case "$1" in
        --site)
            [[ $# -ge 2 ]] || { echo "Missing value for --site" >&2; usage >&2; exit 2; }
            site_name="$2"
            shift 2
            ;;
        --site=*)
            site_name="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$site_name" ]]; then
    echo "A dedicated test site is required." >&2
    usage >&2
    exit 2
fi

case "$site_name" in
    *test*|*staging*|*localhost) ;;
    *)
        echo "Refusing to run transaction fixtures on non-test-looking site: $site_name" >&2
        exit 2
        ;;
esac

command -v bench >/dev/null 2>&1 || {
    echo "bench was not found on PATH. Run this from the Frappe bench environment." >&2
    exit 127
}

modules=(
    reckon_distribution.tests.test_field_sales
    reckon_distribution.tests.test_collection
    reckon_distribution.tests.test_due_assignment
    reckon_distribution.tests.test_settlement
    reckon_distribution.tests.test_delivery
    reckon_distribution.tests.test_van_loading
    reckon_distribution.tests.test_purchase_receipt
)

failed_module=""
trap 'status=$?; if (( status != 0 )); then echo "FAILED: ${failed_module:-transaction test runner setup}" >&2; fi; exit "$status"' EXIT

for module in "${modules[@]}"; do
    failed_module="$module"
    printf '\n=== Running %s on %s ===\n' "$module" "$site_name"
    bench --site "$site_name" run-tests \
        --app reckon_distribution \
        --module "$module"
done

failed_module=""
echo
echo "SR/DSR transaction regression suite passed."
