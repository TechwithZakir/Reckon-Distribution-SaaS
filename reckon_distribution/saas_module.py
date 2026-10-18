from __future__ import annotations


def get_module_definition() -> dict:
    from reckon_distribution.desk_guard import (
        ALLOWED_DISTRIBUTION_DOCTYPES,
        ALLOWED_DISTRIBUTION_PAGES,
        DISTRIBUTION_QUERY_REPORTS,
    )

    return {
        "key": "distribution",
        "label": "Distribution SaaS",
        "description": "Bangla-first SR/DSR distribution for FMCG businesses: routes, "
        "deliveries, collections and stock in one place.",
        "workspace": "app/distribution",
        "home_route": "/desk/distribution",
        "admin_role": "Reckon Distribution Admin",
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
        # Desk reach for tenants that subscribe to several modules: the module
        # guards allow the union of every subscribed module's lists.
        "desk_pages": sorted(ALLOWED_DISTRIBUTION_PAGES),
        "desk_doctypes": sorted(ALLOWED_DISTRIBUTION_DOCTYPES),
        "desk_reports": sorted(DISTRIBUTION_QUERY_REPORTS),
    }
