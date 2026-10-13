"""Seed-lifecycle regression tests runnable without a Frappe database."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
DEMO_DATA = ROOT / "reckon_distribution" / "demo_data.py"
VAN_LOADING = ROOT / "reckon_distribution" / "van_loading.py"
SETTLEMENT = ROOT / "reckon_distribution" / "settlement.py"


def _module():
    return ast.parse(DEMO_DATA.read_text(encoding="utf-8"))


def _assignment_value(module: ast.Module, name: str):
    assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _called_names(function: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


class DistributionDemoSeedContractTests(unittest.TestCase):
    def setUp(self):
        self.module = _module()

    def test_seed_keeps_the_requested_one_hundred_operational_records(self):
        record_count = _assignment_value(self.module, "DEMO_RECORD_COUNT")
        transaction_plan = _assignment_value(self.module, "TRANSACTION_PLAN")

        self.assertEqual(record_count, 100)
        self.assertEqual(sum(count for _, count in transaction_plan), record_count)

    def test_delivery_and_invoice_posting_times_are_in_daily_order(self):
        delivery_plan = _assignment_value(self.module, "DELIVERY_PLAN")

        self.assertEqual(len(delivery_plan), 2)
        self.assertEqual(sum(quantity for quantity, _, _ in delivery_plan), 40)
        self.assertTrue(all(delivery_time < invoice_time for _, delivery_time, invoice_time in delivery_plan))
        self.assertEqual(tuple(delivery_time for _, delivery_time, _ in delivery_plan), ("12:00:00", "13:00:00"))

    def test_seed_checks_the_real_van_balance_without_creating_unlinked_stock(self):
        delivery = _function(self.module, "_delivery")
        stock_check = _function(self.module, "_assert_delivery_stock")
        delivery_source = ast.unparse(delivery)
        stock_check_source = ast.unparse(stock_check)

        self.assertIn("_assert_delivery_stock", delivery_source)
        self.assertIn("get_stock_balance", stock_check_source)
        self.assertNotIn("frappe.get_doc", stock_check_source)

    def test_seeded_challans_and_settlements_have_fixed_daily_posting_times(self):
        demo_data = DEMO_DATA.read_text(encoding="utf-8")
        van_loading = VAN_LOADING.read_text(encoding="utf-8")
        settlement = SETTLEMENT.read_text(encoding="utf-8")

        self.assertIn('DEMO_CHALLAN_POSTING_TIME = "08:45:00"', demo_data)
        self.assertIn("doc.flags.rd_stock_entry_posting_time = DEMO_CHALLAN_POSTING_TIME", demo_data)
        self.assertIn('SEED_STOCK_ENTRY_POSTING_TIME_FLAG = "rd_stock_entry_posting_time"', van_loading)
        self.assertIn("_apply_seed_stock_entry_time(doc, stock_entry)", van_loading)
        self.assertIn('STOCK_RECONCILIATION_POSTING_TIME = "22:45:00"', settlement)
        self.assertIn('STOCK_RETURN_POSTING_TIME = "23:00:00"', settlement)

    def test_outlet_visit_audit_uses_its_actual_status_field(self):
        source = DEMO_DATA.read_text(encoding="utf-8")

        self.assertIn('status_field="visit_status"', source)
        self.assertIn("row.get(status_field) != status", source)

    def test_demo_reset_and_bangladesh_fmcg_masters_are_explicitly_scoped(self):
        source = DEMO_DATA.read_text(encoding="utf-8")

        self.assertIn("def reset_distribution_test_data(", source)
        self.assertIn("confirm_reset", source)
        self.assertIn("def _demo_master_plan(", source)
        self.assertIn("def _remove_demo_ledger_rows(", source)
        self.assertIn("Meghna FMCG Supply Ltd.", source)
        self.assertIn("Mirpur 10 Delivery Van", source)
        self.assertIn("Bengal Harvest Mustard Oil 1 L", source)

    def test_rollback_cancels_dependent_documents_before_their_sources(self):
        rollback_order = _assignment_value(self.module, "ROLLBACK_ORDER")

        self.assertLess(rollback_order.index("DSR Day Settlement"), rollback_order.index("DSR Challan"))
        self.assertLess(rollback_order.index("Sales Invoice"), rollback_order.index("Delivery Note"))
        self.assertLess(rollback_order.index("Delivery Note"), rollback_order.index("DSR Challan"))
        self.assertLess(rollback_order.index("Purchase Invoice"), rollback_order.index("Purchase Receipt"))
        self.assertLess(rollback_order.index("Purchase Receipt"), rollback_order.index("Purchase Order"))

    def test_lifecycle_test_runs_seed_audit_and_confirmed_rollback(self):
        lifecycle = _function(self.module, "test_distribution_demo_data_lifecycle")
        names = _called_names(lifecycle)
        source = ast.unparse(lifecycle)

        self.assertTrue({"seed_distribution_test_data", "audit_distribution_test_data", "rollback_distribution_test_data"}.issubset(names))
        self.assertIn("confirm_cleanup", source)
        self.assertIn("confirm_rollback=True", source)


if __name__ == "__main__":
    unittest.main()
