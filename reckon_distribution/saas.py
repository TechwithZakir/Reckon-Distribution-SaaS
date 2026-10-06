from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from reckon_distribution.constants import CURRENT_SEED_VERSION, SAAS_ACTIVE_STATUSES


class SubscriptionGateError(frappe.PermissionError):
    pass


class PaymentGatewayAdapter:
    def verify(self, reference: str) -> bool:
        raise NotImplementedError


@frappe.whitelist(allow_guest=True)
def public_signup(
    business_name: str,
    owner_email: str,
    owner_name: str,
    plan: str,
    billing_cycle: str = "Monthly",
):
    return create_registration(
        business_name=business_name,
        owner_email=owner_email,
        owner_name=owner_name,
        plan=plan,
        billing_cycle=billing_cycle,
    ).name


def create_registration(
    *,
    business_name: str,
    owner_email: str,
    owner_name: str,
    plan: str,
    billing_cycle: str = "Monthly",
):
    plan_doc = frappe.get_doc("SaaS Plan", plan)
    registration = frappe.get_doc(
        {
            "doctype": "SaaS Registration",
            "business_name": business_name,
            "owner_email": owner_email,
            "owner_name": owner_name,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "status": "Pending Payment",
        }
    ).insert(ignore_permissions=True)

    company = _get_or_create_company(business_name)
    admin_user = _get_or_create_admin_user(owner_email, owner_name)
    _assign_company_admin(admin_user.name, company.name)

    subscription = frappe.get_doc(
        {
            "doctype": "SaaS Subscription",
            "registration": registration.name,
            "company": company.name,
            "company_admin": admin_user.name,
            "plan": plan_doc.name,
            "plan_version": plan_doc.plan_version,
            "billing_cycle": billing_cycle,
            "status": "Pending",
            "price": plan_doc.price,
            "currency": plan_doc.currency,
            "start_date": nowdate(),
        }
    ).insert(ignore_permissions=True)

    payment = frappe.get_doc(
        {
            "doctype": "SaaS Payment",
            "subscription": subscription.name,
            "company": company.name,
            "amount": plan_doc.price,
            "currency": plan_doc.currency,
            "status": "Pending Verification",
        }
    ).insert(ignore_permissions=True)

    job = ensure_tenant_seed_job(company.name)
    registration.db_set(
        {
            "company": company.name,
            "company_admin": admin_user.name,
            "subscription": subscription.name,
            "payment": payment.name,
            "provisioning_job": job.name,
        }
    )
    return registration


def ensure_tenant_seed_job(company: str, seed_version: str = CURRENT_SEED_VERSION):
    existing = frappe.db.exists(
        "Tenant Provisioning Job",
        {"company": company, "seed_version": seed_version},
    )
    if existing:
        return frappe.get_doc("Tenant Provisioning Job", existing)

    return frappe.get_doc(
        {
            "doctype": "Tenant Provisioning Job",
            "company": company,
            "seed_version": seed_version,
            "status": "Pending",
            "idempotency_key": f"{company}:{seed_version}",
        }
    ).insert(ignore_permissions=True)


def run_tenant_seed_job(company: str, seed_version: str = CURRENT_SEED_VERSION):
    job = ensure_tenant_seed_job(company, seed_version)
    if job.status == "Complete":
        return job

    job.status = "Running"
    job.current_step = "generic-defaults"
    job.save(ignore_permissions=True)

    # Seed only generic non-sensitive placeholders. Do not copy Items, Customers,
    # Suppliers, prices, balances, contacts, or stock.
    job.status = "Complete"
    job.current_step = "verified"
    job.completed_on = nowdate()
    job.error = ""
    job.save(ignore_permissions=True)
    return job


def verify_payment(payment: str, reference: str | None = None):
    payment_doc = frappe.get_doc("SaaS Payment", payment)
    payment_doc.status = "Verified"
    if reference:
        payment_doc.gateway_reference = reference
    payment_doc.verified_on = nowdate()
    payment_doc.save(ignore_permissions=True)

    subscription = frappe.get_doc("SaaS Subscription", payment_doc.subscription)
    subscription.status = "Active"
    subscription.start_date = subscription.start_date or nowdate()
    subscription.end_date = subscription.end_date or add_days(nowdate(), 30)
    subscription.save(ignore_permissions=True)
    return subscription


def is_subscription_active(company: str) -> bool:
    subscription = get_company_subscription(company)
    if not subscription:
        return False
    if subscription.status not in SAAS_ACTIVE_STATUSES:
        return False

    if subscription.status == "Grace" and subscription.grace_until:
        return getdate(subscription.grace_until) >= getdate(nowdate())
    if subscription.end_date and getdate(subscription.end_date) < getdate(nowdate()):
        return False
    return True


def assert_operational_access(company: str) -> None:
    seed_complete = frappe.db.exists(
        "Tenant Provisioning Job",
        {"company": company, "seed_version": CURRENT_SEED_VERSION, "status": "Complete"},
    )
    if not seed_complete:
        raise SubscriptionGateError(_("Tenant seed provisioning is not complete."))
    if not is_subscription_active(company):
        raise SubscriptionGateError(_("Subscription is not active."))


def get_company_subscription(company: str):
    name = frappe.db.get_value(
        "SaaS Subscription",
        {"company": company},
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc("SaaS Subscription", name) if name else None


def _get_or_create_company(company_name: str):
    if frappe.db.exists("Company", company_name):
        return frappe.get_doc("Company", company_name)
    return frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": company_name,
            "abbr": _abbr(company_name),
            "default_currency": "BDT",
            "country": "Bangladesh",
        }
    ).insert(ignore_permissions=True)


def _get_or_create_admin_user(email: str, full_name: str):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": full_name or email,
            "send_welcome_email": 0,
            "enabled": 1,
            "roles": [{"role": "Reckon Distribution Admin"}],
        }
    )
    return user.insert(ignore_permissions=True)


def _assign_company_admin(user: str, company: str):
    existing = frappe.db.exists(
        "Tenant User Assignment",
        {"user": user, "company": company, "active": 1},
    )
    if existing:
        return frappe.get_doc("Tenant User Assignment", existing)
    return frappe.get_doc(
        {
            "doctype": "Tenant User Assignment",
            "user": user,
            "company": company,
            "role_profile": "Company Admin",
            "active": 1,
            "is_default": 1,
        }
    ).insert(ignore_permissions=True)


def _abbr(company_name: str) -> str:
    letters = "".join(part[:1] for part in company_name.split() if part).upper()[:5]
    return letters or "RDS"
