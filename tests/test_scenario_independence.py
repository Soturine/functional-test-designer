from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

from run_independence_benchmark import run  # noqa: E402
from scenario_independence import (  # noqa: E402
    FORBIDDEN_MERGE_REASONS,
    audit_multi_cp_scenarios,
    candidate_from_coverage_point,
    merge_candidates,
    merge_reason,
)


class ScenarioIndependenceTests(unittest.TestCase):
    def test_generic_fixtures_a_through_j_pass(self) -> None:
        result = run(ROOT / "benchmarks" / "scenario-independence" / "fixture.json")

        self.assertEqual(list("ABCDEFGHIJ"), [item["fixture"] for item in result["fixtures"]])
        self.assertEqual(0, result["metrics"]["possible_scenario_overcompression_warnings"])
        self.assertGreater(result["metrics"]["scenario_candidates_before_merge"], result["metrics"]["scenarios_after_merge"])

    def test_every_atomic_cp_gets_a_candidate_before_merge(self) -> None:
        coverage_points = [
            {"id": f"CP-{number:03d}", "requirement_ref": "REQ-001", "source_refs": []}
            for number in range(1, 5)
        ]

        candidates = [candidate_from_coverage_point(cp, {"behavior": cp["id"]}) for cp in coverage_points]

        self.assertEqual(coverage_points.__len__(), len(candidates))
        self.assertEqual(
            {item["id"] for item in coverage_points},
            {item["coverage_point_refs"][0] for item in candidates},
        )

    def test_same_requirement_setup_actor_and_evidence_do_not_merge(self) -> None:
        shared = {
            "requirement_refs": ["REQ-001"],
            "actor": "operator",
            "setup": "same screen",
            "execution_evidence": "shared-pack",
        }
        left = {"id": "CAND-1", "coverage_point_refs": ["CP-001"], **shared, "behavior": "approve"}
        right = {"id": "CAND-2", "coverage_point_refs": ["CP-002"], **shared, "behavior": "cancel"}

        scenarios, decisions = merge_candidates([left, right])

        self.assertEqual(2, len(scenarios))
        self.assertEqual([], decisions)

    def test_different_partitions_do_not_merge_even_with_requested_reason(self) -> None:
        shared = {
            "actor": "operator",
            "setup": "form",
            "preconditions": ["form open"],
            "state": "OPEN",
            "trigger": "submit",
            "execution_evidence": "response",
            "reporting_purpose": "validation",
            "pass_fail_boundary": "submission",
            "continuous_execution": True,
            "nature": "negative",
            "can_fail_independently": False,
            "merge_key": "validation",
            "merge_reason": "SHARED_PASS_FAIL_BOUNDARY",
        }
        left = {"id": "CAND-1", "coverage_point_refs": ["CP-001"], **shared, "input_partition": "zero"}
        right = {"id": "CAND-2", "coverage_point_refs": ["CP-002"], **shared, "input_partition": "eleven"}

        self.assertIsNone(merge_reason(left, right))

    def test_inseparable_merge_preserves_cp_requirement_and_source_provenance(self) -> None:
        shared = {
            "actor": "operator", "setup": "pending", "preconditions": ["pending"],
            "state": "PENDING", "trigger": "confirm", "execution_evidence": "response",
            "reporting_purpose": "confirmation", "pass_fail_boundary": "atomic commit",
            "continuous_execution": True, "nature": "functional", "input_partition": "valid",
            "can_fail_independently": False, "merge_key": "confirmation",
            "merge_reason": "INSEPARABLE_SAME_EVENT",
        }
        left = {
            "id": "CAND-1", "coverage_point_refs": ["CP-001"],
            "requirement_refs": ["REQ-001"], "source_refs": [{"source": "a", "reference": "1"}],
            "behavior": "state changes", **shared,
        }
        right = {
            "id": "CAND-2", "coverage_point_refs": ["CP-002"],
            "requirement_refs": ["REQ-002"], "source_refs": [{"source": "b", "reference": "2"}],
            "behavior": "audit is written", **shared,
        }

        scenarios, decisions = merge_candidates([left, right])

        self.assertEqual(1, len(scenarios))
        self.assertEqual("INSEPARABLE_SAME_EVENT", decisions[0]["reason"])
        self.assertEqual(["CP-001", "CP-002"], scenarios[0]["coverage_point_refs"])
        self.assertEqual(["REQ-001", "REQ-002"], scenarios[0]["requirement_refs"])
        self.assertEqual(2, len(scenarios[0]["source_refs"]))

    def test_true_duplicate_dedup_preserves_both_sources(self) -> None:
        shared = {
            "actor": "operator", "setup": "draft", "preconditions": ["editable"],
            "state": "DRAFT", "trigger": "submit", "behavior": "submit draft",
            "input_partition": "valid", "oracle": "state is SUBMITTED",
            "expected_result": "State is SUBMITTED", "execution_evidence": "submit response",
            "reporting_purpose": "submission", "nature": "state-transition",
        }
        left = {
            "id": "CAND-1", "coverage_point_refs": ["CP-001"],
            "source_refs": [{"source": "requirements.md", "reference": "A"}], **shared,
        }
        right = {
            "id": "CAND-2", "coverage_point_refs": ["CP-002"],
            "source_refs": [{"source": "approved-spec.md", "reference": "B"}], **shared,
        }

        scenarios, decisions = merge_candidates([left, right])

        self.assertEqual("TRUE_SEMANTIC_DUPLICATE", decisions[0]["reason"])
        self.assertEqual(1, len(scenarios))
        self.assertEqual(2, len(scenarios[0]["source_refs"]))

    def test_dependent_steps_remain_one_scenario_without_becoming_candidates(self) -> None:
        import json

        benchmark = json.loads(
            (ROOT / "benchmarks" / "scenario-independence" / "fixture.json").read_text(encoding="utf-8")
        )
        fixture = next(item for item in benchmark["fixtures"] if item["id"] == "H")

        self.assertEqual(4, len(fixture["dependent_steps"]))
        self.assertEqual(1, len(fixture["profiles"]))
        self.assertEqual(1, fixture["expected_test_cases"])

    def test_unjustified_multi_cp_scenario_is_advisory_warning(self) -> None:
        warnings = audit_multi_cp_scenarios(
            [{"id": "SCN-001", "coverage_point_refs": ["CP-001", "CP-002"]}]
        )

        self.assertEqual("POSSIBLE_SCENARIO_OVERCOMPRESSION", warnings[0]["code"])

    def test_forbidden_reasons_are_never_accepted(self) -> None:
        for reason in FORBIDDEN_MERGE_REASONS:
            left = {
                "behavior": "approve", "merge_reason": reason, "merge_key": "x",
                "can_fail_independently": False,
            }
            right = {
                "behavior": "cancel", "merge_reason": reason, "merge_key": "x",
                "can_fail_independently": False,
            }
            self.assertIsNone(merge_reason(left, right), reason)


if __name__ == "__main__":
    unittest.main()
