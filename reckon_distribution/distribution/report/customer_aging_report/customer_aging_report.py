from reckon_distribution.accounting_reports import receivable_payable_aging


def execute(filters=None):
    return receivable_payable_aging(filters, "Receivable")
