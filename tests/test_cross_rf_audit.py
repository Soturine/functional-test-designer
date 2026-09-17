from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cross_rf_audit", ROOT / "scripts/cross_rf_audit.py")
assert spec and spec.loader
CROSS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CROSS)


def case(case_id: str, refs: list[str], data: str = "valid") -> dict:
    return {
        "id": case_id, "objective": "Verify processing.", "requirement_refs": refs,
        "preconditions": ["Record exists."],
        "test_data": [{"name": "value", "description": data}],
        "steps": [{"step": 1, "action": "Submit the record.", "expected_result": "The record is accepted."}],
        "postconditions": [], "coverage_point_refs": ["CP-001"], "status": "READY",
    }


class CrossRequirementAuditTests(unittest.TestCase):
    def test_multi_rf_case_is_counted_once_and_never_merged(self) -> None:
        result = CROSS.audit_cross_rf(
            [case("TC-001", ["REQ-001", "REQ-002"])],
            {"REQ-001": "RF001", "REQ-002": "RF002"},
        )
        self.assertEqual(1, len(result["same_multi_rf_coverage"]))
        self.assertEqual(0, result["automatic_merges"])
        self.assertEqual(0, result["automatic_removals"])

    def test_semantically_equal_cases_are_only_duplicate_candidates(self) -> None:
        result = CROSS.audit_cross_rf(
            [case("TC-001", ["REQ-001"]), case("TC-002", ["REQ-002"])],
            {"REQ-001": "RF001", "REQ-002": "RF002"},
        )
        self.assertEqual(1, result["duplicate_candidates"])
        self.assertEqual(2, len(["TC-001", "TC-002"]))

    def test_same_trigger_and_oracle_with_distinct_boundary_is_not_duplicate(self) -> None:
        result = CROSS.audit_cross_rf(
            [case("TC-001", ["REQ-001"], "minimum 1"), case("TC-002", ["REQ-002"], "maximum 10")],
            {"REQ-001": "RF001", "REQ-002": "RF002"},
        )
        self.assertEqual(0, result["duplicate_candidates"])
        self.assertEqual(1, result["similar_but_distinct"])


if __name__ == "__main__":
    unittest.main()
