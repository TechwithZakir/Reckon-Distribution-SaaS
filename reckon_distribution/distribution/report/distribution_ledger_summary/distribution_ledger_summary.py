from reckon_distribution.accounting_reports import ledger_summary


def execute(filters=None):
    return ledger_summary(filters)
