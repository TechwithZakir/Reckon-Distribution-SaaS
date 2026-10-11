from reckon_distribution.accounting_reports import distribution_purchase_register


def execute(filters=None):
    return distribution_purchase_register(filters)
