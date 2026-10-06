from __future__ import annotations

import frappe


def get_saas_modules() -> list[frappe._dict]:
    modules: list[frappe._dict] = []
    for module in frappe.get_hooks("reckon_saas_modules"):
        if isinstance(module, str):
            module = frappe.get_attr(module)()
        modules.append(frappe._dict(module))
    return modules


def get_default_module() -> frappe._dict | None:
    modules = get_saas_modules()
    return modules[0] if modules else None


def get_landing_workspace(module_key: str | None = None) -> str:
    modules = get_saas_modules()
    if module_key:
        for module in modules:
            if module.get("key") == module_key:
                return module.get("workspace") or "distribution"

    default = modules[0] if modules else None
    return default.get("workspace") if default else "distribution"


def get_seed_handlers() -> list[str]:
    return [module.seed_handler for module in get_saas_modules() if module.get("seed_handler")]
