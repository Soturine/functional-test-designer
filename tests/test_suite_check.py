from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from suite_check import check_suite  # noqa: E402


class SuiteCheckTests(unittest.TestCase):
    def test_check_is_read_only_and_reports_procedural_gap(self) -> None:
        cases = [{"id": "TC-001", "status": "NEEDS_REVIEW", "preconditions": [], "test_data": [], "steps": []}]
        original = deepcopy(cases)
        result = check_suite(cases, focus="procedure")
        self.assertEqual(original, cases)
        self.assertFalse(result["suite_mutated"])
        self.assertEqual(0, result["source_reads"])
        self.assertIn("MISSING_TRIGGER", result["findings"][0]["reason_codes"])

    def test_cohesion_trail_is_returned_without_reduction(self) -> None:
        decision = {"decision_id": "COH-001", "candidate_refs": ["A", "B"], "resulting_scenario": "SCN-001"}
        result = check_suite([], focus="cohesion", cohesion_decisions=[decision])
        self.assertEqual([decision], result["cohesion_decisions"])


if __name__ == "__main__":
    unittest.main()
