from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("normative_applicability", ROOT / "scripts/normative_applicability.py")
assert spec and spec.loader
APPLICABILITY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(APPLICABILITY)


class NormativeApplicabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((ROOT / "benchmarks/applicable-rules/catalog.json").read_text(encoding="utf-8"))

    def test_explicit_rules_resolve_only_from_in_scope_catalog(self) -> None:
        result = APPLICABILITY.resolve_applicable_rules("RF002", ["RN001", "RN003"], self.catalog)

        self.assertEqual(2, result["referenced_rules_resolved_in_scope"])
        self.assertEqual(2, len(result["applicable_rule_claims"]))
        self.assertEqual([], result["unresolved_refs"])

    def test_out_of_scope_reference_is_recorded_without_loading_or_invention(self) -> None:
        result = APPLICABILITY.resolve_applicable_rules("RF002", ["RN999"], self.catalog)

        self.assertEqual(0, result["referenced_rules_resolved_in_scope"])
        self.assertEqual(["RN999"], result["unresolved_refs"])
        self.assertEqual([], result["applicable_rule_claims"])

    def test_equivalent_owner_and_rule_claim_keep_one_claim_with_both_sources(self) -> None:
        owner_claims = [
            {"normalized_claim": "Approved requests are accepted.", "semantic_key": "approved-request", "polarity": "allow"}
        ]

        result = APPLICABILITY.resolve_applicable_rules(
            "RF002", ["RN001"], self.catalog, owner_claims=owner_claims
        )

        self.assertEqual(1, len(result["combined_claims"]))
        self.assertEqual(["RF002", "RN001"], result["combined_claims"][0]["source_refs"])

    def test_conflicting_applicable_rules_produce_source_conflict(self) -> None:
        owner_claims = [
            {"normalized_claim": "Approved requests are accepted.", "semantic_key": "approved-request", "polarity": "allow"}
        ]
        result = APPLICABILITY.resolve_applicable_rules(
            "RF002", ["RN010"], self.catalog, owner_claims=owner_claims
        )

        self.assertEqual("SOURCE_CONFLICT", result["conflicts"][0]["type"])
        self.assertEqual(["RF002", "RN010"], result["conflicts"][0]["references"])
        self.assertEqual(2, len(result["combined_claims"]))


if __name__ == "__main__":
    unittest.main()
