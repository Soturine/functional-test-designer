"""Setup acquisition and procedural provenance are part of executability."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from procedural_readiness import (  # noqa: E402
    align_public_status, audit_execution_readiness, classify_procedural_provenance,
    classify_setup_acquisition,
)


MANUAL_REF = {"source": "operations-manual.md", "reference": "SEC-2"}


def ready_case(**overrides: object) -> dict[str, object]:
    case = {
        "id": "TC-001",
        "status": "READY",
        "preconditions": ["An operator with transfer permission is authenticated."],
        "test_data": [{"name": "starting balance", "description": "balance = 40"}],
        "steps": [{
            "step": 1, "action": "Select Confirm transfer.",
            "expected_result": "The transfer is recorded.", "needs_clarification": False,
        }],
    }
    case.update(overrides)
    return case


def context(**overrides: object) -> dict[str, object]:
    value = {
        "known_path_actions": 1,
        "procedural_actions": [{"action": "Select Confirm transfer.", "evidence_source": MANUAL_REF}],
    }
    value.update(overrides)
    return value


class SetupAcquisitionTests(unittest.TestCase):
    def test_a_precondition_alone_is_not_an_acquisition_strategy(self) -> None:
        result = classify_setup_acquisition({})
        self.assertEqual("MISSING", result["classification"])
        self.assertIn("MISSING_SETUP_ACQUISITION", result["reasons"])

    def test_a_strategy_without_a_concrete_rule_is_not_ready(self) -> None:
        result = classify_setup_acquisition(
            {"setup": {"strategy": "REUSE_EXISTING_WITH_QUERY_RULE"}}
        )
        self.assertIn("MISSING_SETUP_ACQUISITION", result["reasons"])

    def test_a_query_rule_makes_an_existing_record_obtainable(self) -> None:
        result = classify_setup_acquisition({"setup": {
            "strategy": "REUSE_EXISTING_WITH_QUERY_RULE",
            "acquisition_rule": (
                "Select an existing record in state Pending with at least 2 available units "
                "and record its identifier before execution."
            ),
        }})
        self.assertEqual("READY", result["classification"])
        self.assertEqual("REUSE_EXISTING_WITH_QUERY_RULE", result["strategy"])

    def test_a_preseeded_environment_still_needs_provenance(self) -> None:
        result = classify_setup_acquisition({"setup": {"strategy": "PRESEEDED_ENVIRONMENT"}})
        self.assertIn("MISSING_SETUP_PROVENANCE", result["reasons"])

    def test_an_unobtainable_record_keeps_the_case_out_of_ready(self) -> None:
        case = ready_case()
        audit = audit_execution_readiness(case, None, context(setup_required=True))
        align_public_status(case, audit)
        self.assertEqual("NEEDS_REVIEW", case["status"])
        self.assertIn("MISSING_SETUP_ACQUISITION", audit["reason_codes"])
        self.assertEqual("AUTOMATION_EXECUTION_NOT_READY", audit["automation_classification"])


class ProceduralProvenanceTests(unittest.TestCase):
    def test_an_untraced_technical_action_is_refused(self) -> None:
        result = classify_procedural_provenance(
            {"procedural_actions": [{"action": "Call POST /internal/transfers."}]}
        )
        self.assertEqual(1, result["untraced_actions"])
        self.assertIn("MISSING_PROCEDURAL_PROVENANCE", result["reasons"])

    def test_procedural_evidence_refs_satisfy_provenance(self) -> None:
        result = classify_procedural_provenance(context())
        self.assertEqual("READY", result["classification"])
        self.assertEqual(0, result["untraced_actions"])

    def test_provenance_is_unknown_rather_than_failing_when_not_supplied(self) -> None:
        self.assertEqual("UNKNOWN", classify_procedural_provenance({})["classification"])

    def test_an_untraced_procedure_cannot_be_presented_as_ready(self) -> None:
        case = ready_case()
        audit = audit_execution_readiness(
            case, None, context(procedural_actions=[{"action": "Call POST /internal/transfers."}]),
        )
        align_public_status(case, audit)
        self.assertEqual("NEEDS_REVIEW", case["status"])
        self.assertIn("MISSING_PROCEDURAL_PROVENANCE", audit["reason_codes"])

    def test_a_fully_supported_case_stays_ready_on_both_axes(self) -> None:
        case = ready_case()
        audit = audit_execution_readiness(case, None, context(setup_required=True, setup={
            "strategy": "SETUP_BY_API",
            "acquisition_rule": "Create a pending transfer through the documented transfers endpoint.",
        }))
        align_public_status(case, audit)
        self.assertEqual("READY", case["status"])
        self.assertEqual("HUMAN_EXECUTION_READY", audit["human_classification"])
        self.assertEqual("READY", audit["setup"]["classification"])
        self.assertEqual("READY", audit["procedural_provenance"]["classification"])


if __name__ == "__main__":
    unittest.main()
