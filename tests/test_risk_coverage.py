"""Adversarial, resilience and E2E discovery stays evidence-grounded."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from risk_coverage import (  # noqa: E402
    RISK_DIMENSIONS, RiskCoverageError, audit_flow_coverage, audit_risk_matrix,
)


MANUAL_REF = {"source": "operations-manual.md", "reference": "SEC-4"}
AUTHORITY_REF = {"source": "requirements.md", "reference": "RF-002#AC-1"}


def risk_condition(**overrides: object) -> dict[str, object]:
    condition = {
        "id": "RISK-001",
        "risk_class": "OPERATOR_ERROR",
        "dimension": "object_identity",
        "condition_support_refs": [MANUAL_REF],
        "oracle_support": "NORMATIVE",
    }
    condition.update(overrides)
    return condition


def opportunity(**overrides: object) -> dict[str, object]:
    item = {
        "id": "OPP-101",
        "risk_condition_ref": "RISK-001",
        "disposition": "NEW_NORMATIVE_SCENARIO",
        "normative_support_refs": [AUTHORITY_REF],
        "target_refs": ["SCN-004"],
    }
    item.update(overrides)
    return item


class RiskMatrixTests(unittest.TestCase):
    def test_an_evidence_supported_risk_cannot_be_silently_dropped(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "no opportunity disposition"):
            audit_risk_matrix([risk_condition()], [])

    def test_a_risk_condition_needs_selected_evidence_behind_the_condition(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "not supported by the selected evidence"):
            audit_risk_matrix([risk_condition(condition_support_refs=[])], [opportunity()])

    def test_an_undefined_expected_behavior_cannot_become_a_normative_scenario(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "cannot .*become a normative scenario"):
            audit_risk_matrix(
                [risk_condition(risk_class="RESILIENCE", dimension="integration",
                                oracle_support="UNDEFINED")],
                [opportunity()],
            )

    def test_an_undefined_expected_behavior_requires_a_focused_question(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "focused Question"):
            audit_risk_matrix(
                [risk_condition(oracle_support="UNDEFINED")],
                [opportunity(disposition="IMPLEMENTATION_CHARACTERIZATION",
                             normative_support_refs=[], target_refs=[])],
                question_ids={"Q-001"},
            )

    def test_a_characterization_candidate_with_a_question_is_accepted(self) -> None:
        metrics = audit_risk_matrix(
            [risk_condition(risk_class="RECOVERY", dimension="interruption_recovery",
                            oracle_support="UNDEFINED")],
            [opportunity(disposition="IMPLEMENTATION_CHARACTERIZATION",
                         normative_support_refs=[], target_refs=[], question_refs=["Q-001"])],
            question_ids={"Q-001"},
        )
        self.assertEqual(1, metrics["characterization_risk_candidates"])
        self.assertEqual(1, metrics["recovery_opportunities"])

    def test_a_normative_risk_scenario_needs_functional_authority_support(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "Functional Authority support"):
            audit_risk_matrix([risk_condition()], [opportunity(normative_support_refs=[])])

    def test_operator_and_infrastructure_risks_are_counted_separately(self) -> None:
        metrics = audit_risk_matrix(
            [
                risk_condition(),
                risk_condition(id="RISK-002", risk_class="RESILIENCE", dimension="integration"),
                risk_condition(id="RISK-003", risk_class="CONCURRENCY", dimension="concurrency"),
            ],
            [
                opportunity(),
                opportunity(id="OPP-102", risk_condition_ref="RISK-002"),
                opportunity(id="OPP-103", risk_condition_ref="RISK-003"),
            ],
        )
        self.assertEqual(1, metrics["adversarial_opportunities"])
        self.assertEqual(1, metrics["operator_error_opportunities"])
        self.assertEqual(1, metrics["resilience_opportunities"])
        self.assertEqual(1, metrics["concurrency_opportunities"])
        self.assertEqual(3, metrics["risk_dimensions_exercised"])
        self.assertEqual(0, metrics["unaccounted_risk_conditions"])

    def test_the_matrix_is_a_review_not_one_test_case_per_dimension(self) -> None:
        metrics = audit_risk_matrix([risk_condition()], [opportunity()])
        self.assertEqual(1, metrics["risk_conditions_reviewed"])
        self.assertLess(metrics["risk_dimensions_exercised"], len(RISK_DIMENSIONS))

    def test_an_opportunity_cannot_reference_an_unknown_risk(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "unknown risk conditions"):
            audit_risk_matrix([risk_condition()], [opportunity(), opportunity(
                id="OPP-199", risk_condition_ref="RISK-404")])


def flow(**overrides: object) -> dict[str, object]:
    item = {"id": "FLOW-001", "kind": "MAIN_FLOW", "source_refs": [AUTHORITY_REF]}
    item.update(overrides)
    return item


def flow_opportunity(**overrides: object) -> dict[str, object]:
    item = {
        "id": "OPP-201", "flow_ref": "FLOW-001", "flow_disposition": "E2E_SCENARIO",
        "continuous_execution": True, "coverage_point_refs": ["CP-001", "CP-002"],
    }
    item.update(overrides)
    return item


class FlowCoverageTests(unittest.TestCase):
    def test_a_documented_flow_cannot_be_skipped(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "no E2E review disposition"):
            audit_flow_coverage([flow()], [])

    def test_an_alternative_flow_is_reviewed_independently_of_the_main_flow(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "FLOW-002"):
            audit_flow_coverage(
                [flow(), flow(id="FLOW-002", kind="ALTERNATIVE_FLOW")],
                [flow_opportunity()],
            )

    def test_an_e2e_scenario_must_be_one_continuous_rerunnable_execution(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "continuous rerunnable execution"):
            audit_flow_coverage([flow()], [flow_opportunity(continuous_execution=False)])

    def test_an_e2e_scenario_traces_checkpoints_to_atomic_coverage_points(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "at least two Coverage Points"):
            audit_flow_coverage([flow()], [flow_opportunity(coverage_point_refs=["CP-001"])])

    def test_a_flow_already_covered_by_atomic_scenarios_needs_no_duplicate_e2e(self) -> None:
        metrics = audit_flow_coverage(
            [flow(), flow(id="FLOW-002", kind="ALTERNATIVE_FLOW"),
             flow(id="FLOW-003", kind="EXCEPTION_FLOW")],
            [
                flow_opportunity(),
                flow_opportunity(id="OPP-202", flow_ref="FLOW-002",
                                 flow_disposition="COVERED_BY_ATOMIC_SCENARIOS"),
                flow_opportunity(id="OPP-203", flow_ref="FLOW-003",
                                 flow_disposition="NOT_TESTABLE",
                                 reason="The documented trigger has no observable surface."),
            ],
        )
        self.assertEqual(3, metrics["use_case_flows_reviewed"])
        self.assertEqual(1, metrics["alternative_flows_reviewed"])
        self.assertEqual(1, metrics["exception_flows_reviewed"])
        self.assertEqual(1, metrics["e2e_scenarios_promoted"])

    def test_a_non_testable_flow_requires_a_reason(self) -> None:
        with self.assertRaisesRegex(RiskCoverageError, "requires a reason"):
            audit_flow_coverage([flow()], [flow_opportunity(flow_disposition="NOT_TESTABLE")])


if __name__ == "__main__":
    unittest.main()
