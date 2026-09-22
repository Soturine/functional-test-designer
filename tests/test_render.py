from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LegacySuiteRenderTests(unittest.TestCase):
    """Schema 1.2 suites stay renderable; rendering never changes JSON."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def render_all(self) -> str:
        render.render_markdown(self.output)
        return render.render_report(self.output).read_text(encoding="utf-8")

    def test_offline_html_without_changing_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path: digest(path) for path in json_files}
        report = self.render_all()
        self.assertEqual(before, {path: digest(path) for path in json_files})
        self.assertIn("Submit a create-order request", report)
        self.assertIn('href="test-cases/TC-001.json"', report)
        self.assertIn('href="test-cases-md/TC-010.md"', report)
        self.assertEqual(11, report.count('class="tc-card"'))
        for forbidden in ("https://", "<script src=", "unpkg", "jsdelivr", "mermaid.min.js", 'src="http'):
            self.assertNotIn(forbidden, report)

    def test_one_markdown_per_case_contains_every_step(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        rendered = render.render_markdown(self.output)
        self.assertEqual(len(index["test_cases"]), len(rendered))
        for entry in index["test_cases"]:
            case = json.loads((self.output / entry["file"]).read_text(encoding="utf-8"))
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            for step in case["steps"]:
                self.assertIn(step["action"], markdown)

    def test_mermaid_is_last_linear_and_identical_in_html(self) -> None:
        report = self.render_all()
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        for entry in index["test_cases"]:
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            mermaid = render.extract_mermaid(markdown)
            self.assertTrue(markdown.rstrip().endswith("```"))
            self.assertNotIn("-->|", mermaid)
            self.assertIn(render.esc(mermaid), report)
        self.assertEqual(len(index["test_cases"]), report.count('class="mermaid-svg"'))

    def test_missing_expected_result_is_marked_without_invention(self) -> None:
        case = json.loads((self.output / "test-cases/TC-010.json").read_text(encoding="utf-8"))
        case["steps"][0]["expected_result"] = None
        case["steps"][0]["needs_clarification"] = True
        labels = render.LABELS["en"]
        source = render.mermaid_source(case, labels)
        self.assertIn(labels["needs_answer"], source)
        self.assertIn("class C1 clarification", source)

    def test_mermaid_labels_wrap_and_sanitize(self) -> None:
        label = "Confirm the synthetic reservation and then inspect the resulting availability for the selected item"
        wrapped = render._mermaid_label(label, width=50)
        self.assertIn("<br/>", wrapped)
        self.assertEqual(label, wrapped.replace("<br/>", " "))
        sanitized = render._mermaid_label('<script>"bad" [node] {shape} | value & more')
        for token in ("<script>", '"', "[", "]", "{", "}", "|"):
            self.assertNotIn(token, sanitized)

    def test_source_content_is_escaped(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        case = json.loads((self.output / "test-cases/TC-001.json").read_text(encoding="utf-8"))
        case["steps"][0]["action"] = '<script>alert("x")</script>'
        labels = render.labels_for(index)
        html = render.render_case_html(
            case, index["test_cases"][0], render.mermaid_source(case, labels), labels,
            {item["id"]: item for item in index["requirements"]}, "G", "Group", set(), {"JSON"},
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_refuses_missing_or_divergent_markdown(self) -> None:
        render.render_markdown(self.output)
        markdown = self.output / "test-cases-md/TC-001.md"
        markdown.write_text(markdown.read_text(encoding="utf-8").replace("Submit", "Send"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs"):
            render.render_report(self.output)
        markdown.unlink()
        with self.assertRaisesRegex(ValueError, "Missing Markdown artifact"):
            render.render_report(self.output)

    def test_renderer_refuses_invalid_output(self) -> None:
        (self.output / "test-cases" / "TC-001.json").unlink()
        with self.assertRaisesRegex(ValueError, "Output validation failed"):
            render.render_report(self.output)


class OfficialTitleTests(unittest.TestCase):
    def test_label_uses_stored_identifier_and_title_only(self) -> None:
        requirement = {
            "id": "REQ-001", "statement": "x", "source_identifier": "RF-7", "source_title": "Consulta de Saldo",
            "source_refs": [{"source": "a.md", "reference": "RF-7 header"}],
        }
        self.assertEqual("RF-7 — Consulta de Saldo", render.requirement_label(requirement))

    def test_reference_text_is_never_parsed_into_a_title(self) -> None:
        requirement = {"id": "REQ-002", "statement": "x", "source_refs": [{"source": "a.md", "reference": "RF-8 header"}]}
        label = render.requirement_label(requirement)
        self.assertEqual("REQ-002", label)
        self.assertNotIn("header", label)


if __name__ == "__main__":
    unittest.main()
