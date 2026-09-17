from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PerformanceStructureTests(unittest.TestCase):
    def test_write_and_summary_instructions_forbid_reanalysis(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("json_write", skill)
        self.assertIn("deterministic serialization only", skill)
        self.assertIn("do not reopen sources or repeat semantic analysis", skill)

    def test_renderer_has_no_source_reader_or_semantic_audit(self) -> None:
        renderer = (ROOT / "scripts/render_report.py").read_text(encoding="utf-8")

        self.assertNotIn("resolve_scope", renderer)
        self.assertNotIn("audit_cross_rf", renderer)
        self.assertNotIn("audit_source_claims", renderer)


if __name__ == "__main__":
    unittest.main()
