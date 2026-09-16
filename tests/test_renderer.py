from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_report", ROOT / "scripts" / "render_report.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load renderer")
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_renderer_creates_offline_html_without_changing_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path.relative_to(self.output): digest(path) for path in json_files}

        report_path = RENDERER.render_report(self.output)
        report = report_path.read_text(encoding="utf-8")
        after = {path.relative_to(self.output): digest(path) for path in json_files}

        self.assertEqual(before, after)
        self.assertEqual((self.output / "report.html").resolve(), report_path)
        self.assertIn("Passos", report)
        self.assertIn("Submit a create-order request", report)
        self.assertIn("Perguntas", report)
        self.assertIn("Cobertura", report)
        self.assertIn("The minimum quantity 1 is accepted.", report)
        self.assertIn("Fluxo do Teste", report)
        self.assertIn('href="test-cases/TC-001.json"', report)
        self.assertIn('href="test-cases-md/TC-001.md"', report)
        self.assertIn('href="test-cases/TC-010.json"', report)
        self.assertIn('href="test-cases-md/TC-010.md"', report)
        self.assertEqual(10, report.count('class="tc-card"'))
        self.assertNotIn("https://", report)
        self.assertNotIn("<script src=", report)

    def test_html_uses_the_exact_mermaid_from_each_markdown(self) -> None:
        report = RENDERER.render_report(self.output).read_text(encoding="utf-8")
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))

        for entry in index["test_cases"]:
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            mermaid = RENDERER.extract_mermaid(markdown)
            self.assertIn(RENDERER.esc(mermaid), report)

    def test_html_refuses_missing_or_divergent_markdown(self) -> None:
        markdown_path = self.output / "test-cases-md/TC-001.md"
        markdown_path.unlink()

        with self.assertRaisesRegex(ValueError, "Missing Markdown artifact for TC-001"):
            RENDERER.render_report(self.output)

    def test_json_markdown_and_cards_remain_one_to_one(self) -> None:
        report = RENDERER.render_report(self.output).read_text(encoding="utf-8")
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        markdown_files = list((self.output / "test-cases-md").glob("*.md"))

        self.assertEqual(len(index["test_cases"]), len(markdown_files))
        self.assertEqual(len(index["test_cases"]), report.count('class="tc-card"'))
        for entry in index["test_cases"]:
            self.assertIn(entry["file"], report)
            self.assertIn(entry["markdown_file"], report)

    def test_renderer_refuses_invalid_output(self) -> None:
        (self.output / "test-cases" / "TC-001.json").unlink()

        with self.assertRaisesRegex(ValueError, "Output validation failed"):
            RENDERER.render_report(self.output)


if __name__ == "__main__":
    unittest.main()
