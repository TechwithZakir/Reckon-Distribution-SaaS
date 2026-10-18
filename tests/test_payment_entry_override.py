"""Payment Entry controller composition with Reckon Accounts (runs without a database).

Frappe keeps only the last installed app's ``override_doctype_class`` for a doctype,
so Distribution's controller must carry Reckon Accounts' direct voucher behaviour
too (and vice versa) for both to apply whichever hook wins.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).parents[1] / "reckon_distribution"
ACCOUNTS_MODULE = "reckon_accounts.overrides.direct_voucher"


class ValidationError(Exception):
    pass


class ERPNextPaymentEntry:
    """The few ERPNext controller methods the mixins call through ``super()``."""

    def __init__(self, **values):
        self.calls = []
        self.flags = {}
        self.meta = SimpleNamespace(has_field=lambda fieldname: True)
        self.__dict__.update(values)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def set_missing_values(self):
        self.calls.append("erpnext")


class FakeDirectVoucherPaymentMixin:
    """Stands in for ``reckon_accounts.overrides.direct_voucher``."""

    def is_direct_voucher(self):
        return self.get("custom_voucher_subtype") in {"Direct Expense", "Direct Income"}

    def set_missing_values(self):
        if not self.is_direct_voucher():
            return super().set_missing_values()
        self.calls.append("direct")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _package(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    return module


class PaymentEntryOverrideTests(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda text: text
        frappe.throw = Mock(side_effect=ValidationError)
        frappe.db = SimpleNamespace(
            get_value=Mock(return_value=SimpleNamespace(company="Co", payment_entry=None))
        )
        utils = ModuleType("frappe.utils")
        utils.flt = lambda value, precision=None: float(value or 0)
        frappe.utils = utils
        self.frappe = frappe

        payment_entry = ModuleType("erpnext.accounts.doctype.payment_entry.payment_entry")
        payment_entry.PaymentEntry = ERPNextPaymentEntry
        payment_entry.get_account_details = Mock(
            return_value=SimpleNamespace(
                account_currency="BDT", account_type="Cash", account_balance=500
            )
        )
        self.get_account_details = payment_entry.get_account_details

        self.modules = {
            "frappe": frappe,
            "frappe.utils": utils,
            "erpnext": _package("erpnext"),
            "erpnext.accounts": _package("erpnext.accounts"),
            "erpnext.accounts.doctype": _package("erpnext.accounts.doctype"),
            "erpnext.accounts.doctype.payment_entry": _package(
                "erpnext.accounts.doctype.payment_entry"
            ),
            "erpnext.accounts.doctype.payment_entry.payment_entry": payment_entry,
            "reckon_distribution": _package("reckon_distribution"),
            "reckon_distribution.overrides": _package("reckon_distribution.overrides"),
        }

    def _controller(self, accounts_modules):
        modules = {**self.modules, **accounts_modules}
        with patch.dict(sys.modules, modules):
            mixin = _load(
                APP / "overrides" / "office_expense_payment.py",
                "reckon_distribution.overrides.office_expense_payment",
            )
            module = _load(
                APP / "overrides" / "payment_entry.py", "reckon_distribution.overrides.payment_entry"
            )
        return mixin.OfficeExpensePaymentMixin, module.DistributionPaymentEntry

    def _with_accounts(self):
        direct_voucher = ModuleType(ACCOUNTS_MODULE)
        direct_voucher.DirectVoucherPaymentMixin = FakeDirectVoucherPaymentMixin
        return self._controller(
            {
                "reckon_accounts": _package("reckon_accounts"),
                "reckon_accounts.overrides": _package("reckon_accounts.overrides"),
                ACCOUNTS_MODULE: direct_voucher,
            }
        )

    def _without_accounts(self):
        # ``None`` in sys.modules makes ``import reckon_accounts`` fail as if absent.
        return self._controller({"reckon_accounts": None})

    def _office_expense_entry(self, controller, **values):
        defaults = {
            "name": "ACC-PAY-0001",
            "company": "Co",
            "payment_type": "Pay",
            "rd_office_expense": "OE-0001",
            "party": None,
            "party_type": None,
            "paid_from": "Cash - Co",
            "paid_to": "Cash - Co",
            "paid_amount": 100,
            "deductions": [SimpleNamespace(amount=60), SimpleNamespace(amount=40)],
            "posting_date": "2026-10-18",
            "cost_center": "Main - Co",
            "party_account": "Creditors - Co",
            "references": ["stale"],
            "flags": {"reckon_office_expense_payment": True},
        }
        return controller(**{**defaults, **values})

    def test_hook_still_points_at_distribution_controller(self):
        hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn(
            '"Payment Entry": "reckon_distribution.overrides.payment_entry.DistributionPaymentEntry"',
            hooks,
        )

    def test_without_reckon_accounts_only_office_expense_is_added(self):
        office, controller = self._without_accounts()

        self.assertEqual(controller.__mro__[1:], (office, ERPNextPaymentEntry, object))
        entry = controller(payment_type="Pay", custom_voucher_subtype="Direct Expense")
        entry.set_missing_values()
        self.assertEqual(entry.calls, ["erpnext"])

    def test_with_reckon_accounts_both_mixins_are_composed(self):
        office, controller = self._with_accounts()

        self.assertEqual(
            controller.__mro__[1:],
            (office, FakeDirectVoucherPaymentMixin, ERPNextPaymentEntry, object),
        )

    def test_direct_voucher_reaches_reckon_accounts_behaviour(self):
        _, controller = self._with_accounts()

        entry = controller(payment_type="Pay", custom_voucher_subtype="Direct Expense")
        entry.set_missing_values()

        self.assertEqual(entry.calls, ["direct"])
        self.frappe.db.get_value.assert_not_called()

    def test_ordinary_payment_falls_through_to_erpnext(self):
        _, controller = self._with_accounts()

        entry = controller(payment_type="Receive", custom_voucher_subtype="Party Settlement")
        entry.set_missing_values()

        self.assertEqual(entry.calls, ["erpnext"])

    def test_office_expense_payment_is_balanced_without_party(self):
        _, controller = self._with_accounts()

        entry = self._office_expense_entry(controller, custom_voucher_subtype="Party Settlement")
        entry.set_missing_values()

        self.assertEqual(entry.calls, [])
        self.frappe.db.get_value.assert_called_once_with(
            "Office Expense", "OE-0001", ["company", "payment_entry"], as_dict=True
        )
        self.get_account_details.assert_called_once_with("Cash - Co", "2026-10-18", "Main - Co")
        self.assertEqual(entry.paid_from_account_currency, "BDT")
        self.assertEqual(entry.paid_to_account_type, "Cash")
        self.assertEqual(entry.paid_to_account_balance, 500)
        self.assertIsNone(entry.party_account)
        self.assertEqual(entry.party_account_currency, "BDT")
        self.assertEqual(entry.references, [])

    def test_office_expense_payment_works_without_reckon_accounts(self):
        _, controller = self._without_accounts()

        entry = self._office_expense_entry(controller)
        entry.set_missing_values()

        self.assertEqual(entry.calls, [])
        self.assertIsNone(entry.party_account)

    def test_office_expense_cannot_also_be_a_direct_voucher(self):
        _, controller = self._with_accounts()

        entry = self._office_expense_entry(controller, custom_voucher_subtype="Direct Expense")
        with self.assertRaises(ValidationError):
            entry.set_missing_values()

        self.assertIn("direct", self.frappe.throw.call_args.args[0])
        self.assertEqual(entry.calls, [])

    def test_unbalanced_office_expense_is_rejected(self):
        _, controller = self._with_accounts()

        entry = self._office_expense_entry(controller, paid_amount=90)
        with self.assertRaises(ValidationError):
            entry.set_missing_values()

        self.assertIn("equal the paid amount", self.frappe.throw.call_args.args[0])

    def test_unlinked_office_expense_falls_through(self):
        _, controller = self._with_accounts()

        entry = self._office_expense_entry(controller, flags={})
        entry.set_missing_values()

        self.assertEqual(entry.calls, ["erpnext"])

    def test_old_reckon_accounts_without_mixin_module_is_skipped(self):
        office, controller = self._controller(
            {
                "reckon_accounts": _package("reckon_accounts"),
                "reckon_accounts.overrides": _package("reckon_accounts.overrides"),
            }
        )

        self.assertEqual(controller.__mro__[1:], (office, ERPNextPaymentEntry, object))

    def test_broken_reckon_accounts_import_is_not_swallowed(self):
        error = ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")
        with patch("importlib.import_module", side_effect=error):
            with self.assertRaises(ModuleNotFoundError):
                self._controller({})


if __name__ == "__main__":
    unittest.main()
