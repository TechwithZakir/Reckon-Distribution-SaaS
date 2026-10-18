"""Test helper: set SaaS Platform Settings for one test and restore them afterwards."""

from __future__ import annotations

import frappe
from frappe.utils.password import remove_encrypted_password

SETTINGS_DOCTYPE = "SaaS Platform Settings"
PASSWORD_FIELDS = ("bulksmsbd_api_key", "recaptcha_secret_key")
SIGNUP_VERIFICATION_OFF = {
    "require_phone_verification": 0,
    "require_captcha": 0,
    "bulksmsbd_api_key": "",
    "bulksmsbd_sender_id": "",
    "recaptcha_site_key": "",
    "recaptcha_secret_key": "",
}


def use_signup_settings(test_case, **values) -> None:
    """Apply ``values`` (defaults: phone and captcha verification off) until test cleanup."""
    values = {**SIGNUP_VERIFICATION_OFF, **values}
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    previous = {}
    for field in values:
        if field in PASSWORD_FIELDS:
            previous[field] = settings.get_password(field, raise_exception=False) or ""
        else:
            previous[field] = settings.get(field)
    _save(values)
    test_case.addCleanup(_save, previous)


def _save(values: dict) -> None:
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    cleared = []
    for field, value in values.items():
        if field in PASSWORD_FIELDS and not value:
            # An empty Password value keeps the stored secret; delete it instead.
            cleared.append(field)
            value = ""
        settings.set(field, value)
    settings.save(ignore_permissions=True)
    for field in cleared:
        remove_encrypted_password(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, field)
    frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
