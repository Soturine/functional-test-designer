from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from procedural_readiness import (  # noqa: E402
    align_public_status,
    audit_execution_readiness,
    automation_plan,
    classify_test_data,
)
from scenario_independence import (  # noqa: E402
    AssertionObservation,
    ExecutionSignature,
    TestIdentity,
)


def ready_identity(assertions: tuple[AssertionObservation, ...] | None = None) -> TestIdentity:
    observed = assertions or (
        AssertionObservation("CP-001", "REQ-001", "Status is Confirmed.", "status field"),
    )
    return TestIdentity(
        id="TC-001",
        title="Confirm a pending reservation",
        scenario_ref="SCN-001",
        scenario_type="STATE_TRANSITION",
        requirement_refs=("REQ-001",),
        coverage_point_refs=tuple(item.coverage_point_ref for item in observed),
        normative_source_refs=(("requirements.md", "RF001"),),
        normative_oracle="The status field shows Confirmed.",
        objective="Confirm one pending reservation",
        material_preconditions=("An Operator is authenticated and Reservations is open.",),
        test_data_partition="pending reservation with sufficient balance",
        assertions=observed,
        execution_signature=ExecutionSignature(
            actor_permission="operator",
            setup="pending reservation",
            starting_state="pending",
            preconditions=("authenticated",),
            input_partition="pending with balance >= 10",
            trigger="confirm",
            transaction_event="confirmation",
            environment_platform="web",
            reset_required=False,
            path_objective="confirm reservation",
            execution_boundary="one confirmation",
        ),
        execution_boundary="one confirmation",
    )


def ready_case() -> dict:
    return {
        "id": "TC-001",
        "status": "READY",
        "preconditions": ["An Operator is authenticated; Reservations is open; a Pending record exists."],
        "test_data": [
            {"description": "Select a Pending reservation with balance >= 10 and record its ID."},
            {"description": "quantity = 2"},
        ],
        "steps": [
            {"step": 1, "action": "Enter the recorded ID in Search.", "expected_result": "The Pending reservation appears in the results.", "needs_clarification": False},
            {"step": 2, "action": "Open the reservation and select Confirm.", "expected_result": "The status field shows Confirmed.", "needs_clarification": False},
        ],
        "cleanup": ["Return the reservation to the approved baseline when the environment supports reset."],
        "source_refs": [{"source": "operator-guide.md", "reference": "Confirm"}],
    }


class ProceduralReadinessTests(unittest.TestCase):
    def test_supported_multi_action_path_cannot_be_compressed_to_one_generic_step(self) -> None:
        case = ready_case()
        case["steps"] = [{
            "step": 1, "action": "Perform the complete workflow.",
            "expected_result": "The reservation is confirmed.", "needs_clarification": False,
        }]
        audit = audit_execution_readiness(
            case, execution_context={"known_path_actions": 4, "execution_surface": "operator UI"},
        )
        self.assertIn("PATH_COMPRESSION", audit["reason_codes"])
        self.assertEqual("NEEDS_REVIEW", align_public_status(case, audit)["status"])

    def test_legitimate_one_action_path_is_not_path_compression(self) -> None:
        case = ready_case()
        case["steps"] = [{
            "step": 1, "action": "Select Refresh.",
            "expected_result": "The counter is updated.", "needs_clarification": False,
        }]
        audit = audit_execution_readiness(
            case, execution_context={"known_path_actions": 1, "execution_surface": "dashboard"},
        )
        self.assertNotIn("PATH_COMPRESSION", audit["reason_codes"])

    def test_missing_surface_and_record_acquisition_block_novice_readiness(self) -> None:
        case = ready_case()
        case["test_data"] = [{"name": "record", "description": "<existing object>"}]
        audit = audit_execution_readiness(
            case,
            execution_context={
                "known_path_actions": len(case["steps"]),
                "execution_surface_required": True,
                "record_required": True,
            },
        )
        self.assertIn("MISSING_EXECUTION_SURFACE", audit["reason_codes"])
        self.assertIn("MISSING_RECORD_ACQUISITION_RULE", audit["reason_codes"])

    def test_novice_ready_fixture_passes_human_and_automation_gates(self) -> None:
        audit = audit_execution_readiness(ready_case(), ready_identity())

        self.assertEqual("HUMAN_EXECUTION_READY", audit["human_classification"])
        self.assertEqual("AUTOMATION_EXECUTION_READY", audit["automation_classification"])
        self.assertEqual([], audit["reason_codes"])

    def test_procedure_gap_is_not_disguised_as_an_executable_case(self) -> None:
        case = ready_case()
        case["status"] = "NEEDS_REVIEW"
        case["steps"] = [{
            "step": 1,
            "action": "Obtain the documented execution path from an authorized selected source.",
            "expected_result": "The status field shows Confirmed.",
            "needs_clarification": True,
        }]

        audit = audit_execution_readiness(case, ready_identity())

        self.assertIn("PROCEDURE_GAP", audit["reason_codes"])
        self.assertEqual("HUMAN_EXECUTION_NOT_READY", audit["human_classification"])
        self.assertEqual("AUTOMATION_EXECUTION_NOT_READY", audit["automation_classification"])
        self.assertNotIn("button", str(case).casefold())
        self.assertNotIn("endpoint", str(case).casefold())

    def test_abstract_action_and_expected_are_detected_by_semantic_family(self) -> None:
        case = ready_case()
        case["steps"] = [{
            "step": 1,
            "action": "Execute the action described in the objective.",
            "expected_result": "The step becomes available for continuation.",
            "needs_clarification": False,
        }]

        reasons = audit_execution_readiness(case, ready_identity())["reason_codes"]

        self.assertIn("ABSTRACT_TRIGGER", reasons)
        self.assertIn("ABSTRACT_OBSERVATION", reasons)

    def test_test_data_concreteness_rejects_internal_labels_and_accepts_rules(self) -> None:
        bad = classify_test_data([
            {"description": "valid_item"},
            {"description": "existing record"},
            {"description": "partition-001"},
        ])
        good = classify_test_data([
            {"description": "quantity = 2"},
            {"description": "available balance = 10"},
            {"description": "Select a Pending record with balance >= 10 and record its ID."},
        ])

        self.assertIn("PLACEHOLDER_TEST_DATA", bad["reasons"])
        self.assertEqual("READY", good["classification"])

    def test_indistinguishable_assertions_warn_without_splitting_the_case(self) -> None:
        assertions = (
            AssertionObservation("CP-001", "REQ-001", "State changes.", "final value"),
            AssertionObservation("CP-002", "REQ-001", "Balance changes.", "final value"),
        )
        case = ready_case()
        audit = audit_execution_readiness(case, ready_identity(assertions))

        self.assertIn("INSUFFICIENT_ASSERTION_DISCRIMINATION", audit["reason_codes"])
        self.assertEqual("TC-001", case["id"])
        self.assertEqual(2, len(assertions))

    def test_automation_plan_is_a_non_executing_translation_contract(self) -> None:
        plan = automation_plan(ready_case(), ready_identity())

        self.assertEqual("TC-001", plan["tc_id"])
        self.assertEqual("AUTOMATION_EXECUTION_READY", plan["classification"])
        self.assertNotIn("locator", str(plan).casefold())
        self.assertEqual(1, len(plan["assertions"]))


if __name__ == "__main__":
    unittest.main()
