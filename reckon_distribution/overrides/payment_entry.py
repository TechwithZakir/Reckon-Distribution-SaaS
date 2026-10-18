"""Payment Entry controller registered through ``override_doctype_class``.

Frappe keeps one controller class per doctype: the hook of the last installed app
wins. Reckon Accounts also overrides Payment Entry, so this class includes its
direct income/expense voucher mixin whenever that app is on the bench. Its controller
does the same with ``OfficeExpensePaymentMixin``, so both behaviours apply whichever
hook wins. Each mixin is inert unless its own fields are set on the document.
"""

from __future__ import annotations

import importlib

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

from reckon_distribution.overrides.office_expense_payment import OfficeExpensePaymentMixin


def _optional_mixin(module_path: str, name: str):
    """Return ``name`` from ``module_path``, or None when that module is not installed."""
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only a missing app (or an older version without this module) is optional;
        # a broken import inside an installed module must still fail loudly.
        if exc.name and (module_path == exc.name or module_path.startswith(f"{exc.name}.")):
            return None
        raise
    return getattr(module, name)


# Same base order as Reckon Accounts' controller, so the MRO does not depend on
# which app's hook Frappe picks.
_MIXINS = tuple(
    mixin
    for mixin in (
        OfficeExpensePaymentMixin,
        _optional_mixin("reckon_accounts.overrides.direct_voucher", "DirectVoucherPaymentMixin"),
    )
    if mixin
)


class DistributionPaymentEntry(*_MIXINS, PaymentEntry):
    """ERPNext Payment Entry with Office Expense and, when present, direct vouchers."""
