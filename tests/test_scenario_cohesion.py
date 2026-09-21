from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scenario_independence import build_scenario_pipeline  # noqa: E402


def coverage(number: int) -> dict:
    return {
        "id": f"CP-{number:03d}",
        "requirement_ref": "REQ-001",
        "statement": f"Observation {number}",
        "source_refs": [{"source": "requirements.md", "reference": f"R1-{number}"}],
        "disposition": "TEST_CASE",
        "target_refs": [],
    }


def cohesive_profile(number: int, **overrides) -> dict:
    value = {
        "title": "Submit one order",
        "behavior": f"Observe effect {number}",
        "assertion_oracle": f"Effect {number} is observable.",
        "normative_oracle": "Submitting the order produces all required effects.",
        "scenario_type": "STATE_TRANSITION",
        "actor": "operator",
        "setup": "one draft order",
        "starting_state": "DRAFT",
        "material_preconditions": ["the order is editable"],
        "input_partition": "one valid order",
        "trigger": "submit",
        "transaction": "order submission",
        "environment": "web application",
        "reset_required": False,
        "objective": "submit the draft order once",
        "execution_boundary": "one independently rerunnable submission",
        "execution_family": "order-submission",
        "merge_reason": "SHARED_EXECUTION_OBSERVATIONS",
        "observation_from_same_execution": True,
        "requires_independent_rerun": False,
        "observation_target": f"effect-{number}",
    }
    value.update(overrides)
    return value


class ScenarioCohesionTests(unittest.TestCase):
    def test_multiple_assertions_share_one_execution_without_losing_cps(self) -> None:
        points = [coverage(number) for number in range(1, 5)]
        profiles = {
            point["id"]: cohesive_profile(number)
            for number, point in enumerate(points, 1)
        }

        result = build_scenario_pipeline(points, profiles)
        identity = result["test_identities"][0]

        self.assertEqual(4, result["metrics"]["scenario_candidates_before_merge"])
        self.assertEqual(3, result["metrics"]["scenario_cohesion_decisions"])
        self.assertEqual(1, result["metrics"]["scenarios_after_merge"])
        self.assertEqual(4, result["metrics"]["traceable_assertions"])
        self.assertEqual(tuple(point["id"] for point in points), identity.coverage_point_refs)
        self.assertEqual(4, len(identity.assertions))
        self.assertIn("CP-004: Effect 4 is observable.", identity.normative_oracle)
        trail = result["cohesion_audit_trail"]
        self.assertEqual(3, len(trail))
        self.assertEqual("COH-001", trail[0]["decision_id"])
        self.assertEqual("SCN-001", trail[0]["resulting_scenario"])
        self.assertTrue(trail[0]["observation_compatibility"])
        self.assertEqual(["CP-001", "CP-002", "CP-003", "CP-004"], trail[-1]["coverage_point_refs"])

    def test_three_independent_triggers_remain_three_test_cases(self) -> None:
        points = [coverage(number) for number in range(1, 4)]
        triggers = ("complete", "reverse", "cancel")
        profiles = {
            point["id"]: cohesive_profile(
                number,
                title=f"{trigger.title()} request",
                trigger=trigger,
                transaction=f"request {trigger}",
                execution_boundary=f"one {trigger} execution",
            )
            for number, (point, trigger) in enumerate(zip(points, triggers), 1)
        }

        result = build_scenario_pipeline(points, profiles)

        self.assertEqual(3, result["metrics"]["scenarios_after_merge"])
        self.assertEqual(0, result["metrics"]["scenario_cohesion_decisions"])

    def test_filter_dimensions_remain_separate_input_partitions(self) -> None:
        points = [coverage(number) for number in range(1, 4)]
        dimensions = ("type", "status", "period")
        profiles = {
            point["id"]: cohesive_profile(
                number,
                input_partition=f"filter by {dimension}",
                objective=f"apply the {dimension} filter",
                execution_boundary=f"one {dimension} filter application",
            )
            for number, (point, dimension) in enumerate(zip(points, dimensions), 1)
        }

        self.assertEqual(3, build_scenario_pipeline(points, profiles)["metrics"]["test_cases_generated"])

    def test_same_navigation_does_not_merge_different_branches(self) -> None:
        points = [coverage(1), coverage(2)]
        profiles = {
            "CP-001": cohesive_profile(1, trigger="confirm", transaction="confirmation"),
            "CP-002": cohesive_profile(2, trigger="cancel", transaction="cancellation"),
        }

        result = build_scenario_pipeline(points, profiles)

        self.assertEqual(2, result["metrics"]["test_cases_generated"])

    def test_negative_partitions_platforms_and_performance_windows_remain_separate(self) -> None:
        dimensions = (
            {"input_partition": "unauthenticated"},
            {"input_partition": "invalid value"},
            {"input_partition": "unknown identifier"},
            {"environment": "desktop", "input_partition": "valid desktop"},
            {"environment": "tablet", "input_partition": "valid tablet"},
            {"environment": "handheld", "input_partition": "valid handheld"},
            {"objective": "measure search within 2 seconds", "input_partition": "search timing"},
            {"objective": "measure sync within 5 seconds", "input_partition": "sync timing"},
            {"objective": "measure refresh within 10 seconds", "input_partition": "refresh timing"},
        )
        points = [coverage(number) for number in range(1, 10)]
        profiles = {
            point["id"]: cohesive_profile(number, **values)
            for number, (point, values) in enumerate(zip(points, dimensions), 1)
        }

        result = build_scenario_pipeline(points, profiles)

        self.assertEqual(9, result["metrics"]["test_cases_generated"])


if __name__ == "__main__":
    unittest.main()
