"""Tests for the standalone Bench registry recovery tool."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "repair_frappe_app_registry.py"
SPEC = importlib.util.spec_from_file_location("repair_frappe_app_registry", SCRIPT)
REPAIR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(REPAIR)


class AppRegistryRecoveryTests(unittest.TestCase):
    def _app(self, root: Path, directory: str, package: str, app_name: str) -> None:
        package_directory = root / directory / package
        package_directory.mkdir(parents=True)
        (package_directory / "hooks.py").write_text(f'app_name = "{app_name}"\n', encoding="utf-8")

    def test_discovery_uses_python_app_names_not_repository_directory_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            apps = Path(temporary) / "apps"
            self._app(apps, "frappe", "frappe", "frappe")
            self._app(apps, "erpnext", "erpnext", "erpnext")
            self._app(apps, "Reckon-Distribution-SaaS", "reckon_distribution", "reckon_distribution")
            self._app(apps, "Reckon-SaaS-Platform", "reckon_saas_platform", "reckon_saas_platform")
            self._app(apps, "naidapa_theme", "naidapa_theme", "naidapa_theme")

            self.assertEqual(
                REPAIR.discover_app_names(apps),
                ["frappe", "erpnext", "naidapa_theme", "reckon_distribution", "reckon_saas_platform"],
            )

    def test_discovery_refuses_to_repair_a_bench_missing_required_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            apps = Path(temporary) / "apps"
            self._app(apps, "frappe", "frappe", "frappe")

            with self.assertRaisesRegex(RuntimeError, "reckon_distribution"):
                REPAIR.discover_app_names(apps)


if __name__ == "__main__":
    unittest.main()
