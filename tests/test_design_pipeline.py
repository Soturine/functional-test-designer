from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from procedural_execution import (  # noqa: E402
    assert_identity_preserved,
    compose_path,
    synthesize_test_case,
)
from run_synthetic_e2e import run  # noqa: E402
from scenario_independence import TestIdentity, build_scenario_pipeline  # noqa: E402
from validate_output import validate  # noqa: E402


def coverage(cp_id: str, req_id: str = "REQ-001") -> dict:
    return {
        "id": cp_id,
        "requirement_ref": req_id,
        "source_refs": [{"source": "requirements.md", "reference": cp_id}],
        "disposition": "TEST_CASE",
        "target_refs": [],
    }


def profile(title: str, oracle: str, **values) -> dict:
    return {"title": title, "behavior": title, "normative_oracle": oracle, **values}


class ProductionScenarioPipelineTests(unittest.TestCase):
    def test_every_testable_cp_enters_candidate_first_pipeline(self) -> None:
        points = [coverage(f"CP-{number:03d}") for number in range(1, 4)]
        profiles = {
            point["id"]: profile(point["id"], f"{point['id']} result") for point in points
        }

        result = build_scenario_pipeline(points, profiles)

        self.assertEqual(3, result["metrics"]["testable_coverage_points"])
        self.assertEqual(3, result["metrics"]["scenario_candidates_before_merge"])
        self.assertEqual(3, result["metrics"]["scenarios_after_merge"])
        self.assertEqual(0, result["metrics"]["scenario_merges_applied"])

    def test_missing_candidate_profile_is_a_structural_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "has no scenario candidate profile"):
            build_scenario_pipeline([coverage("CP-001")], {})

    def test_generic_or_implementation_oracle_cannot_replace_normative_oracle(self) -> None:
        with self.assertRaisesRegex(ValueError, "has no normative oracle"):
            build_scenario_pipeline(
                [coverage("CP-001")],
                {"CP-001": {"title": "Confirm", "behavior": "Confirm", "oracle": "State is REVIEWED"}},
            )

    def test_candidate_reduction_equals_explicit_merge_decisions(self) -> None:
        shared = {
            "title": "Commit one transaction", "normative_oracle": "All effects are committed.",
            "nature": "functional", "input_partition": "valid", "actor": "operator",
            "setup": "pending transaction", "preconditions": ["pending"], "state": "PENDING",
            "trigger": "commit", "objective": "atomic commit", "execution_evidence": "response",
            "reporting_purpose": "transaction", "pass_fail_boundary": "atomic commit",
            "continuous_execution": True, "can_fail_independently": False,
            "merge_key": "commit", "merge_reason": "INSEPARABLE_SAME_EVENT",
        }
        points = [coverage("CP-001"), coverage("CP-002")]
        profiles = {
            "CP-001": {**shared, "behavior": "change state"},
            "CP-002": {**shared, "behavior": "write audit"},
        }

        result = build_scenario_pipeline(points, profiles)

        metrics = result["metrics"]
        self.assertEqual(
            metrics["scenario_candidates_before_merge"] - metrics["scenario_merges_applied"],
            metrics["scenarios_after_merge"],
        )
        self.assertEqual("INSEPARABLE_SAME_EVENT", result["merge_decisions"][0]["reason"])
        self.assertEqual(0, metrics["possible_scenario_overcompression_warnings"])

    def test_frozen_identity_is_immutable(self) -> None:
        result = build_scenario_pipeline(
            [coverage("CP-001")],
            {"CP-001": profile("Reject malformed input", "HTTP 400 is returned.")},
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            result["test_identities"][0].title = "Changed"  # type: ignore[misc]


class ProceduralExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = TestIdentity(
            id="TC-001",
            title="Confirm reservation",
            scenario_ref="SCN-001",
            scenario_type="STATE_TRANSITION",
            requirement_refs=("REQ-001",),
            coverage_point_refs=("CP-001",),
            normative_source_refs=(("requirements.md", "RSV-001"),),
            normative_oracle="The reservation state is CONFIRMED.",
        )
        self.manual_ref = {"source": "manual.md", "reference": "Confirm reservation"}

    def test_documented_path_becomes_real_ordered_steps(self) -> None:
        actions = [
            {"action": "Open the reservation list.", "expected_result": "The list is presented.", "evidence_source": self.manual_ref},
            {"action": "Search by reservation identifier.", "expected_result": "The reservation is displayed.", "evidence_source": self.manual_ref, "depends_on_previous_step": True},
            {"action": "Open the reservation detail.", "expected_result": "The detail is presented.", "evidence_source": self.manual_ref, "depends_on_previous_step": True},
            {"action": "Choose Confirm.", "expected_result": "Confirmation is available.", "evidence_source": self.manual_ref, "depends_on_previous_step": True},
            {"action": "Provide the required input.", "expected_result": "The input is retained.", "evidence_source": self.manual_ref, "depends_on_previous_step": True},
            {"action": "Confirm the action.", "expected_result": "The action is submitted.", "evidence_source": self.manual_ref, "depends_on_previous_step": True},
            {"action": "Review the resulting state.", "depends_on_previous_step": True},
        ]

        case = synthesize_test_case(
            self.identity,
            {"actions": actions, "source_refs": [self.manual_ref], "preconditions": [], "test_data": []},
        )

        self.assertEqual(7, len(case["steps"]))
        self.assertEqual(list(range(1, 8)), [step["step"] for step in case["steps"]])
        self.assertEqual(self.identity.normative_oracle, case["steps"][-1]["expected_result"])
        self.assertNotIn("REVIEWED", json.dumps(case))

    def test_one_action_can_remain_one_step(self) -> None:
        identity = dataclasses.replace(
            self.identity,
            title="Reject malformed request",
            normative_oracle="HTTP 400 is returned.",
        )

        case = synthesize_test_case(identity, {"actions": [{"action": "Send the malformed request."}]})

        self.assertEqual(1, len(case["steps"]))
        self.assertEqual("HTTP 400 is returned.", case["steps"][0]["expected_result"])

    def test_unsupported_intermediate_expected_is_not_invented(self) -> None:
        case = synthesize_test_case(
            self.identity,
            {
                "actions": [
                    {"action": "Open the detail.", "expected_result": "A green modal appears."},
                    {"action": "Confirm.", "depends_on_previous_step": True},
                ]
            },
        )

        self.assertIsNone(case["steps"][0]["expected_result"])
        self.assertEqual("NEEDS_REVIEW", case["status"])

    def test_independent_variant_is_rejected_after_identity_freeze(self) -> None:
        with self.assertRaisesRegex(ValueError, "return it to scenario design"):
            synthesize_test_case(
                self.identity,
                {"actions": [{"action": "Try valid and invalid values.", "independent_variant": True}]},
            )

    def test_shared_navigation_does_not_merge_branch_identities(self) -> None:
        shared = [{"action": "Open the list.", "expected_result": "The list is shown.", "evidence_source": self.manual_ref}]
        confirm_path = compose_path(shared, [{"action": "Confirm.", "depends_on_previous_step": True}])
        cancel_path = compose_path(shared, [{"action": "Cancel.", "depends_on_previous_step": True}])
        cancel_identity = dataclasses.replace(
            self.identity,
            id="TC-002", title="Cancel reservation", scenario_ref="SCN-002",
            coverage_point_refs=("CP-002",), normative_oracle="The state is CANCELLED.",
        )

        confirm = synthesize_test_case(self.identity, {"actions": confirm_path})
        cancel = synthesize_test_case(cancel_identity, {"actions": cancel_path})

        self.assertEqual("TC-001", confirm["id"])
        self.assertEqual("TC-002", cancel["id"])
        self.assertNotEqual(confirm["scenario_refs"], cancel["scenario_refs"])

    def test_identity_guard_detects_post_synthesis_mutation(self) -> None:
        case = synthesize_test_case(self.identity, {"actions": [{"action": "Confirm."}]})
        case["coverage_point_refs"] = ["CP-999"]

        with self.assertRaisesRegex(ValueError, "changed frozen Test Case identity"):
            assert_identity_preserved(self.identity, case)


class FullPipelineE2ETests(unittest.TestCase):
    def test_synthetic_full_pipeline_materializes_valid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            result = run(Path(value))
            output = Path(result["output"])
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))

            self.assertEqual([], validate(output))
            self.assertEqual(5, result["metrics"]["testable_coverage_points"])
            self.assertEqual(5, result["metrics"]["scenario_candidates_before_merge"])
            self.assertEqual(2, result["metrics"]["scenario_merges_applied"])
            self.assertEqual(3, result["metrics"]["scenarios_after_merge"])
            self.assertEqual(3, result["metrics"]["test_cases_generated"])
            self.assertEqual(1, result["metrics"]["multi_cp_scenarios"])
            self.assertEqual(0, result["metrics"]["possible_scenario_overcompression_warnings"])
            self.assertEqual(4, len(result["cases"][0]["steps"]))
            self.assertEqual(4, len(result["cases"][1]["steps"]))
            self.assertEqual(1, len(result["cases"][2]["steps"]))
            self.assertIn("CONFIRMED", result["cases"][0]["steps"][-1]["expected_result"])
            self.assertNotIn("REVIEWED", result["cases"][0]["steps"][-1]["expected_result"])
            self.assertEqual(3, result["markdown_files"])
            self.assertTrue((output / "report.html").is_file())
            self.assertEqual("NEEDS_REVIEW", result["cases"][2]["status"])
            self.assertEqual(1, diagnostic["totals"]["questions"])
            self.assertEqual(1, diagnostic["totals"]["procedure_gaps"])
            self.assertEqual(1, diagnostic["totals"]["procedural_divergences"])
            self.assertEqual(5, diagnostic["totals"]["source_analysis_workers_completed"])
            self.assertEqual(0, diagnostic["totals"]["duplicate_source_reads"])
            self.assertEqual(5, diagnostic["totals"]["traceable_assertions"])
            self.assertEqual(0, diagnostic["totals"]["hidden_subtest_warnings"])
            self.assertEqual(0, diagnostic["totals"]["new_tcs_appended"])
            self.assertEqual(0, result["additive_feedback"]["pending_additive_follow_up"])
            self.assertEqual(
                "AUTOMATION_EXECUTION_NOT_READY",
                result["automation_audits"][2]["classification"],
            )
            self.assertNotIn("subtests", json.dumps(result["cases"]))
            self.assertEqual(5, diagnostic["totals"]["scenario_candidates_before_merge"])
            self.assertEqual(2, diagnostic["totals"]["scenario_merges_applied"])
            self.assertEqual(3, diagnostic["totals"]["scenarios_after_merge"])
            self.assertEqual(0, diagnostic["scope_proof"]["files_opened_outside_scope"])
            self.assertEqual(3, diagnostic["totals"]["source_items"])
            self.assertEqual(5, diagnostic["totals"]["atomic_source_claims_identified"])
            self.assertEqual(1, diagnostic["totals"]["compound_source_items_split"])
            self.assertEqual(1, diagnostic["totals"]["compound_claims_reviewed"])
            self.assertEqual(1, diagnostic["totals"]["compound_claims_split"])
            self.assertEqual(0, diagnostic["totals"]["compound_claims_kept_atomic"])
            self.assertEqual(5, diagnostic["totals"]["normative_clauses_extracted"])
            self.assertEqual(5, diagnostic["totals"]["coverage_points"])
            self.assertEqual(0, diagnostic["totals"]["possible_compound_claim_warnings"])
            self.assertEqual(
                ["CP-001", "CP-002", "CP-003"],
                result["cases"][0]["coverage_point_refs"],
            )
            self.assertEqual(
                {
                    "FUNCTIONAL_AUTHORITY",
                    "TECHNICAL_CONTEXT",
                    "IMPLEMENTATION_EVIDENCE",
                    "OTHER_SELECTED",
                    "TEST_ASSET",
                },
                set(result["source_analysis"]["evidence_records_by_role"]),
            )


if __name__ == "__main__":
    unittest.main()
