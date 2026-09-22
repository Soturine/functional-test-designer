from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GROUPS = load_script("requirement_groups")
MARKDOWN = load_script("render_markdown")
REPORT = load_script("render_report")


class RequirementGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def read(self, relative: str) -> dict:
        return json.loads((self.output / relative).read_text(encoding="utf-8"))

    def write(self, relative: str, value: dict) -> None:
        (self.output / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_original_rf_identifier_is_derived_without_schema_change(self) -> None:
        requirement = {
            "id": "REQ-001",
            "statement": "Finalize an order.",
            "source_refs": [{"source": "requirements.md", "reference": "RF003 - Finalization"}],
        }

        self.assertEqual("RF003", GROUPS.original_rf_identifier(requirement))

    def test_fallback_uses_normalized_requirement_id(self) -> None:
        requirement = {
            "id": "REQ-001",
            "statement": "Finalize an order.",
            "source_refs": [{"source": "requirements.md", "reference": "Order finalization"}],
        }

        self.assertEqual({"REQ-001": "REQ-001"}, GROUPS.requirement_group_map([requirement]))

    def test_official_title_and_missing_title_are_presentational(self) -> None:
        titled = {
            "id": "REQ-001", "statement": "Finalize.",
            "source_refs": [{"reference": "RF006 — Inventory operations"}],
        }
        untitled = {
            "id": "REQ-002", "statement": "Audit.",
            "source_refs": [{"reference": "RN012"}],
        }

        self.assertEqual("RF006 — Inventory operations", GROUPS.requirement_group_label(titled))
        self.assertEqual("RN012 — Audit.", GROUPS.requirement_group_label(untitled))

    def test_markdown_and_html_show_rf_group_without_changing_json_or_paths(self) -> None:
        index = self.read("test-cases.json")
        before = json.dumps(index, sort_keys=True)
        index["requirements"][0]["source_refs"][0]["reference"] = "RF003 - Create order"
        self.write("test-cases.json", index)

        MARKDOWN.render_markdown(self.output)
        report = REPORT.render_report(self.output).read_text(encoding="utf-8")
        markdown = (self.output / "test-cases-md" / "TC-001.md").read_text(encoding="utf-8")
        after = self.read("test-cases.json")

        self.assertIn("**Requirement group:** RF003 — Create order", markdown)
        self.assertIn('data-requirement-group="RF003 — Create order"', report)
        self.assertIn('id="rf-RF003"', report)
        self.assertIn('id="rf-filter"', report)
        self.assertIn('class="rf-navigation"', report)
        self.assertIn('class="group-toggle"', report)
        self.assertIn('Source claims:', report)
        self.assertIn('id="feature-filter"', report)
        self.assertEqual(len(after["test_cases"]), report.count('class="tc-card"'))
        self.assertEqual(
            [entry["file"] for entry in json.loads(before)["test_cases"]],
            [entry["file"] for entry in after["test_cases"]],
        )

    def test_multi_rf_case_uses_first_source_order_group_without_duplication(self) -> None:
        requirements = [
            {"id": "REQ-001", "source_refs": [{"reference": "RF002"}], "statement": "First"},
            {"id": "REQ-002", "source_refs": [{"reference": "RF004"}], "statement": "Second"},
        ]
        groups = GROUPS.requirement_group_map(requirements)
        case = {"id": "TC-010", "requirement_refs": ["REQ-002", "REQ-001"], "tags": []}

        primary, related, _ = GROUPS.case_group(case, groups, {"REQ-001": 0, "REQ-002": 1})

        self.assertEqual("RF002 — First", primary)
        self.assertEqual(["RF004 — Second"], related)

    def test_explicit_e2e_case_uses_cross_rf_group_once(self) -> None:
        groups = {"REQ-001": "RF002", "REQ-002": "RF004"}
        case = {
            "id": "TC-010",
            "requirement_refs": ["REQ-001", "REQ-002"],
            "tags": ["e2e"],
        }

        primary, related, _ = GROUPS.case_group(case, groups, {"REQ-001": 0, "REQ-002": 1})

        self.assertEqual("Cross-RF / End-to-End", primary)
        self.assertEqual(["RF002", "RF004"], related)


if __name__ == "__main__":
    unittest.main()
