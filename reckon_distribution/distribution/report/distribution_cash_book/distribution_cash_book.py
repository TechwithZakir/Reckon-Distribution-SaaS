from reckon_distribution.accounting_reports import cash_book


def execute(filters=None):
    return cash_book(filters)
