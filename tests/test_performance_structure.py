from __future__ import annotations

import unittest
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_scope import resolve_selected_scope  # noqa: E402


class PerformanceStructureTests(unittest.TestCase):
    def test_write_and_summary_instructions_forbid_reanalysis(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        performance = (ROOT / "references" / "performance-orchestration.md").read_text(encoding="utf-8")

        self.assertIn("performance-orchestration.md", skill)
        self.assertIn("Serialization/rendering must not hide semantic work", performance)

    def test_renderer_has_no_source_reader_or_semantic_audit(self) -> None:
        renderer = (ROOT / "scripts/render_report.py").read_text(encoding="utf-8")

        self.assertNotIn("resolve_scope", renderer)
        self.assertNotIn("audit_cross_rf", renderer)
        self.assertNotIn("audit_source_claims", renderer)

    def test_large_tree_inventory_is_metadata_first_and_binary_selective(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected = root / "selected"
            selected.mkdir()
            for number in range(80):
                suffix = ".md" if number < 20 else ".png"
                (selected / f"item-{number:03d}{suffix}").write_bytes(b"metadata fixture")
            ignored = selected / "node_modules"
            ignored.mkdir()
            (ignored / "unread.js").write_text("secret", encoding="utf-8")

            plan = resolve_selected_scope(root, ["selected"])

            self.assertEqual(80, len(plan["resolved_scope_paths"]))
            self.assertEqual(20, len(plan["recommended_source_reads"]))
            self.assertEqual(60, len(plan["metadata_only_paths"]))
            self.assertNotIn("selected/node_modules/unread.js", plan["resolved_scope_paths"])


if __name__ == "__main__":
    unittest.main()
