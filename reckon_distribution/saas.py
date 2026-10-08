"""Compatibility exports for the SaaS platform app."""

import frappe
from reckon_saas_platform.saas import (
    PaymentGatewayAdapter,
    SubscriptionGateError,
    assert_operational_access,
    create_registration,
    ensure_tenant_seed_job,
    get_company_subscription,
    get_subscription_summary,
    get_user_home_page,
    get_vendor_saas_summary,
    is_subscription_active,
    public_signup,
)
from reckon_saas_platform.saas import (
    run_tenant_seed_job as _run_tenant_seed_job,
)
from reckon_saas_platform.saas import (
    verify_payment as _verify_payment,
)
from reckon_saas_platform.saas_security import is_vendor_user

__all__ = [
    "PaymentGatewayAdapter",
    "SubscriptionGateError",
    "assert_operational_access",
    "create_registration",
    "ensure_tenant_seed_job",
    "get_company_subscription",
    "get_subscription_summary",
    "get_user_home_page",
    "get_vendor_saas_summary",
    "is_subscription_active",
    "public_signup",
    "retry_tenant_seed_job",
    "run_tenant_seed_job",
    "verify_payment",
    "verify_payment_manual",
]

run_tenant_seed_job = _run_tenant_seed_job
verify_payment = _verify_payment


def verify_payment_manual(payment: str, reference: str | None = None):
    if not is_vendor_user():
        frappe.throw("Only vendor administrators can perform this action.", frappe.PermissionError)
    return _verify_payment(payment, reference=reference).name


def retry_tenant_seed_job(company: str):
    if not is_vendor_user():
        frappe.throw("Only vendor administrators can perform this action.", frappe.PermissionError)
    return _run_tenant_seed_job(company).name
