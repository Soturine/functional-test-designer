"""Reproduce selected-source accounting and independent-review omissions.

Input consistency is not source coverage. A run must not pass merely because every
structured input it received was internally consistent; the selected-source
exploration itself needs evidence of completeness.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from source_accounting import (  # noqa: E402
    SourceAccountingError, audit_source_review_independence, build_source_ledger,
    read_telemetry,
)


def ledger_entry(path: str, **overrides: object) -> dict[str, object]:
    entry = {
        "source": path,
        "source_role": "FUNCTIONAL_AUTHORITY",
        "content_type": "text/markdown",
        "disposition": "INSPECTED_CONTENT",
        "inspection_method": "FULL_TEXT_READ",
        "evidence_records": 2,
        "source_behaviors": 2,
    }
    entry.update(overrides)
    return entry


def independent_review(**overrides: object) -> dict[str, object]:
    review = {
        "method": "SUBAGENT_INDEPENDENT",
        "anchoring_inputs_withheld": [
            "final_scenario_count", "final_test_case_count", "desired_suite_size",
        ],
        "structural_units": [
            {"id": "UNIT-001", "kind": "ACCEPTANCE_CRITERION", "source": "requirements.md",
             "reference": "RF-001#AC-1"},
            {"id": "UNIT-002", "kind": "ACCEPTANCE_CRITERION", "source": "requirements.md",
             "reference": "RF-001#AC-2"},
        ],
        "behaviors": [
            {"requirement_ref": "REQ-001", "normalized_claim": "Refresh updates the counter.",
             "structural_unit_ref": "UNIT-001"},
            {"requirement_ref": "REQ-001", "normalized_claim": "Refresh records an audit entry.",
             "structural_unit_ref": "UNIT-002"},
        ],
    }
    review.update(overrides)
    return review


class SourceLedgerTests(unittest.TestCase):
    def test_every_resolved_selected_source_needs_an_explicit_disposition(self) -> None:
        with self.assertRaisesRegex(SourceAccountingError, "no inspection disposition"):
            build_source_ledger(
                ["requirements.md", "service.py"],
                [ledger_entry("requirements.md")],
            )

    def test_ledger_cannot_invent_a_source_outside_the_resolved_scope(self) -> None:
        with self.assertRaisesRegex(SourceAccountingError, "outside the resolved selected scope"):
            build_source_ledger(
                ["requirements.md"],
                [ledger_entry("requirements.md"), ledger_entry("sibling.md")],
            )

    def test_uninspected_sources_require_a_reason(self) -> None:
        with self.assertRaisesRegex(SourceAccountingError, "requires a reason"):
            build_source_ledger(
                ["requirements.md", "diagram.png"],
                [
                    ledger_entry("requirements.md"),
                    ledger_entry("diagram.png", disposition="METADATA_ONLY",
                                 inspection_method="METADATA_ONLY", evidence_records=0,
                                 source_behaviors=0),
                ],
            )

    def test_accounted_sources_produce_privacy_safe_disposition_metrics(self) -> None:
        ledger = build_source_ledger(
            ["requirements.md", "diagram.png", "legacy.md"],
            [
                ledger_entry("requirements.md"),
                ledger_entry(
                    "diagram.png", disposition="UNSUPPORTED_BINARY", inspection_method="METADATA_ONLY",
                    reason="Binary image outside the supported text extraction set.",
                    evidence_records=0, source_behaviors=0,
                ),
                ledger_entry(
                    "legacy.md", disposition="DUPLICATE_EQUIVALENT_SOURCE",
                    inspection_method="FULL_TEXT_READ",
                    reason="Byte-equivalent restatement of requirements.md.",
                    evidence_records=0, source_behaviors=0,
                ),
            ],
        )
        self.assertEqual(3, ledger["metrics"]["resolved_selected_sources"])
        self.assertEqual(1, ledger["metrics"]["sources_inspected_content"])
        self.assertEqual(0, ledger["metrics"]["sources_unaccounted"])
        self.assertNotIn("source_text", str(ledger["metrics"]))


class ReadTelemetryTests(unittest.TestCase):
    def test_unavailable_telemetry_is_null_rather_than_a_fabricated_zero(self) -> None:
        telemetry = read_telemetry({})
        self.assertFalse(telemetry["source_read_telemetry_available"])
        self.assertIsNone(telemetry["source_reads"])
        self.assertIsNone(telemetry["source_rereads"])
        self.assertIsNone(telemetry["agent_reasoning_seconds"])

    def test_observed_telemetry_is_reported_as_measured(self) -> None:
        telemetry = read_telemetry({
            "source_read_telemetry": {"source_reads": 12, "source_rereads": 3, "max_concurrency": 4}
        })
        self.assertTrue(telemetry["source_read_telemetry_available"])
        self.assertEqual(12, telemetry["source_reads"])
        self.assertEqual(4, telemetry["source_max_concurrency"])


class IndependentSourceReviewTests(unittest.TestCase):
    def test_a_review_derived_from_the_primary_claims_is_not_independent(self) -> None:
        review = independent_review()
        for behavior in review["behaviors"]:
            behavior["derived_from_claim_id"] = "CLAIM-001"
        with self.assertRaisesRegex(SourceAccountingError, "derived from the primary"):
            audit_source_review_independence(review, primary_claim_count=2)

    def test_a_review_that_saw_the_target_suite_size_is_anchored(self) -> None:
        review = independent_review(anchoring_inputs_withheld=["desired_suite_size"])
        with self.assertRaisesRegex(SourceAccountingError, "anchoring"):
            audit_source_review_independence(review, primary_claim_count=2)

    def test_an_unsupported_review_method_is_rejected(self) -> None:
        review = independent_review(method="REFORMATTED_PRIMARY_CLAIMS")
        with self.assertRaisesRegex(SourceAccountingError, "review method"):
            audit_source_review_independence(review, primary_claim_count=2)

    def test_structural_units_cannot_silently_lose_their_child_behaviors(self) -> None:
        review = independent_review()
        review["behaviors"] = [review["behaviors"][0]]
        with self.assertRaisesRegex(SourceAccountingError, "UNIT-002"):
            audit_source_review_independence(review, primary_claim_count=2)

    def test_a_structural_unit_without_behavior_needs_an_explicit_reason(self) -> None:
        review = independent_review()
        review["behaviors"] = [review["behaviors"][0]]
        review["structural_units"][1]["no_behavior_reason"] = "Non-normative editorial note."
        audit = audit_source_review_independence(review, primary_claim_count=2)
        self.assertEqual(2, audit["structural_units_inventoried"])
        self.assertEqual(1, audit["structural_units_without_behavior"])

    def test_an_independent_review_reports_its_own_behavior_inventory(self) -> None:
        audit = audit_source_review_independence(independent_review(), primary_claim_count=2)
        self.assertEqual(2, audit["independent_review_source_behaviors"])
        self.assertEqual("SUBAGENT_INDEPENDENT", audit["independent_review_method"])
        self.assertEqual(
            [{"requirement_ref": "REQ-001", "normalized_claim": "Refresh updates the counter."},
             {"requirement_ref": "REQ-001", "normalized_claim": "Refresh records an audit entry."}],
            [{"requirement_ref": item["requirement_ref"],
              "normalized_claim": item["normalized_claim"]} for item in audit["source_first_claims"]],
        )


if __name__ == "__main__":
    unittest.main()
