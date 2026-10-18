"""Office Expense ships with reckon_accounts; Distribution keeps only its scope (no database)."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).parents[1] / "reckon_distribution"


def _hooks() -> dict:
    """Top-level literal assignments of hooks.py, without importing frappe."""
    values = {}
    for node in ast.parse((APP / "hooks.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                values[node.targets[0].id] = node.value
    return values


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OfficeExpenseOwnershipTests(unittest.TestCase):
    def test_distribution_requires_reckon_accounts(self):
        self.assertIn("reckon_accounts", _hooks()["required_apps"])

    def test_distribution_no_longer_overrides_payment_entry(self):
        self.assertNotIn("override_doctype_class", _hooks())
        self.assertFalse((APP / "overrides").exists())

    def test_office_expense_code_and_doctypes_are_gone(self):
        self.assertFalse((APP / "office_expense.py").exists())
        self.assertEqual(list((APP / "distribution" / "doctype").glob("office_expense*")), [])
        for path in APP.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("reckon_distribution.office_expense", source)
                self.assertNotIn("reckon_distribution.overrides", source)

    def test_link_field_is_left_to_reckon_accounts(self):
        source = (APP / "install.py").read_text(encoding="utf-8")
        self.assertNotIn('"fieldname": "rd_office_expense"', source)
        self.assertIn("from reckon_accounts.office_expense import _category_map", source)

    def test_tenant_scope_and_menus_stay_in_distribution(self):
        source = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"Office Expense": "reckon_saas_platform.tenant_security.get_tenant_owned_query"', source)
        self.assertIn(
            '"Office Expense Settings": "reckon_saas_platform.tenant_security.has_tenant_owned_permission"',
            source,
        )
        sidebar = (APP / "distribution" / "sidebar" / "distribution" / "distribution.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"link_to": "Office Expense"', sidebar)


class OfficeExpenseDefaultsSeedTests(unittest.TestCase):
    """The default Office Expense Settings seed now lives in reckon_accounts."""

    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda text: text
        frappe.throw = Mock(side_effect=AssertionError)
        frappe.db = SimpleNamespace(exists=Mock(return_value=True))
        frappe.get_doc = Mock()
        frappe.get_all = Mock(return_value=[])
        setup = ModuleType("reckon_accounts.office_expense_setup")
        setup.ensure_office_expense_defaults = Mock(return_value=["Office Expense Settings"])
        master_data = ModuleType("reckon_distribution.master_data")
        master_data.get_or_create_company_sales_price_list = Mock()
        self.frappe, self.setup = frappe, setup
        self.modules = {
            "frappe": frappe,
            "frappe.permissions": ModuleType("frappe.permissions"),
            "reckon_accounts": ModuleType("reckon_accounts"),
            "reckon_accounts.office_expense_setup": setup,
            "reckon_distribution.master_data": master_data,
        }

    def test_distribution_no_longer_defines_the_seed(self):
        helpers = {
            "_get_or_create_account",
            "_get_or_create_cost_center",
            "_get_or_create_cash_account",
            "_get_or_create_cash_mode_of_payment",
        }
        for name in ("seed.py", "install.py", "demo_data.py"):
            tree = ast.parse((APP / name).read_text(encoding="utf-8"))
            defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            with self.subTest(module=name):
                self.assertTrue(defined.isdisjoint(helpers))
        seed_source = (APP / "seed.py").read_text(encoding="utf-8")
        self.assertNotIn("def ensure_office_expense_defaults", seed_source)
        self.assertNotIn("OFFICE_EXPENSE_CATEGORIES", seed_source)

    def test_demo_data_uses_the_reckon_accounts_seed(self):
        source = (APP / "demo_data.py").read_text(encoding="utf-8")
        self.assertIn(
            "from reckon_accounts.office_expense_setup import ensure_office_expense_defaults", source
        )
        self.assertIn("ensure_office_expense_defaults(company)", source)

    def test_tenant_seed_creates_office_expense_defaults(self):
        with patch.dict(sys.modules, self.modules):
            seed = _load(APP / "seed.py", "reckon_distribution.seed")
            result = seed.run_distribution_seed("Acme", "v1")

        self.setup.ensure_office_expense_defaults.assert_called_once_with("Acme")
        self.assertIn("Office Expense Settings", result["created"])

    def test_migrate_backfills_every_tenant_with_the_reckon_accounts_seed(self):
        self.frappe.get_all.side_effect = lambda doctype, **kwargs: {
            "Distribution Settings": ["Beta", "Acme"],
            "Tenant User Assignment": ["Acme", None, "Gamma"],
        }[doctype]
        with patch.dict(sys.modules, self.modules):
            constants = _load(APP / "constants.py", "reckon_distribution.constants")
            with patch.dict(sys.modules, {"reckon_distribution.constants": constants}):
                install = _load(APP / "install.py", "reckon_distribution.install")
            install.ensure_office_expense_defaults()

        self.assertEqual(
            [call.args[0] for call in self.setup.ensure_office_expense_defaults.call_args_list],
            ["Acme", "Beta", "Gamma"],
        )


class OfficeExpensePermissionTests(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda text: text
        self.perms = {}
        self.inserted = []
        frappe.db = SimpleNamespace(
            exists=Mock(side_effect=self._exists), sql=Mock(), get_value=Mock()
        )
        frappe.get_doc = Mock(side_effect=self._get_doc)
        frappe.clear_cache = Mock()
        permissions = ModuleType("frappe.permissions")
        permissions.setup_custom_perms = Mock()
        frappe.permissions = permissions
        self.frappe = frappe

        with patch.dict(sys.modules, {"frappe": frappe, "frappe.permissions": permissions}):
            constants = _load(APP / "constants.py", "reckon_distribution.constants")
            with patch.dict(sys.modules, {"reckon_distribution.constants": constants}):
                self.install = _load(APP / "install.py", "reckon_distribution.install")

    def _exists(self, doctype, filters=None):
        if doctype in {"DocType", "Role"}:
            return True
        if doctype == "Custom DocPerm":
            return (filters["parent"], filters["role"]) if (filters["parent"], filters["role"]) in self.perms else None
        raise AssertionError(doctype)

    def _get_doc(self, doctype, name=None):
        if isinstance(doctype, dict):
            key = (doctype["parent"], doctype["role"])
        else:
            key = name
        perm = self.perms.setdefault(key, SimpleNamespace(values={}))
        perm.insert = Mock(side_effect=lambda **kwargs: self.inserted.append(key))
        perm.db_set = Mock(side_effect=lambda field, value: perm.values.__setitem__(field, value))
        return perm

    def test_permissions_run_with_the_other_distribution_permissions(self):
        source = (APP / "install.py").read_text(encoding="utf-8")
        body = source.split("def ensure_distribution_permissions()", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("ensure_office_expense_permissions()", body)

    def test_admins_and_managers_keep_their_previous_rights(self):
        self.install.ensure_office_expense_permissions()

        self.install.permissions.setup_custom_perms.assert_any_call("Office Expense")
        self.install.permissions.setup_custom_perms.assert_any_call("Office Expense Settings")
        rights = {
            key: {field for field, value in perm.values.items() if value}
            for key, perm in self.perms.items()
        }
        full = {"read", "write", "create", "delete", "submit", "cancel", "amend", "print", "email", "report", "export"}
        self.assertEqual(rights[("Office Expense", "Reckon Distribution Admin")], full)
        self.assertEqual(rights[("Office Expense", "Company Admin")], full)
        self.assertEqual(rights[("Office Expense", "Reckon Distribution Manager")], full - {"delete"})
        self.assertEqual(rights[("Office Expense", "Company Manager")], full - {"delete"})
        self.assertEqual(
            rights[("Office Expense Settings", "Reckon Distribution Admin")],
            {"read", "write", "create", "delete", "print"},
        )
        self.assertEqual(rights[("Office Expense Settings", "Reckon Distribution Manager")], {"read"})
        self.assertNotIn(("Office Expense", "Reckon Distribution User"), rights)
        self.assertEqual(len(self.inserted), 8)

    def test_rerun_updates_existing_rows_instead_of_inserting(self):
        self.install.ensure_office_expense_permissions()
        self.inserted.clear()
        self.install.ensure_office_expense_permissions()

        self.assertEqual(self.inserted, [])


if __name__ == "__main__":
    unittest.main()
