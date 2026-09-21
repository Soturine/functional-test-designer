"""The operational catalog and risk-oriented suites reuse one canonical Test Case."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from azure_devops_adapter import build_preview, build_suite_mapping  # noqa: E402
from canonical_state import OutputSelection, persist_canonical_suite, render_selected_outputs  # noqa: E402
from render_operational_scenarios import (  # noqa: E402
    build_operational_catalog, render_operational_scenarios,
)


def case(case_id: str = "TC-042", **overrides: object) -> dict[str, object]:
    value = {
        "schema_version": "1.2", "id": case_id, "title": "Reject a duplicate submission",
        "status": "READY", "priority": "HIGH", "type": "FUNCTIONAL",
        "objective": "Reject a duplicate submission.",
        "requirement_refs": ["REQ-002"], "scenario_refs": ["SCN-002"],
        "coverage_point_refs": ["CP-002"],
        "source_refs": [{"source": "requirements.md", "reference": "RF-002"}],
        "preconditions": ["An operator with submit permission is authenticated."],
        "test_data": [{"name": "submission", "description": "reference = 4821"}],
        "steps": [{"step": 1, "action": "Submit the same reference twice.",
                   "expected_result": "The second submission is rejected.",
                   "needs_clarification": False}],
        "postconditions": [], "cleanup": [], "tags": ["negative", "operator-error"],
        "notes": [],
    }
    value.update(overrides)
    return value


def family(**overrides: object) -> dict[str, object]:
    value = {
        "id": "OPS-001", "title": "Duplicate submission by the same operator",
        "test_case_refs": ["TC-042"], "requirement_refs": ["REQ-002", "CP-002"],
        "actor": "Warehouse operator with submit permission",
        "location": "Receiving station", "tools": "Handheld scanner",
        "starting_state": "One pending submission exists",
        "trigger": "The same reference is submitted a second time",
        "risk": "Duplicate action creates a second record",
        "oracle_source": "requirements.md RF-002",
        "recovery": "Cancel the pending submission",
        "tags": ["negative", "operator-error"], "open_questions": [],
    }
    value.update(overrides)
    return value


class OperationalCatalogTests(unittest.TestCase):
    def test_a_family_cannot_link_a_test_case_that_does_not_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown Test Cases"):
            build_operational_catalog([family(test_case_refs=["TC-999"])], [case()])

    def test_a_family_must_link_at_least_one_canonical_test_case(self) -> None:
        with self.assertRaisesRegex(ValueError, "links no Test Case"):
            build_operational_catalog([family(test_case_refs=[])], [case()])

    def test_the_catalog_reuses_readiness_from_canonical_state(self) -> None:
        catalog = build_operational_catalog([family()], [case()])
        self.assertEqual(["READY"], catalog["families"][0]["readiness"])
        self.assertEqual(1, catalog["family_count"])

    def test_unsupported_detail_is_shown_as_unsupported_rather_than_invented(self) -> None:
        catalog = build_operational_catalog([family(tools="", location="")], [case()])
        markdown = render_operational_scenarios(catalog)
        self.assertIn("Tools / device: Not supported by the selected evidence", markdown)
        self.assertIn("Location / context: Not supported by the selected evidence", markdown)

    def test_rendering_is_deterministic_and_links_canonical_ids(self) -> None:
        catalog = build_operational_catalog([family()], [case()])
        first = render_operational_scenarios(catalog)
        self.assertEqual(first, render_operational_scenarios(catalog))
        self.assertIn("OPS-001", first)
        self.assertIn("Test Cases: TC-042", first)

    def test_an_empty_catalog_renders_without_inventing_families(self) -> None:
        markdown = render_operational_scenarios(build_operational_catalog([], [case()]))
        self.assertIn("No operational scenario family", markdown)


class OperationalOutputSelectionTests(unittest.TestCase):
    def index(self) -> dict[str, object]:
        return {
            "schema_version": "1.2", "generated_at": "2026-01-01T00:00:00Z",
            "sources": [{"path": "requirements.md", "role": "FUNCTIONAL_AUTHORITY"}],
            "requirements": [{
                "id": "REQ-002", "statement": "Duplicate submissions are rejected.",
                "status": "TESTABLE",
                "source_refs": [{"source": "requirements.md", "reference": "RF-002"}],
            }],
            "normative_clauses": [{
                "id": "CLAUSE-002", "requirement_ref": "REQ-002",
                "normalized_claim": "A duplicate submission is rejected.",
                "authority": "FUNCTIONAL_AUTHORITY",
                "source_refs": [{"source": "requirements.md", "reference": "RF-002"}],
                "destination_type": "COVERAGE_POINT", "destination_id": "CP-002",
            }],
            "findings": [],
            "coverage_points": [{
                "id": "CP-002", "requirement_ref": "REQ-002",
                "statement": "The duplicate submission is rejected.",
                "clause_refs": ["CLAUSE-002"],
                "source_refs": [{"source": "requirements.md", "reference": "RF-002"}],
                "disposition": "TEST_CASE", "target_refs": ["TC-042"],
            }],
            "scenarios": [{"id": "SCN-002", "title": "Duplicate submission",
                           "type": "NEGATIVE", "requirement_refs": ["REQ-002"]}],
            "test_cases": [{
                "id": "TC-042", "title": "Reject a duplicate submission", "status": "READY",
                "requirement_refs": ["REQ-002"], "scenario_refs": ["SCN-002"],
                "coverage_point_refs": ["CP-002"],
                "file": "test-cases/TC-042.json", "markdown_file": "test-cases-md/TC-042.md",
            }],
        }

    def render(self, formats: list[str], root: Path) -> dict[str, object]:
        canonical = persist_canonical_suite(
            root, "run-ops", index=self.index(),
            questions={"schema_version": "1.2", "questions": []}, cases=[case()],
            operational_catalog=build_operational_catalog([family()], [case()]),
        )
        return render_selected_outputs(canonical, root, OutputSelection.normalize(formats))

    def test_the_catalog_is_optional_and_absent_from_a_json_only_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rendered = self.render(["JSON"], root)
            self.assertEqual(["JSON"], rendered["rendered_public_formats"])
            self.assertFalse((root / "output" / "operational-scenarios.md").exists())

    def test_the_catalog_is_rendered_from_canonical_state_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rendered = self.render(["JSON", "OPERATIONAL"], root)
            catalog = root / "output" / "operational-scenarios.md"
            self.assertIn("OPERATIONAL", rendered["rendered_public_formats"])
            self.assertIn("TC-042", catalog.read_text(encoding="utf-8"))
            self.assertEqual(0, rendered["source_reads_during_render"])


class AzureSuiteMappingTests(unittest.TestCase):
    def test_one_canonical_case_reaches_requirement_and_risk_suites_without_cloning(self) -> None:
        mapping = build_suite_mapping(
            [case()], requirement_suite="Requirement-based suite",
            risk_suites={"negative": "Operational Adversarial"},
        )
        membership = mapping["memberships"][0]
        self.assertEqual(1, mapping["canonical_test_cases"])
        self.assertEqual(0, mapping["cloned_test_cases"])
        self.assertEqual(2, mapping["suite_placements"])
        self.assertEqual(
            ["Requirement-based suite", "Operational Adversarial"],
            [item["suite"] for item in membership["suites"]],
        )
        self.assertEqual(["TC-042"], mapping["suite_members"]["Operational Adversarial"])
        self.assertEqual(["TC-042"], mapping["suite_members"]["Requirement-based suite"])

    def test_an_untagged_case_stays_in_the_requirement_suite_only(self) -> None:
        mapping = build_suite_mapping(
            [case(tags=[])], requirement_suite="Requirement-based suite",
        )
        self.assertEqual(1, mapping["suite_placements"])

    def test_an_unsupported_risk_suite_tag_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported risk suite tags"):
            build_suite_mapping(
                [case()], requirement_suite="Suite", risk_suites={"made-up": "Elsewhere"},
            )

    def test_the_preview_carries_the_mapping_without_extra_payloads(self) -> None:
        mapping = build_suite_mapping(
            [case()], requirement_suite="Requirement-based suite",
            risk_suites={"operator-error": "Operational Adversarial"},
        )
        preview = build_preview(
            [case()], {}, project="Demo", plan="Regression", suite="Requirement-based suite",
            suite_mapping=mapping,
        )
        self.assertEqual(1, len(preview["create"]))
        self.assertEqual(2, preview["suite_mapping"]["suite_placements"])
        self.assertEqual(
            ["TC-042"], [item["local_id"] for item in preview["create"]],
        )


if __name__ == "__main__":
    unittest.main()
