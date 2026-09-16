from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_output", ROOT / "scripts" / "validate_output.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load validator")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ValidatorTests(unittest.TestCase):
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

    def test_expected_output_passes(self) -> None:
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_v12_cases_have_no_subtests_and_can_have_multiple_steps(self) -> None:
        cases = [self.read(entry["file"]) for entry in self.read("test-cases.json")["test_cases"]]

        self.assertTrue(all("subtests" not in case for case in cases))
        self.assertGreater(len(cases[0]["steps"]), 1)

    def test_sources_declare_roles_and_selected_code_is_evidence(self) -> None:
        index = self.read("test-cases.json")
        sources = {item["path"]: item["role"] for item in index["sources"]}

        self.assertEqual("FUNCTIONAL_AUTHORITY", sources["examples/requirements.md"])
        self.assertEqual(
            "IMPLEMENTATION_EVIDENCE",
            sources["examples/selected-source/order_service.py"],
        )
        self.assertEqual("IMPLEMENTATION_DIVERGENCE", index["findings"][0]["type"])

    def test_implementation_evidence_does_not_replace_normative_result(self) -> None:
        case = self.read("test-cases/TC-006.json")

        self.assertIn("SUBMITTED", case["steps"][0]["expected_result"])
        self.assertNotIn("PROCESSING", case["steps"][0]["expected_result"])
        self.assertTrue(any("diverges" in note for note in case["notes"]))
        self.assertEqual(1, len(case["steps"]))

    def test_selected_code_gap_has_one_new_independent_case(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-011.json")
        finding = next(item for item in index["findings"] if item["id"] == "FND-002")

        self.assertEqual("COVERAGE_GAP", finding["type"])
        self.assertEqual(["CP-023", "CP-024"], case["coverage_point_refs"])
        self.assertIn("FINALIZED", case["steps"][0]["expected_result"])
        self.assertIn("visible confirmation", case["steps"][0]["expected_result"])

    def test_test_data_is_local_to_each_case(self) -> None:
        index = self.read("test-cases.json")
        cases = [self.read(entry["file"]) for entry in index["test_cases"]]

        self.assertNotIn("test_data", index)
        self.assertTrue(all("test_data" in case for case in cases))

    def test_known_and_ambiguous_parts_have_separate_destinations(self) -> None:
        coverage = {
            item["id"]: item for item in self.read("test-cases.json")["coverage_points"]
        }

        self.assertEqual("TEST_CASE", coverage["CP-019"]["disposition"])
        self.assertEqual("TEST_CASE", coverage["CP-020"]["disposition"])
        self.assertEqual("QUESTION", coverage["CP-021"]["disposition"])

    def test_coverage_audit_preserves_independently_failing_effects(self) -> None:
        coverage = self.read("test-cases.json")["coverage_points"]
        by_requirement = {
            requirement: [item for item in coverage if item["requirement_ref"] == requirement]
            for requirement in {item["requirement_ref"] for item in coverage}
        }

        self.assertEqual(3, len(by_requirement["REQ-001"]))
        self.assertEqual(4, len(by_requirement["REQ-004"]))
        self.assertEqual(3, len(by_requirement["REQ-006"]))
        self.assertEqual(2, len(by_requirement["REQ-008"]))

    def test_duplicate_requirement_id_fails(self) -> None:
        index = self.read("test-cases.json")
        index["requirements"].append(copy.deepcopy(index["requirements"][0]))
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("duplicate requirement ID: REQ-001" in error for error in errors))

    def test_duplicate_scenario_candidate_fails_after_early_deduplication(self) -> None:
        index = self.read("test-cases.json")
        duplicate = copy.deepcopy(index["scenarios"][0])
        duplicate["id"] = "SCN-999"
        index["scenarios"].append(duplicate)
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("duplicate scenario remains after early deduplication" in error for error in errors))

    def test_one_test_case_cannot_hide_multiple_independent_scenarios(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-001.json")
        index["test_cases"][0]["scenario_refs"].append("SCN-002")
        case["scenario_refs"].append("SCN-002")
        self.write("test-cases.json", index)
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("TC-001 must reference exactly one independent scenario" in error for error in errors))

    def test_independent_scenario_cannot_be_reused_by_another_case(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-002.json")
        index["test_cases"][1]["scenario_refs"] = ["SCN-001"]
        case["scenario_refs"] = ["SCN-001"]
        self.write("test-cases.json", index)
        self.write("test-cases/TC-002.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("SCN-001 is reused by 2 test cases" in error for error in errors))
        self.assertTrue(any("SCN-002 is not materialized" in error for error in errors))

    def test_missing_case_file_fails(self) -> None:
        (self.output / "test-cases" / "TC-001.json").unlink()

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("missing file" in error for error in errors))

    def test_blocking_question_requires_blocked_case(self) -> None:
        questions = self.read("questions.json")
        questions["questions"][1]["blocking"] = True
        self.write("questions.json", questions)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("Q-002 is blocking but TC-010 status is not BLOCKED" in error for error in errors))

    def test_nonconsecutive_steps_fail(self) -> None:
        case = self.read("test-cases/TC-001.json")
        case["steps"][1]["step"] = 3
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("step numbers must be ordered consecutively" in error for error in errors))

    def test_case_source_must_be_declared(self) -> None:
        case = self.read("test-cases/TC-001.json")
        case["source_refs"][0]["source"] = "unknown.md"
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("TC-001 references source absent from index sources" in error for error in errors))

    def test_case_requirement_must_be_covered_by_scenario(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-001.json")
        index["test_cases"][0]["requirement_refs"] = ["REQ-002"]
        case["requirement_refs"] = ["REQ-002"]
        self.write("test-cases.json", index)
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("REQ-002 is not covered by its referenced scenarios" in error for error in errors))

    def test_coverage_point_to_existing_test_case_passes(self) -> None:
        index = self.read("test-cases.json")
        coverage_point = next(item for item in index["coverage_points"] if item["id"] == "CP-001")

        self.assertEqual("TEST_CASE", coverage_point["disposition"])
        self.assertEqual(["TC-001"], coverage_point["target_refs"])
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_coverage_point_to_missing_test_case_fails(self) -> None:
        index = self.read("test-cases.json")
        index["coverage_points"][0]["target_refs"] = ["TC-999"]
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("CP-001 has no valid destination" in error for error in errors))

    def test_coverage_point_to_existing_question_passes(self) -> None:
        index = self.read("test-cases.json")
        coverage_point = next(item for item in index["coverage_points"] if item["id"] == "CP-018")

        self.assertEqual("QUESTION", coverage_point["disposition"])
        self.assertEqual(["Q-001"], coverage_point["target_refs"])
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_out_of_scope_without_reason_fails(self) -> None:
        index = self.read("test-cases.json")
        index["coverage_points"].append(
            {
                "id": "CP-999",
                "requirement_ref": "REQ-001",
                "statement": "Explicitly excluded synthetic behavior.",
                "source_refs": [{"source": "examples/requirements.md", "reference": "ORD-001"}],
                "disposition": "OUT_OF_SCOPE",
                "target_refs": [],
            }
        )
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("CP-999 has no valid destination" in error for error in errors))

    def test_testable_requirement_without_coverage_point_fails(self) -> None:
        index = self.read("test-cases.json")
        index["requirements"].append(
            {
                "id": "REQ-999",
                "statement": "Synthetic testable behavior.",
                "status": "TESTABLE",
                "source_refs": [{"source": "examples/requirements.md", "reference": "Synthetic"}],
            }
        )
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("REQ-999 is TESTABLE but has no coverage point" in error for error in errors))

    def test_unknown_finding_source_fails(self) -> None:
        index = self.read("test-cases.json")
        index["findings"][0]["source_refs"][1]["source"] = "unselected.py"
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("FND-001 references source absent" in error for error in errors))

    def test_markdown_path_is_specific_to_case(self) -> None:
        index = self.read("test-cases.json")
        index["test_cases"][0]["markdown_file"] = "test-cases-md/TC-002.md"
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("TC-001 markdown_file must be test-cases-md/TC-001.md" in error for error in errors))

    def test_materialized_normative_clause_requires_exact_coverage_destination(self) -> None:
        index = self.read("test-cases.json")
        index["normative_clauses"] = [
            {
                "id": "CLAUSE-001",
                "requirement_ref": "REQ-001",
                "normalized_claim": "The created order has a visible reference.",
                "authority": "FUNCTIONAL_AUTHORITY",
                "source_refs": [{"source": "examples/requirements.md", "reference": "ORD-001"}],
                "destination_type": "COVERAGE_POINT",
                "destination_id": "CP-001",
            }
        ]
        self.write("test-cases.json", index)

        self.assertEqual([], VALIDATOR.validate(self.output))

        index["normative_clauses"][0]["destination_id"] = "CP-999"
        self.write("test-cases.json", index)
        errors = VALIDATOR.validate(self.output)
        self.assertTrue(any("CLAUSE-001 has no valid coverage_point destination" in error for error in errors))

    def test_unmapped_materialized_clause_fails_even_when_requirement_has_coverage(self) -> None:
        index = self.read("test-cases.json")
        index["normative_clauses"][0]["destination_id"] = None
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("CLAUSE-001 has no valid coverage_point destination" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
