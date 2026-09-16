from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_markdown", ROOT / "scripts" / "render_markdown.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load Markdown renderer")
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MarkdownRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_one_markdown_per_case_contains_every_step_and_expected_result(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        rendered = RENDERER.render_markdown(self.output)

        self.assertEqual(len(index["test_cases"]), len(rendered))
        for entry in index["test_cases"]:
            case = json.loads((self.output / entry["file"]).read_text(encoding="utf-8"))
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            for step in case["steps"]:
                self.assertIn(step["action"], markdown)
                self.assertIn(step["expected_result"] or "Clarification required", markdown)

    def test_mermaid_is_last_and_has_only_linear_step_flow(self) -> None:
        RENDERER.render_markdown(self.output)
        case = json.loads((self.output / "test-cases/TC-001.json").read_text(encoding="utf-8"))
        markdown = (self.output / "test-cases-md/TC-001.md").read_text(encoding="utf-8")
        mermaid = RENDERER.extract_mermaid(markdown)

        self.assertTrue(markdown.rstrip().endswith("```"))
        self.assertEqual(RENDERER.mermaid_source(case), mermaid)
        self.assertNotIn("-->|", mermaid)
        self.assertIn("S --> A1 --> R1 --> A2 --> R2 --> F", mermaid)
        self.assertIn("classDef action", mermaid)
        self.assertIn("classDef expected", mermaid)
        self.assertIn("class S,F startEnd", mermaid)

    def test_missing_expected_result_is_marked_without_invention(self) -> None:
        case = json.loads((self.output / "test-cases/TC-010.json").read_text(encoding="utf-8"))
        case["steps"][0]["expected_result"] = None
        case["steps"][0]["needs_clarification"] = True

        markdown = RENDERER.render_case(case, "test-cases/TC-010.json")

        self.assertIn("Clarification required", markdown)
        self.assertIn("class C1 clarification", markdown)

    def test_mermaid_wraps_long_labels_without_changing_json(self) -> None:
        label = "Confirm the synthetic reservation and then inspect the resulting availability for the selected item"

        wrapped = RENDERER.wrap_mermaid_label(label, width=50)

        self.assertIn("<br/>", wrapped)
        self.assertEqual(label, wrapped.replace("<br/>", " "))

    def test_mermaid_sanitizes_parser_breaking_content(self) -> None:
        label = '<script>"bad" [node] {shape} | value & more'

        sanitized = RENDERER.wrap_mermaid_label(label)

        for token in ('<script>', '"', "[", "]", "{", "}", "|"):
            self.assertNotIn(token, sanitized)

    def test_renderer_does_not_change_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path.relative_to(self.output): digest(path) for path in json_files}

        RENDERER.render_markdown(self.output)

        after = {path.relative_to(self.output): digest(path) for path in json_files}
        self.assertEqual(before, after)

    def test_repository_has_no_per_run_generator_script(self) -> None:
        scripts = {path.name for path in (ROOT / "scripts").glob("*.py")}
        self.assertFalse(any(name.startswith("generate_") for name in scripts))


if __name__ == "__main__":
    unittest.main()
