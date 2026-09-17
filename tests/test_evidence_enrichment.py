from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "expected-output"
BENCHMARK = ROOT / "benchmarks" / "multi-source-enrichment"
NORMATIVE_BASELINE_SHA256 = "6e2a6a35beb93390b3c1643b12e612add53ddc26ade5bdbffab8672645ac1b19"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class EvidenceEnrichmentTests(unittest.TestCase):
    def test_manual_enriches_steps_without_replacing_normative_oracle(self) -> None:
        case = read_json(OUTPUT / "test-cases" / "TC-011.json")

        self.assertEqual(3, len(case["steps"]))
        self.assertIn("Orders", case["steps"][0]["action"])
        self.assertIn("Search", case["steps"][0]["action"])
        self.assertEqual(
            "The order state changes to FINALIZED and a visible confirmation is shown.",
            case["steps"][-1]["expected_result"],
        )
        sources = {ref["source"] for ref in case["source_refs"]}
        self.assertEqual(
            {
                "examples/requirements.md",
                "examples/selected-source/user-guide.md",
                "examples/selected-source/order_service.py",
            },
            sources,
        )

    def test_implementation_only_details_do_not_become_normative_claims(self) -> None:
        expected_case = read_json(BENCHMARK / "expected-case.json")
        assessment = read_json(BENCHMARK / "expected-assessment.json")
        case_text = json.dumps(expected_case)

        self.assertIn(assessment["normative_oracle"], expected_case["steps"][-1]["expected_result"])
        self.assertNotIn("internal_timestamp", case_text)
        self.assertNotIn("PARTIAL", case_text)
        self.assertIn("PROCESSING", expected_case["notes"][0])
        self.assertTrue(assessment["required_question"].endswith("?"))

    def test_test_asset_opportunities_are_preserved_without_subtests(self) -> None:
        assessment = read_json(BENCHMARK / "expected-assessment.json")

        self.assertEqual(3, len(assessment["test_asset_opportunities"]))
        self.assertNotIn("subtests", json.dumps(read_json(BENCHMARK / "expected-case.json")))

    def test_concrete_length_data_does_not_invent_character_format(self) -> None:
        data = read_json(BENCHMARK / "expected-assessment.json")["reference_data"]

        self.assertEqual(8, len(data["supported_valid_value"]))
        self.assertEqual(7, len(data["supported_invalid_value"]))
        self.assertEqual("letters-only format", data["unsupported_inference"])

    def test_one_step_remains_valid_when_one_action_reaches_the_result(self) -> None:
        case = {
            "preconditions": ["Dashboard is open."],
            "steps": [{"step": 1, "action": "Select Refresh.", "expected_result": "The counter updates."}],
        }

        self.assertEqual(1, len(case["steps"]))
        self.assertNotIn("login", case["steps"][0]["action"].casefold())

    def test_missing_execution_path_does_not_invent_ui_or_api(self) -> None:
        path_case = read_json(BENCHMARK / "expected-assessment.json")["unsupported_path_case"]

        self.assertEqual("NEEDS_REVIEW", path_case["status"])
        for invented in path_case["forbidden_actions"]:
            self.assertNotEqual(invented, path_case["action"])

    def test_enrichment_does_not_change_normative_design_baseline(self) -> None:
        index = read_json(OUTPUT / "test-cases.json")
        questions = read_json(OUTPUT / "questions.json")
        case_oracles = []
        for entry in index["test_cases"]:
            case = read_json(OUTPUT / entry["file"])
            case_oracles.append(
                {
                    key: case[key]
                    for key in ("id", "status", "requirement_refs", "scenario_refs", "coverage_point_refs")
                }
                | {"normative_oracle": case["steps"][-1]["expected_result"]}
            )
        projection = {
            "schema_version": index["schema_version"],
            "requirements": index["requirements"],
            "normative_clauses": index["normative_clauses"],
            "findings": index["findings"],
            "coverage_points": index["coverage_points"],
            "scenarios": index["scenarios"],
            "test_cases": [
                {
                    key: entry[key]
                    for key in (
                        "id", "title", "status", "requirement_refs", "scenario_refs",
                        "coverage_point_refs", "file", "markdown_file",
                    )
                }
                for entry in index["test_cases"]
            ],
            "case_oracles": case_oracles,
            "questions": questions["questions"],
        }
        canonical = json.dumps(
            projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()

        self.assertEqual(NORMATIVE_BASELINE_SHA256, hashlib.sha256(canonical).hexdigest())

    def test_public_output_contract_and_paths_remain_unchanged(self) -> None:
        index = read_json(OUTPUT / "test-cases.json")

        self.assertEqual("1.2", index["schema_version"])
        self.assertTrue(all(entry["file"] == f"test-cases/{entry['id']}.json" for entry in index["test_cases"]))
        self.assertTrue(all(entry["markdown_file"] == f"test-cases-md/{entry['id']}.md" for entry in index["test_cases"]))

    def test_benchmark_case_uses_the_unchanged_v12_case_schema(self) -> None:
        schema = read_json(ROOT / "schemas" / "test-case.schema.json")
        case = read_json(BENCHMARK / "expected-case.json")

        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(case)))


if __name__ == "__main__":
    unittest.main()
