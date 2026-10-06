from __future__ import annotations


def get_module_definition() -> dict:
    return {
        "key": "distribution",
        "label": "Distribution SaaS",
        "workspace": "distribution",
        "roles": [
            "Reckon Distribution Admin",
            "Reckon Distribution Manager",
            "Reckon Distribution User",
            "Reckon Master Data Manager",
        ],
        "seed_handler": "reckon_distribution.seed.run_distribution_seed",
        "subscription_features": [
            "dsr_routes",
            "retailer_receivable",
            "dsr_cash_custody",
            "supplier_provided_goods",
            "bangla_pwa",
        ],
    }
