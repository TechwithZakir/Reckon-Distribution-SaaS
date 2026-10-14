#!/usr/bin/env python3
"""Recover a Frappe bench whose registered app names no longer import.

This utility intentionally uses only the Python standard library.  It can run
when Bench cannot boot because `sites/apps.txt` or Frappe's installed-app
registry contains a repository title, renamed package, or deleted app.

Run from the bench directory, first without --apply to inspect the result:

    python apps/reckon_distribution/scripts/repair_frappe_app_registry.py \
        --site distribution.reckon.tech

Then run again with --apply to write timestamped backups and repair the
registry.  It is designed for MariaDB-backed Frappe sites.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _app_name_from_hooks(hooks_file: Path) -> str | None:
    """Return the literal app_name defined by a Frappe app's hooks module."""
    try:
        module = ast.parse(hooks_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for node in module.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if not any(isinstance(target, ast.Name) and target.id == "app_name" for target in targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


APP_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_DISTRIBUTION_SITE_APPS = ["frappe", "erpnext", "reckon_saas_platform", "reckon_distribution"]


def discover_app_names(apps_directory: Path) -> list[str]:
    """Build a candidate registry from the app names declared in hooks.py."""
    app_names = {
        app_name
        for hooks_file in apps_directory.glob("*/*/hooks.py")
        if (app_name := _app_name_from_hooks(hooks_file))
    }

    invalid = sorted(app_name for app_name in app_names if not APP_NAME_PATTERN.fullmatch(app_name))
    if invalid:
        raise RuntimeError("Invalid app_name value(s) in hooks.py: " + ", ".join(invalid))

    return ["frappe", "erpnext", *sorted(app_names - {"frappe", "erpnext"})]


def importable_app_names(app_names: list[str], bench_python: Path) -> list[str]:
    """Keep only applications the Bench interpreter can actually import."""
    if not bench_python.is_file():
        raise RuntimeError(f"Bench Python executable was not found: {bench_python}")

    importable = []
    unavailable = []
    for app_name in app_names:
        result = subprocess.run(
            [str(bench_python), "-c", f"import importlib; importlib.import_module({app_name!r})"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            unavailable.append(app_name)
        else:
            importable.append(app_name)

    if unavailable:
        print("Ignoring non-importable app folder(s): " + ", ".join(unavailable))

    required = {"frappe", "erpnext", "reckon_saas_platform", "reckon_distribution", "naidapa_theme"}
    missing = sorted(required - set(importable))
    if missing:
        raise RuntimeError(
            "Required app package(s) cannot be imported by Bench Python: " + ", ".join(missing)
        )

    return importable


def bench_python_executable(bench_directory: Path) -> Path:
    """Return the virtual-environment interpreter used by Bench on Linux or Windows."""
    candidates = (bench_directory / "env" / "bin" / "python", bench_directory / "env" / "Scripts" / "python.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Bench Python executable was not found under env/.")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read JSON configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Configuration {path} must be a JSON object.")
    return value


def _backup(path: Path, backup_directory: Path) -> None:
    if path.exists():
        shutil.copy2(path, backup_directory / path.name)


def _database_registry_command(config: dict[str, Any], installed_apps: list[str]) -> list[str]:
    db_type = config.get("db_type", "mariadb")
    if db_type not in {"mariadb", "mysql"}:
        raise RuntimeError(f"This recovery utility supports MariaDB/MySQL only, not {db_type!r}.")

    client = shutil.which("mariadb") or shutil.which("mysql")
    if not client:
        raise RuntimeError("Neither mariadb nor mysql client is available on PATH.")

    db_name = config.get("db_name")
    if not isinstance(db_name, str) or not db_name:
        raise RuntimeError("site_config.json does not contain a database name.")

    registry = json.dumps(installed_apps, separators=(",", ":"))
    escaped_registry = registry.replace("\\", "\\\\").replace("'", "\\'")
    sql = (
        "UPDATE `tabDefaultValue` "
        f"SET defvalue = '{escaped_registry}' "
        "WHERE parent = '__global' AND defkey = 'installed_apps'; "
        "SELECT defvalue FROM `tabDefaultValue` "
        "WHERE parent = '__global' AND defkey = 'installed_apps';"
    )

    command = [client, f"--user={config.get('db_user', 'root')}"]
    if config.get("db_password"):
        command.append(f"--password={config['db_password']}")
    if config.get("db_host"):
        command.append(f"--host={config['db_host']}")
    if config.get("db_port"):
        command.append(f"--port={config['db_port']}")
    command.extend([db_name, "--execute", sql])
    return command


def repair_registry(
    bench_directory: Path,
    site: str,
    apply: bool,
    skip_database: bool,
    site_apps: list[str],
) -> list[str]:
    apps_directory = bench_directory / "apps"
    sites_directory = bench_directory / "sites"
    apps_file = sites_directory / "apps.txt"
    site_config_file = sites_directory / site / "site_config.json"

    if not apps_directory.is_dir():
        raise RuntimeError(f"Apps directory was not found: {apps_directory}")
    if not site_config_file.is_file():
        raise RuntimeError(f"Site configuration was not found: {site_config_file}")

    app_names = importable_app_names(
        discover_app_names(apps_directory), bench_python_executable(bench_directory)
    )
    unavailable_site_apps = sorted(set(site_apps) - set(app_names))
    if unavailable_site_apps:
        raise RuntimeError(
            "Site app package(s) cannot be imported by Bench Python: " + ", ".join(unavailable_site_apps)
        )

    config = _read_json(site_config_file)
    updated_config = dict(config)
    if "installed_apps" in updated_config:
        updated_config["installed_apps"] = site_apps

    print("Canonical app registry:")
    print("\n".join(f"  - {app_name}" for app_name in app_names))
    print("\nSite-installed app registry:")
    print("\n".join(f"  - {app_name}" for app_name in site_apps))
    print(f"\nBench registry: {apps_file}")
    print(f"Site configuration: {site_config_file}")
    print("Database installed-app registry: " + ("skipped" if skip_database else "will be repaired"))

    if not apply:
        print("\nDry run only. Re-run with --apply after reviewing this list.")
        return app_names

    backup_directory = sites_directory / ".app-registry-backups" / datetime.now().strftime("%Y%m%d%H%M%S")
    backup_directory.mkdir(parents=True, exist_ok=False)
    _backup(apps_file, backup_directory)
    _backup(site_config_file, backup_directory)
    (backup_directory / "registry.json").write_text(
        json.dumps({"app_names": app_names, "site": site, "site_apps": site_apps}, indent=2) + "\n",
        encoding="utf-8",
    )

    apps_file.write_text("\n".join(app_names) + "\n", encoding="utf-8")
    site_config_file.write_text(json.dumps(updated_config, indent=2) + "\n", encoding="utf-8")

    if not skip_database:
        result = subprocess.run(
            _database_registry_command(config, site_apps), text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise RuntimeError(
                "The file registry was repaired but the database registry update failed. "
                f"Restore from {backup_directory} if needed.\n{result.stderr.strip() or result.stdout.strip()}"
            )
        if not result.stdout.strip():
            raise RuntimeError(
                "The database registry row was not found after the update. "
                f"Restore from {backup_directory} and investigate tabDefaultValue."
            )

    print(f"\nRegistry repaired. Backups: {backup_directory}")
    return app_names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, help="Frappe site name, for example distribution.reckon.tech")
    parser.add_argument("--bench", type=Path, default=Path.cwd(), help="Bench directory; defaults to current directory")
    parser.add_argument("--apply", action="store_true", help="Write the repaired registry and timestamped backups")
    parser.add_argument("--skip-database", action="store_true", help="Repair only files, not Frappe's database registry")
    parser.add_argument(
        "--site-app",
        action="append",
        dest="site_apps",
        help="Importable app installed on this site; repeat for additional installed apps",
    )
    args = parser.parse_args()

    # These are the confirmed application dependencies of the Distribution site.
    site_apps = args.site_apps or DEFAULT_DISTRIBUTION_SITE_APPS

    try:
        repair_registry(args.bench.resolve(), args.site, args.apply, args.skip_database, site_apps)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
