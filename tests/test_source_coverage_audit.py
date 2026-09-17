from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_coverage_audit", ROOT / "scripts/source_coverage_audit.py")
assert spec and spec.loader
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


def claim(number: int, text: str) -> dict:
    return {"id": f"SRC-{number:03d}", "requirement_ref": "REQ-006", "normalized_claim": text}


def clause(number: int, text: str) -> dict:
    return {"id": f"CLAUSE-{number:03d}", "requirement_ref": "REQ-006", "normalized_claim": text}


class SourceCoverageAuditTests(unittest.TestCase):
    def test_compound_source_effects_remain_three_independent_claims(self) -> None:
        claims = [
            claim(1, "The system alerts the operator."),
            claim(2, "The system records a pending item."),
            claim(3, "The system writes an audit entry."),
        ]
        result = AUDIT.audit_source_claims(claims, [clause(i, item["normalized_claim"]) for i, item in enumerate(claims, 1)])

        self.assertEqual(3, result["source_claims_identified"])
        self.assertEqual(3, result["source_claims_represented"])
        self.assertEqual(0, result["source_coverage_gaps"])

    def test_source_first_audit_finds_gap_even_when_all_existing_clauses_are_mapped(self) -> None:
        fixture = (ROOT / "benchmarks/source-coverage/rf006-like.md").read_text(encoding="utf-8")
        effects = [line.split(". ", 1)[1].rstrip(";") for line in fixture.splitlines() if line[:1].isdigit()]
        claims = [claim(i, text) for i, text in enumerate(effects, 1)]
        clauses = [clause(i, item["normalized_claim"]) for i, item in enumerate(claims[:-1], 1)]

        result = AUDIT.audit_source_claims(claims, clauses)

        self.assertEqual(14, result["source_claims_identified"])
        self.assertEqual(13, result["source_claims_represented"])
        self.assertEqual([claims[-1]], AUDIT.recovery_candidates(result, clauses))

    def test_one_recovery_and_verification_pass_does_not_duplicate_existing_claims(self) -> None:
        claims = [claim(1, "Search by identifier."), claim(2, "Search by external reference.")]
        clauses = [clause(1, claims[0]["normalized_claim"])]
        initial = AUDIT.audit_source_claims(claims, clauses)
        recovered = AUDIT.recovery_candidates(initial, clauses)
        clauses.append(clause(2, recovered[0]["normalized_claim"]))

        verified = AUDIT.audit_source_claims(claims, clauses)

        self.assertEqual(0, verified["source_coverage_gaps"])
        self.assertEqual(2, len(clauses))


if __name__ == "__main__":
    unittest.main()
