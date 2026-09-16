from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("resolve_scope", ROOT / "scripts" / "resolve_scope.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load scope resolver")
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)


class ScopeResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / "docs").mkdir()
        (self.workspace / "docs" / "requirements.md").write_text("Selected requirement", encoding="utf-8")
        (self.workspace / "docs" / "nested").mkdir()
        (self.workspace / "docs" / "nested" / "adr.md").write_text("Selected ADR", encoding="utf-8")
        (self.workspace / "sibling").mkdir()
        (self.workspace / "sibling" / "private.md").write_text("Outside", encoding="utf-8")
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "service.py").write_text("import hidden_module\n", encoding="utf-8")
        (self.workspace / "hidden_module.py").write_text("SECRET = True\n", encoding="utf-8")
        (self.workspace / "node_modules").mkdir()
        (self.workspace / "node_modules" / "noise.js").write_text("noise", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_selected_file_resolves_only_itself(self) -> None:
        result = SCOPE.resolve_selected_scope(self.workspace, ["docs/requirements.md"])
        self.assertEqual(["docs/requirements.md"], result["resolved_scope_paths"])

    def test_selected_directory_is_recursive_without_siblings_or_noise(self) -> None:
        result = SCOPE.resolve_selected_scope(self.workspace, ["docs"])
        self.assertEqual(
            ["docs/nested/adr.md", "docs/requirements.md"],
            result["resolved_scope_paths"],
        )
        self.assertNotIn("sibling/private.md", result["resolved_scope_paths"])
        self.assertNotIn("node_modules/noise.js", result["resolved_scope_paths"])

    def test_import_is_not_followed(self) -> None:
        result = SCOPE.resolve_selected_scope(self.workspace, ["src/service.py"])
        self.assertEqual(["src/service.py"], result["resolved_scope_paths"])
        self.assertNotIn("hidden_module.py", result["resolved_scope_paths"])

    def test_selected_code_is_in_scope(self) -> None:
        result = SCOPE.resolve_selected_scope(self.workspace, ["src"])
        self.assertEqual(["src/service.py"], result["resolved_scope_paths"])

    def test_ambiguous_basename_requires_disambiguation(self) -> None:
        (self.workspace / "sibling" / "requirements.md").write_text("Other", encoding="utf-8")
        with self.assertRaisesRegex(SCOPE.ScopeResolutionError, "ambiguous source name"):
            SCOPE.resolve_selected_scope(self.workspace, ["requirements.md"])

    def test_parent_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(SCOPE.ScopeResolutionError, "escapes the allowed boundary"):
            SCOPE.resolve_selected_scope(self.workspace, ["../outside.md"])


if __name__ == "__main__":
    unittest.main()
