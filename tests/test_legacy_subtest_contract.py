from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LegacySubtestContractTests(unittest.TestCase):
    def test_independent_legacy_subtests_normalize_to_three_cases(self) -> None:
        legacy = ["without authentication", "invalid identifier", "resource not found"]
        normalized = [{"id": f"TC-{number:03d}", "scenario": value} for number, value in enumerate(legacy, 1)]

        self.assertEqual(3, len(normalized))
        self.assertTrue(all("subtests" not in case for case in normalized))

    def test_sequential_legacy_subtests_normalize_to_three_steps(self) -> None:
        legacy = ["create order", "confirm created order", "inspect final status"]
        normalized = {
            "id": "TC-001",
            "steps": [{"step": number, "action": value} for number, value in enumerate(legacy, 1)],
        }

        self.assertEqual(1, len([normalized]))
        self.assertEqual(3, len(normalized["steps"]))
        self.assertNotIn("subtests", json.dumps(normalized))

    def test_output_schema_rejects_subtests(self) -> None:
        schema = json.loads((ROOT / "schemas" / "test-case.schema.json").read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("subtests", schema["properties"])


if __name__ == "__main__":
    unittest.main()
