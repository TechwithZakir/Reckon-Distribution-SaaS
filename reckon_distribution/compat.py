from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version


@dataclass(frozen=True)
class FrappeVersion:
    major: int
    raw: str

    @property
    def supports_v15(self) -> bool:
        return self.major == 15

    @property
    def supports_v16(self) -> bool:
        return self.major == 16


@lru_cache
def get_frappe_version() -> FrappeVersion:
    raw = _package_version("frappe")
    return FrappeVersion(major=_major(raw), raw=raw)


@lru_cache
def get_erpnext_version() -> FrappeVersion:
    raw = _package_version("erpnext")
    return FrappeVersion(major=_major(raw), raw=raw)


def assert_supported_versions() -> None:
    frappe_version = get_frappe_version()
    erpnext_version = get_erpnext_version()
    supported = {15, 16}

    if frappe_version.major not in supported:
        raise RuntimeError(f"Unsupported Frappe version: {frappe_version.raw}")
    if erpnext_version.major not in supported:
        raise RuntimeError(f"Unsupported ERPNext version: {erpnext_version.raw}")


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "0.0.0"


def _major(raw: str) -> int:
    try:
        return int(raw.split(".", 1)[0])
    except (TypeError, ValueError):
        return 0
