from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_coverage_audit", ROOT / "scripts/source_coverage_audit.py")
assert spec and spec.loader
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


class AtomicSourceClaimTests(unittest.TestCase):
    def test_compound_source_items_preserve_nine_independent_claims(self) -> None:
        source_items = json.loads((ROOT / "benchmarks/atomic-claims/source-items.json").read_text(encoding="utf-8"))

        inventory = AUDIT.atomic_claim_inventory(source_items)

        self.assertEqual(9, inventory["atomic_source_claims_identified"])
        self.assertEqual(3, inventory["compound_source_items_split"])

    def test_multiple_claims_can_map_to_one_test_case_without_losing_cps(self) -> None:
        claims = [
            {"requirement_ref": "REQ-001", "normalized_claim": f"Effect {number}."}
            for number in range(1, 4)
        ]
        clauses = [
            {**item, "id": f"CLAUSE-{number:03d}", "destination_id": f"CP-{number:03d}"}
            for number, item in enumerate(claims, 1)
        ]
        coverage = [
            {"id": f"CP-{number:03d}", "target_refs": ["TC-001"]}
            for number in range(1, 4)
        ]

        self.assertEqual(0, AUDIT.audit_source_claims(claims, clauses)["source_coverage_gaps"])
        self.assertEqual({"TC-001"}, {target for cp in coverage for target in cp["target_refs"]})

    def test_inseparable_representation_is_not_split_mechanically(self) -> None:
        inventory = AUDIT.atomic_claim_inventory(
            [{"source_item": "Show order number and description.", "atomic_claims": [
                {"requirement_ref": "REQ-001", "normalized_claim": "Show the order number and description."}
            ]}]
        )

        self.assertEqual(1, inventory["atomic_source_claims_identified"])
        self.assertEqual(0, inventory["compound_source_items_split"])

    def test_compound_warning_is_advisory_and_does_not_rewrite_claim(self) -> None:
        clause = {"id": "CLAUSE-001", "normalized_claim": "Show status and record history."}

        warnings = AUDIT.possible_compound_claims([clause])

        self.assertEqual("POSSIBLE_COMPOUND_NORMATIVE_CLAIM", warnings[0]["code"])
        self.assertEqual("Show status and record history.", clause["normalized_claim"])


if __name__ == "__main__":
    unittest.main()
