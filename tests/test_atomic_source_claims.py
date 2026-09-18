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

    def test_raw_source_items_are_reviewed_before_claims_are_materialized(self) -> None:
        source_items = json.loads(
            (ROOT / "benchmarks/source-atomicity/source-items.json").read_text(encoding="utf-8")
        )

        inventory = AUDIT.review_source_items(source_items)
        chain = AUDIT.materialize_atomic_coverage(inventory)
        audit = AUDIT.audit_atomic_chain(inventory, chain)

        claims_by_requirement = {}
        for claim in inventory["claims"]:
            claims_by_requirement.setdefault(claim["requirement_ref"], []).append(claim)
        self.assertEqual(
            {"REQ-001": 2, "REQ-002": 3, "REQ-003": 2, "REQ-004": 4,
             "REQ-005": 3, "REQ-006": 3, "REQ-007": 3, "REQ-008": 2,
             "REQ-009": 2, "REQ-010": 1},
            {key: len(value) for key, value in claims_by_requirement.items()},
        )
        self.assertEqual(25, inventory["atomic_source_claims_identified"])
        self.assertEqual(24, len(chain["normative_clauses"]))
        self.assertEqual(24, len(chain["coverage_points"]))
        self.assertEqual(1, chain["metrics"]["atomic_claims_deduplicated"])
        self.assertEqual(25, audit["source_claims_represented"])

    def test_suspicious_source_item_cannot_bypass_explicit_review(self) -> None:
        item = {
            "id": "SRC-001", "requirement_ref": "REQ-001",
            "source_text": "The system shows an alert and blocks confirmation.",
            "source_refs": [{"source": "requirements.md", "reference": "R1"}],
        }

        with self.assertRaisesRegex(ValueError, "explicit atomicity_review"):
            AUDIT.review_source_items([item])

    def test_compound_keep_atomic_requires_a_valid_semantic_reason(self) -> None:
        item = {
            "id": "SRC-001", "requirement_ref": "REQ-001",
            "source_text": "The system shows an alert and blocks confirmation.",
            "source_refs": [{"source": "requirements.md", "reference": "R1"}],
            "atomicity_review": {
                "decision": "KEEP_ATOMIC", "reason": "SAME_EVENT",
                "claims": [{"normalized_claim": "The system shows an alert and blocks confirmation."}],
            },
        }

        with self.assertRaisesRegex(ValueError, "forbidden KEEP_ATOMIC reason"):
            AUDIT.review_source_items([item])

    def test_inseparable_value_can_be_kept_with_an_explicit_reason(self) -> None:
        item = json.loads(
            (ROOT / "benchmarks/source-atomicity/source-items.json").read_text(encoding="utf-8")
        )[-1]

        inventory = AUDIT.review_source_items([item])

        self.assertEqual(1, inventory["atomic_source_claims_identified"])
        self.assertEqual("INSEPARABLE_VALUE", item["atomicity_review"]["reason"])

    def test_compound_detection_covers_effects_alternatives_dimensions_and_limits(self) -> None:
        items = json.loads(
            (ROOT / "benchmarks/source-atomicity/source-items.json").read_text(encoding="utf-8")
        )
        texts = {item["id"]: item["source_text"] for item in items}

        for item_id in ("SRC-A", "SRC-B", "SRC-C", "SRC-D", "SRC-E", "SRC-F", "SRC-G", "SRC-H"):
            with self.subTest(item=item_id):
                self.assertTrue(AUDIT.compound_signals(texts[item_id]))

    def test_semantic_equivalence_preserves_both_source_refs(self) -> None:
        items = json.loads(
            (ROOT / "benchmarks/source-atomicity/source-items.json").read_text(encoding="utf-8")
        )
        inventory = AUDIT.review_source_items([item for item in items if item["id"].startswith("SRC-I")])
        chain = AUDIT.materialize_atomic_coverage(inventory)

        self.assertEqual(1, len(chain["normative_clauses"]))
        self.assertEqual(2, len(chain["normative_clauses"][0]["source_refs"]))

    def test_atomic_chain_gate_rejects_a_missing_claim_destination(self) -> None:
        source_items = json.loads(
            (ROOT / "benchmarks/source-atomicity/source-items.json").read_text(encoding="utf-8")
        )[:1]
        inventory = AUDIT.review_source_items(source_items)
        chain = AUDIT.materialize_atomic_coverage(inventory)
        chain["claim_destinations"].pop("CLAIM-002")

        with self.assertRaisesRegex(ValueError, "Atomic claims disappeared"):
            AUDIT.audit_atomic_chain(inventory, chain)

    def test_split_cannot_leave_a_residual_compound_claim_unreviewed(self) -> None:
        item = {
            "id": "SRC-001", "requirement_ref": "REQ-001",
            "source_text": "The system shows an alert, blocks confirmation, and records an audit entry.",
            "source_refs": [{"source": "requirements.md", "reference": "R1"}],
            "atomicity_review": {
                "decision": "SPLIT",
                "claims": [
                    {"normalized_claim": "The system shows an alert and blocks confirmation."},
                    {"normalized_claim": "The system records an audit entry."},
                ],
            },
        }

        with self.assertRaisesRegex(ValueError, "remains compound after SPLIT"):
            AUDIT.review_source_items([item])

    def test_non_testable_claim_keeps_an_explicit_destination_without_a_coverage_point(self) -> None:
        item = {
            "id": "SRC-001", "requirement_ref": "REQ-001",
            "source_text": "The archival period is configurable.",
            "source_refs": [{"source": "requirements.md", "reference": "R1"}],
            "atomicity_review": {
                "decision": "KEEP_ATOMIC", "reason": "SINGLE_OBSERVABLE_OUTCOME",
                "claims": [{
                    "normalized_claim": "The archival period is configurable.",
                    "destination_type": "QUESTION", "destination_id": "Q-001",
                }],
            },
        }

        inventory = AUDIT.review_source_items([item])
        chain = AUDIT.materialize_atomic_coverage(inventory)

        self.assertEqual([], chain["coverage_points"])
        self.assertEqual("QUESTION", chain["normative_clauses"][0]["destination_type"])
        self.assertEqual(1, AUDIT.audit_atomic_chain(inventory, chain)["source_claims_represented"])


if __name__ == "__main__":
    unittest.main()
