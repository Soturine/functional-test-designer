from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("execution_quality", ROOT / "scripts/execution_quality.py")
assert spec and spec.loader
QUALITY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QUALITY)


class ExecutionQualityTests(unittest.TestCase):
    def test_natural_distribution_preserves_one_three_and_five_steps(self) -> None:
        cases = json.loads((ROOT / "benchmarks/step-granularity/cases.json").read_text(encoding="utf-8"))

        self.assertEqual({"1": 1, "3": 1, "5": 1}, QUALITY.step_distribution(cases)["step_count_histogram"])

    def test_multi_action_step_is_flagged_without_rewriting_it(self) -> None:
        action = "Open the item, select the state, enter the reason, then confirm the change."
        cases = [{"id": "TC-001", "steps": [{"step": 1, "action": action}]}]

        warnings = QUALITY.multi_action_step_warnings(cases)

        self.assertEqual(1, len(warnings))
        self.assertEqual(action, cases[0]["steps"][0]["action"])

    def test_simple_action_remains_one_step_without_inflation(self) -> None:
        cases = [{"id": "TC-001", "steps": [{"step": 1, "action": "Select Refresh."}]}]

        self.assertEqual({"1": 1}, QUALITY.step_distribution(cases)["step_count_histogram"])
        self.assertEqual([], QUALITY.multi_action_step_warnings(cases))


if __name__ == "__main__":
    unittest.main()
