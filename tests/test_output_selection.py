from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_state import (  # noqa: E402
    OutputSelection,
    persist_canonical_suite,
    render_selected_outputs,
)


class OutputSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "source"
        shutil.copytree(ROOT / "examples" / "expected-output", source)
        self.index = json.loads((source / "test-cases.json").read_text(encoding="utf-8"))
        self.questions = json.loads((source / "questions.json").read_text(encoding="utf-8"))
        self.cases = [
            json.loads((source / entry["file"]).read_text(encoding="utf-8"))
            for entry in self.index["test_cases"]
        ]
        self.canonical = persist_canonical_suite(
            self.root / "artifacts", "run-001",
            index=self.index, questions=self.questions, cases=self.cases,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def render(self, formats: set[str], name: str) -> tuple[Path, dict]:
        artifact_root = self.root / name
        canonical = persist_canonical_suite(
            artifact_root, "run-001",
            index=self.index, questions=self.questions, cases=self.cases,
        )
        metrics = render_selected_outputs(canonical, artifact_root, OutputSelection.normalize(formats))
        return artifact_root / "output", metrics

    def test_output_selection_matrix_preserves_one_canonical_semantic_state(self) -> None:
        combinations = [
            {"HTML"}, {"JSON"}, {"MARKDOWN"}, {"HTML", "JSON"},
            {"JSON", "MARKDOWN"}, {"HTML", "MARKDOWN"},
            {"HTML", "JSON", "MARKDOWN"},
        ]
        fingerprints = set()
        for number, formats in enumerate(combinations):
            output, metrics = self.render(formats, f"case-{number}")
            self.assertEqual(("HTML" in formats), (output / "report.html").exists())
            self.assertEqual(("JSON" in formats), (output / "test-cases.json").exists())
            self.assertEqual(("MARKDOWN" in formats), (output / "test-cases-md").exists())
            self.assertEqual(0, metrics["source_reads_during_render"])
            fingerprints.add(metrics["semantic_fingerprint"])
        self.assertEqual(1, len(fingerprints))

    def test_html_only_has_no_links_to_unpublished_json_or_markdown(self) -> None:
        output, _ = self.render({"HTML"}, "html-only")
        report = (output / "report.html").read_text(encoding="utf-8")
        self.assertNotIn('href="test-cases/TC-', report)
        self.assertNotIn('href="test-cases-md/TC-', report)

    def test_json_projection_remains_schema_1_2(self) -> None:
        output, _ = self.render({"JSON"}, "json-only")
        index = json.loads((output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertEqual("1.2", index["schema_version"])


if __name__ == "__main__":
    unittest.main()
