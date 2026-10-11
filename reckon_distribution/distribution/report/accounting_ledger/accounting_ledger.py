from reckon_distribution.accounting_reports import accounting_ledger


def execute(filters=None):
    return accounting_ledger(filters)
