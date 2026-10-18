"""The v16 left rail is shipped as a file, so ``bench migrate`` stops deleting it as an orphan.

Frappe v16's ``remove_orphan_entities`` deletes every standard Workspace Sidebar whose ``app`` has
no ``<app>/workspace_sidebar/<frappe.scrub(name)>.json``. These tests pin that path and keep the
after_migrate code reading the same file (runs without a database).
"""

import importlib
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "reckon_distribution"


def scrub(text):
    return text.replace(" ", "_").replace("-", "_").lower()


def rows(items):
    keys = ("type", "label", "link_type", "link_to", "icon", "child")
    return [tuple(item.get(key) for key in keys) for item in items]


class V16OrphanNavigationTests(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda text: text
        frappe.permissions = Mock()
        frappe.db = Mock()
        frappe.db.exists = Mock(return_value=True)
        frappe.get_doc = Mock()
        self.frappe = frappe
        saved = {k: v for k, v in sys.modules.items() if k.startswith("reckon_distribution")}
        for key in saved:
            del sys.modules[key]
        self.addCleanup(sys.modules.update, saved)
        modules = patch.dict(sys.modules, {"frappe": frappe})
        modules.start()
        self.addCleanup(modules.stop)
        sys.path.insert(0, str(REPO_ROOT))
        self.addCleanup(sys.path.remove, str(REPO_ROOT))
        self.install = importlib.import_module("reckon_distribution.install")
        self.constants = importlib.import_module("reckon_distribution.constants")
        self.shipped = json.loads(self.install.DISTRIBUTION_SIDEBAR_FILE.read_text(encoding="utf-8"))

    def test_file_sits_where_the_orphan_sweep_looks(self):
        # Mirrors frappe.model.sync.check_if_record_exists("app", get_app_path(app), ...).
        path = REPO_ROOT / self.shipped["app"] / "workspace_sidebar" / f"{scrub(self.shipped['name'])}.json"
        self.assertTrue(path.exists())
        self.assertEqual(self.install.DISTRIBUTION_SIDEBAR_FILE.resolve(), path.resolve())
        self.assertEqual(self.shipped["doctype"], "Workspace Sidebar")
        self.assertEqual(self.shipped["name"], self.constants.DISTRIBUTION_SIDEBAR)
        self.assertEqual(self.shipped["app"], "reckon_distribution")
        self.assertEqual(self.shipped["standard"], 1)
        self.assertIn(self.shipped["module"], (APP / "modules.txt").read_text(encoding="utf-8").splitlines())

    def test_file_has_a_fixed_timestamp_so_migrate_does_not_reimport_it(self):
        # Without `modified`, Frappe's import treats the file as newer than the database row on
        # every migrate and deletes and re-inserts it.
        self.assertRegex(self.shipped["modified"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")

    def test_module_sidebar_file_carries_the_same_rows(self):
        # Newer v16 builds read `<module>/sidebar/<name>/<name>.json` instead; keep the two in step.
        sidebar = json.loads((APP / "distribution/sidebar/distribution/distribution.json").read_text("utf-8"))
        self.assertEqual(sidebar["name"], self.shipped["name"])
        self.assertEqual(rows(sidebar["items"]), rows(self.shipped["items"]))

    def test_definition_is_the_file_minus_missing_links(self):
        self.frappe.db.exists.side_effect = lambda doctype, name: name != "Day Book"
        definition = self.install._workspace_sidebar_doc()
        expected = [item for item in self.shipped["items"] if item.get("link_to") != "Day Book"]
        self.assertEqual(definition["items"], expected)
        self.assertEqual(len(expected), len(self.shipped["items"]) - 1)
        self.assertNotIn("modified", definition)
        self.assertEqual(
            {k: v for k, v in definition.items() if k != "items"},
            {k: v for k, v in self.shipped.items() if k not in {"items", "modified"}},
        )

    def test_pages_are_never_filtered(self):
        self.frappe.db.exists.return_value = None
        items = self.install._workspace_sidebar_doc()["items"]
        self.assertIn("distribution", {item.get("link_to") for item in items})

    def test_missing_sidebar_is_inserted_from_the_file(self):
        self.frappe.db.exists.side_effect = lambda doctype, name=None: doctype != "Workspace Sidebar"
        self.install.ensure_workspace_sidebar()
        inserted = self.frappe.get_doc.call_args.args[0]
        self.assertEqual(inserted["name"], "Distribution")
        self.assertEqual(inserted["items"], self.shipped["items"])
        self.frappe.get_doc.return_value.insert.assert_called_once()

    def test_existing_sidebar_gets_the_file_rows(self):
        sidebar = Mock()
        self.frappe.get_doc.return_value = sidebar
        self.install.ensure_workspace_sidebar()
        sidebar.set.assert_called_once_with("items", self.shipped["items"])
        sidebar.save.assert_called_once()

    def test_v15_without_workspace_sidebar_is_left_alone(self):
        self.frappe.db.exists.return_value = None
        self.install.ensure_workspace_sidebar()
        self.frappe.get_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
