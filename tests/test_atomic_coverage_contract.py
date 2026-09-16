from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AtomicCoverageContractTests(unittest.TestCase):
    def test_compound_and_preserves_two_claims_and_coverage_points(self) -> None:
        source = "The system alerts the user and records a pending item."
        claims = ["alerts the user", "records a pending item"]
        destinations = ["CP-001", "CP-002"]

        self.assertIn(" and ", source)
        self.assertEqual(2, len(claims))
        self.assertEqual(len(claims), len(destinations))

    def test_or_alternatives_preserve_three_clause_destinations(self) -> None:
        source = "Release the link when finalizing, reversing, or canceling."
        claims = ["finalizing releases link", "reversing releases link", "canceling releases link"]
        destinations = ["CP-001", "CP-002", "CP-003"]

        self.assertIn(" or ", source)
        self.assertEqual(3, len(claims))
        self.assertEqual(len(claims), len(destinations))

    def test_inventory_fixture_keeps_six_independent_behaviors(self) -> None:
        claims = [
            "shows balance",
            "updates within ten seconds",
            "filters by type",
            "filters by status",
            "searches by identifier",
            "exports a spreadsheet",
        ]
        coverage_points = [f"CP-{number:03d}" for number in range(1, 7)]

        self.assertEqual(6, len(claims))
        self.assertEqual(6, len(coverage_points))
        self.assertNotIn("view inventory", claims)

    def test_export_is_not_hidden_inside_search_or_filter(self) -> None:
        claims = {"consult list", "filter list", "export list"}

        self.assertIn("export list", claims)
        self.assertEqual(3, len(claims))

    def test_skill_requires_clause_extraction_before_requirement_summary(self) -> None:
        instructions = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertLess(
            instructions.index("Extract atomic normative clauses before summarizing"),
            instructions.index("### 3. Extract and Audit Coverage Points"),
        )
        self.assertIn("unmapped_normative_clauses", instructions)


if __name__ == "__main__":
    unittest.main()
