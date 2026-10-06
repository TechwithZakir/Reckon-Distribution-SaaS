"""Compatibility wrapper for the SaaS platform app.

New code should import from ``reckon_saas_platform.saas``. This module remains
so existing sites, tests, and integrations using the original Distribution app
paths continue to work while the platform split is rolled out.
"""

from reckon_saas_platform.saas import *  # noqa: F403
