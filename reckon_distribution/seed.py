from __future__ import annotations


def run_distribution_seed(company: str, seed_version: str) -> dict:
    """Seed additive distribution defaults for a tenant company.

    Business data such as Item, Customer, Supplier, prices, balances, contacts,
    and stock must never be cloned from another tenant.
    """
    return {
        "company": company,
        "seed_version": seed_version,
        "status": "skipped",
        "reason": "distribution operational seed data is not implemented yet",
    }
