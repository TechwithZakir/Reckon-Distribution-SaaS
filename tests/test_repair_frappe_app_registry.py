"""Tests for the standalone Bench registry recovery tool."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_import_verification_refuses_to_repair_without_required_packages(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(
            REPAIR.subprocess, "run", return_value=Mock(returncode=0)
        ):
            with self.assertRaisesRegex(RuntimeError, "reckon_distribution"):
                REPAIR.importable_app_names(["frappe"], Path("/bench/env/bin/python"))

    def test_non_importable_stale_theme_is_excluded_from_registry(self):
        candidates = [
            "frappe",
            "erpnext",
            "easyai_theme",
            "naidapa_theme",
            "reckon_distribution",
            "reckon_saas_platform",
        ]
        result = Mock()
        result.returncode = 1

        def subprocess_result(command, **_kwargs):
            if command[-1].endswith("'easyai_theme')"):
                return result
            return Mock(returncode=0)

        with patch.object(Path, "is_file", return_value=True), patch.object(
            REPAIR.subprocess, "run", side_effect=subprocess_result
        ):
            self.assertEqual(
                REPAIR.importable_app_names(candidates, Path("/bench/env/bin/python")),
                ["frappe", "erpnext", "naidapa_theme", "reckon_distribution", "reckon_saas_platform"],
            )

    def test_distribution_site_registry_does_not_install_a_bench_theme_implicitly(self):
        self.assertEqual(
            REPAIR.DEFAULT_DISTRIBUTION_SITE_APPS,
            ["frappe", "erpnext", "reckon_saas_platform", "reckon_distribution"],
        )


if __name__ == "__main__":
    unittest.main()
