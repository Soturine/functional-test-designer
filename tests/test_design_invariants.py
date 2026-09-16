from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "expected-output"


def read(relative: str) -> dict:
    return json.loads((OUTPUT / relative).read_text(encoding="utf-8"))


class DesignInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = read("test-cases.json")
        cls.cases = {
            entry["id"]: read(entry["file"])
            for entry in cls.index["test_cases"]
        }
        cls.coverage = {
            item["id"]: item for item in cls.index["coverage_points"]
        }

    def test_three_independent_conditions_are_three_test_cases(self) -> None:
        independent = [self.cases[tc_id] for tc_id in ("TC-004", "TC-005", "TC-008")]

        self.assertEqual(3, len({case["id"] for case in independent}))
        self.assertTrue(all(len(case["scenario_refs"]) == 1 for case in independent))
        self.assertTrue(all(len(case["steps"]) == 1 for case in independent))

    def test_sequential_flow_keeps_dependent_steps_together(self) -> None:
        case = self.cases["TC-001"]

        self.assertEqual(2, len(case["steps"]))
        self.assertIn("create-order", case["steps"][0]["action"])
        self.assertIn("created order", case["steps"][1]["action"])

    def test_boundaries_remain_independent(self) -> None:
        boundary_ids = ("TC-002", "TC-003", "TC-004", "TC-005")
        scenarios = {self.cases[tc_id]["scenario_refs"][0] for tc_id in boundary_ids}

        self.assertEqual(4, len(scenarios))

    def test_permissions_remain_independent(self) -> None:
        create_denied = self.cases["TC-008"]
        edit_denied = self.cases["TC-009"]

        self.assertNotEqual(create_denied["scenario_refs"], edit_denied["scenario_refs"])
        self.assertNotEqual(create_denied["steps"][0]["action"], edit_denied["steps"][0]["action"])

    def test_conjoined_observable_effects_have_atomic_coverage_points(self) -> None:
        creation_points = [
            item for item in self.coverage.values() if item["requirement_ref"] == "REQ-001"
        ]

        self.assertEqual(3, len(creation_points))
        self.assertTrue(any("visible order reference" in item["statement"] for item in creation_points))
        self.assertTrue(any("DRAFT state" in item["statement"] for item in creation_points))

    def test_explicit_boundary_alternatives_are_not_lost(self) -> None:
        self.assertEqual(["TC-004"], self.coverage["CP-006"]["target_refs"])
        self.assertEqual(["TC-005"], self.coverage["CP-008"]["target_refs"])

    def test_partial_oracle_preserves_known_behavior(self) -> None:
        self.assertEqual("TEST_CASE", self.coverage["CP-019"]["disposition"])
        self.assertEqual("TEST_CASE", self.coverage["CP-020"]["disposition"])
        self.assertEqual("QUESTION", self.coverage["CP-021"]["disposition"])

    def test_question_does_not_repeat_known_retry_result(self) -> None:
        questions = read("questions.json")["questions"]
        question = next(item for item in questions if item["id"] == "Q-002")

        self.assertNotIn("retry", question["question"].casefold())
        self.assertIn("state", question["question"].casefold())


if __name__ == "__main__":
    unittest.main()
