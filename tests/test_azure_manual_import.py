"""Manual Azure DevOps import: natural Suite order, the Suite creation guide and local CSV files.
Nothing here contacts Azure."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export as az  # noqa: E402
from integrations import azure_manual_import as mi  # noqa: E402


def suite(name: str, kind: str, identifier: str | None = None, refs: list[str] | None = None) -> dict:
    return {"suite_name": name, "group": identifier or name, "kind": kind, "identifier": identifier,
            "test_case_refs": refs or [f"canonical:{name}-case"]}


class SuiteOrderTests(unittest.TestCase):
    def test_identifiers_order_naturally_for_any_scheme(self) -> None:
        ordered = sorted(["RF10", "RF2", "RF1", "REQ-10", "REQ-2", "UC003", "UC10"], key=az.natural_key)
        self.assertEqual(["REQ-2", "REQ-10", "RF1", "RF2", "RF10", "UC003", "UC10"], ordered)

    def test_requirements_then_use_cases_then_transversal_then_execution_views(self) -> None:
        suites = [
            suite("Load and concurrency", "EXECUTION_VIEW"), suite("End-to-end", "EXECUTION_VIEW"),
            suite("Transversal rules", "TRANSVERSAL"), suite("UC10 — Close", "USE_CASE", "UC10"),
            suite("UC2 — Open", "USE_CASE", "UC2"), suite("RF10 — Export", "FUNCTIONAL", "RF10"),
            suite("RF2 — Edit", "FUNCTIONAL", "RF2"), suite("RF1 — Create", "FUNCTIONAL", "RF1"),
            {**suite("Unassigned", "UNASSIGNED"), "group": None},
        ]
        ordered = az._display_ordered(suites)
        self.assertEqual(["RF1 — Create", "RF2 — Edit", "RF10 — Export", "UC2 — Open", "UC10 — Close",
                          "Transversal rules", "Load and concurrency", "End-to-end", "Unassigned"],
                         [s["suite_name"] for s in ordered])
        self.assertEqual({id(s) for s in suites}, {id(s) for s in ordered})  # same suites, members untouched

    def test_member_order_inside_a_suite_is_kept(self) -> None:
        refs = ["canonical:TC-009", "canonical:TC-002", "chaos:x:CH-001"]
        self.assertEqual(refs, az._display_ordered([suite("RF1", "FUNCTIONAL", "RF1", refs)])[0]["test_case_refs"])

    def test_the_guide_lists_the_display_order_and_its_reverse_with_clean_names(self) -> None:
        text = mi.suite_order_markdown([suite("RF1 — Create", "FUNCTIONAL", "RF1"), suite("RF2 — Edit", "FUNCTIONAL", "RF2"),
                                        suite("End-to-end", "EXECUTION_VIEW")])
        display, creation = text.split("## Manual creation order")
        self.assertIn("1. RF1 — Create\n2. RF2 — Edit\n3. End-to-end", display)
        self.assertIn("1. End-to-end\n2. RF2 — Edit\n3. RF1 — Create", creation)
        self.assertNotIn("01 -", text)


if __name__ == "__main__":
    unittest.main()
