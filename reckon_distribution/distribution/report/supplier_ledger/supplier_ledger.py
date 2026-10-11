from reckon_distribution.accounting_reports import supplier_ledger


def execute(filters=None):
    return supplier_ledger(filters)
