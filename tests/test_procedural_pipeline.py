from __future__ import annotations

import dataclasses
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import procedural_pipeline as pipeline  # noqa: E402
from parallel_evidence import EvidenceRecord  # noqa: E402
from procedural_pipeline import (  # noqa: E402
    automation_execution_audit,
    operator_actions_from_evidence,
    procedural_worker,
    reconcile_additive_feedback,
    run_procedural_tasks,
)
from scenario_independence import AssertionObservation, TestIdentity  # noqa: E402


def identity(tc_id: str = "TC-001", scenario: str = "SCN-001") -> TestIdentity:
    return TestIdentity(
        id=tc_id,
        title="Confirm an order",
        scenario_ref=scenario,
        scenario_type="STATE_TRANSITION",
        requirement_refs=("REQ-001",),
        coverage_point_refs=("CP-001",),
        normative_source_refs=(("requirements.md", "RF001"),),
        normative_oracle="The order state is CONFIRMED.",
        objective="Confirm one eligible order",
        material_preconditions=("An authenticated operator and an eligible order exist.",),
        test_data_partition="eligible order",
        assertions=(AssertionObservation(
            coverage_point_ref="CP-001",
            requirement_ref="REQ-001",
            oracle="The order state is CONFIRMED.",
            observation_target="order state",
        ),),
        execution_boundary="one confirmation transaction",
    )


def manual_record(*path: str) -> EvidenceRecord:
    return EvidenceRecord(
        source="operator-guide.md",
        source_role="TECHNICAL_CONTEXT",
        source_ref="Confirm an order",
        source_excerpt_ref="section 2",
        observation_or_claim="The operator follows the documented path.",
        navigation=path,
        visible_labels=path,
    )


def pack(**values) -> dict:
    return {
        "preconditions": ["An authenticated operator and an eligible order exist."],
        "test_data_partition": "eligible order",
        "test_data": [{"description": "<eligible order in the test environment>"}],
        "source_refs": [{"source": "operator-guide.md", "reference": "Confirm an order"}],
        **values,
    }


class ProceduralEvidenceTests(unittest.TestCase):
    def test_manual_path_generates_supported_ordered_actions(self) -> None:
        result = procedural_worker(
            identity(), pack(manual_evidence_records=[manual_record("Orders", "Pending", "Confirm")])
        )

        self.assertEqual("PROCEDURE_READY", result.result_type)
        self.assertEqual(["Open Orders.", "Select Pending.", "Select Confirm."], [
            step["action"] for step in result.case["steps"]
        ])
        self.assertEqual("The order state is CONFIRMED.", result.case["steps"][-1]["expected_result"])
        self.assertEqual("READY", result.case["status"])
        self.assertIn("operator-guide.md", {ref["source"] for ref in result.case["source_refs"]})

    def test_missing_path_preserves_test_identity_and_creates_question(self) -> None:
        result = procedural_worker(identity(), pack())

        self.assertEqual("PROCEDURE_GAP", result.result_type)
        self.assertEqual("NEEDS_REVIEW", result.case["status"])
        self.assertEqual(["CP-001"], result.case["coverage_point_refs"])
        self.assertEqual("The order state is CONFIRMED.", result.case["steps"][-1]["expected_result"])
        serialized = str(result.case).casefold()
        self.assertNotIn("button", serialized)
        self.assertNotIn("endpoint", serialized)
        self.assertIsNotNone(result.question)

    def test_conflicting_manual_paths_are_reported_as_ambiguity(self) -> None:
        result = procedural_worker(identity(), pack(manual_evidence_records=[
            manual_record("Orders", "Confirm"),
            manual_record("Admin", "Confirm"),
        ]))

        self.assertEqual("PROCEDURAL_AMBIGUITY", result.result_type)
        self.assertIsNotNone(result.question)

    def test_divergence_never_replaces_normative_oracle(self) -> None:
        result = procedural_worker(identity(), pack(
            manual_evidence_records=[manual_record("Orders", "Confirm")],
            divergence={"statement": "Implementation records REVIEWED instead."},
            source_refs=[
                {"source": "operator-guide.md", "reference": "Confirm an order"},
                {"source": "service.py", "reference": "confirm"},
            ],
        ))

        self.assertEqual("DIVERGENCE", result.result_type)
        self.assertEqual("The order state is CONFIRMED.", result.case["steps"][-1]["expected_result"])
        self.assertNotIn("REVIEWED", result.case["steps"][-1]["expected_result"])
        self.assertIsNotNone(result.finding)

    def test_hidden_subtest_is_returned_to_scenario_design(self) -> None:
        result = procedural_worker(identity(), pack(actions=[{
            "action": "Execute separately completion, reversal and cancellation.",
        }]))

        self.assertEqual("INDEPENDENT_BRANCH_DETECTED", result.result_type)
        self.assertIsNotNone(result.new_tc_candidate)
        self.assertEqual("NEEDS_REVIEW", result.case["status"])

    def test_one_execution_with_multiple_assertions_is_not_a_hidden_subtest(self) -> None:
        assertions = tuple(
            AssertionObservation(f"CP-{number:03d}", "REQ-001", f"Outcome {number}")
            for number in range(1, 5)
        )
        cohesive = dataclasses.replace(
            identity(),
            coverage_point_refs=tuple(item.coverage_point_ref for item in assertions),
            assertions=assertions,
            normative_oracle="All four observations match their normative outcomes.",
        )
        result = procedural_worker(cohesive, pack(actions=[{"action": "Confirm the order."}]))

        self.assertEqual("PROCEDURE_READY", result.result_type)
        self.assertEqual(1, len(result.case["steps"]))

    def test_frozen_preconditions_and_partition_cannot_be_changed(self) -> None:
        with self.assertRaisesRegex(ValueError, "frozen preconditions"):
            procedural_worker(identity(), pack(
                preconditions=["A different setup exists."],
                actions=[{"action": "Confirm the order."}],
            ))
        with self.assertRaisesRegex(ValueError, "test-data partition"):
            procedural_worker(identity(), pack(
                test_data_partition="ineligible order",
                actions=[{"action": "Confirm the order."}],
            ))

    def test_operator_actions_require_selected_visible_labels(self) -> None:
        incomplete = dataclasses.replace(
            manual_record("Orders", "Confirm"), visible_labels=("Orders",)
        )
        with self.assertRaisesRegex(ValueError, "visible label"):
            operator_actions_from_evidence([incomplete])


class ParallelProceduralTests(unittest.TestCase):
    def test_frozen_cases_are_enriched_concurrently_and_returned_in_input_order(self) -> None:
        identities = [identity(f"TC-{number:03d}", f"SCN-{number:03d}") for number in range(1, 4)]
        barrier = threading.Barrier(3)
        original = pipeline.procedural_worker

        def synchronized(item: TestIdentity, evidence: dict):
            barrier.wait(timeout=2)
            return original(item, evidence)

        with patch.object(pipeline, "procedural_worker", side_effect=synchronized):
            batch = run_procedural_tasks([
                (item, pack(actions=[{"action": "Confirm the order."}])) for item in identities
            ], max_workers=3)

        self.assertEqual([item.id for item in identities], [result.test_case_id for result in batch.results])
        self.assertEqual(3, batch.metrics["procedural_tasks_completed"])
        self.assertEqual(3, batch.metrics["procedural_max_concurrency"])


class AdditiveFeedbackTests(unittest.TestCase):
    def test_feedback_without_an_approved_candidate_cannot_reduce_suite(self) -> None:
        ready = procedural_worker(
            identity(), pack(actions=[{"action": "Confirm the order."}])
        )

        reconciled = reconcile_additive_feedback([ready.case], (ready,))

        self.assertEqual([ready.case], reconciled["test_cases"])
        self.assertEqual(0, reconciled["metrics"]["new_tcs_appended"])

    def test_late_authorized_branch_appends_without_changing_existing_case(self) -> None:
        original_result = procedural_worker(
            identity(), pack(actions=[{"action": "Confirm the order."}])
        )
        branch_result = dataclasses.replace(
            original_result,
            result_type="INDEPENDENT_BRANCH_DETECTED",
            new_tc_candidate={"authority_sufficient": True, "branch": "reject"},
        )

        def reviewer(candidate: dict, existing: set[str]):
            self.assertTrue(candidate["authority_sufficient"])
            self.assertEqual({"TC-001"}, existing)
            branch = dataclasses.replace(
                identity("TC-002", "SCN-002"),
                title="Reject an order",
                coverage_point_refs=("CP-002",),
                normative_oracle="The order state is REJECTED.",
                assertions=(AssertionObservation("CP-002", "REQ-001", "The order state is REJECTED."),),
            )
            return branch, pack(actions=[{"action": "Reject the order."}])

        reconciled = reconcile_additive_feedback(
            [original_result.case], (branch_result,), reviewer
        )

        self.assertEqual(["TC-001", "TC-002"], [case["id"] for case in reconciled["test_cases"]])
        self.assertEqual(original_result.case, reconciled["test_cases"][0])
        self.assertEqual(1, reconciled["metrics"]["new_tc_candidates"])
        self.assertEqual(1, reconciled["metrics"]["new_tcs_appended"])
        self.assertEqual(0, reconciled["metrics"]["pending_additive_follow_up"])

    def test_automation_audit_returns_objective_classification(self) -> None:
        result = procedural_worker(
            identity(), pack(
                actions=[{"action": "Confirm the order."}],
                test_data=[{"description": "2"}],
            )
        )
        audit = automation_execution_audit(result.case, identity())

        self.assertEqual("AUTOMATION_EXECUTION_READY", audit["classification"])
        self.assertEqual([], audit["reasons"])


if __name__ == "__main__":
    unittest.main()
