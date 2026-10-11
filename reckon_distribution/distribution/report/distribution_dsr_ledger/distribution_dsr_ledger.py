from reckon_distribution.accounting_reports import dsr_ledger


def execute(filters=None):
    return dsr_ledger(filters)
