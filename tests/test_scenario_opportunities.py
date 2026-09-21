from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scenario_opportunities import audit_scenario_opportunities  # noqa: E402


def evidence(role: str, reference: str) -> dict:
    return {
        "source_role": role,
        "source_ref": {"source": f"{role.casefold()}.md", "reference": reference},
        "meaningful_behavior": True,
    }


class ScenarioOpportunityTests(unittest.TestCase):
    def test_every_selected_behavior_requires_a_disposition(self) -> None:
        selected = [evidence("IMPLEMENTATION_EVIDENCE", "retry branch")]
        with self.assertRaisesRegex(ValueError, "disappeared"):
            audit_scenario_opportunities(selected, [])

    def test_implementation_branch_cannot_become_normative_without_support(self) -> None:
        selected = [evidence("IMPLEMENTATION_EVIDENCE", "retry branch")]
        opportunity = {**selected[0], "id": "OPP-001", "disposition": "NEW_NORMATIVE_SCENARIO"}
        with self.assertRaisesRegex(ValueError, "cannot create a normative"):
            audit_scenario_opportunities(selected, [opportunity])

    def test_divergence_links_finding_and_normative_scenario(self) -> None:
        selected = [evidence("IMPLEMENTATION_EVIDENCE", "observed state")]
        opportunity = {
            **selected[0], "id": "OPP-001", "authority_status": "DIVERGENCE",
            "disposition": "DIVERGENCE_SCENARIO", "target_refs": ["SCN-001"],
            "finding_refs": ["FND-001"],
        }
        result = audit_scenario_opportunities(
            selected, [opportunity], scenario_ids={"SCN-001"}, finding_ids={"FND-001"},
        )
        self.assertEqual(1, result["divergence_opportunities_linked"])

    def test_test_asset_is_accounted_without_becoming_authority(self) -> None:
        selected = [evidence("TEST_ASSET", "legacy invalid transition")]
        opportunity = {
            **selected[0], "id": "OPP-001", "authority_status": "IMPLEMENTATION_ONLY",
            "disposition": "IMPLEMENTATION_CHARACTERIZATION",
        }
        result = audit_scenario_opportunities(selected, [opportunity])
        self.assertEqual(1, result["test_asset_behaviors_accounted"])

    def test_continuous_cross_requirement_e2e_requires_multiple_cp_refs(self) -> None:
        selected = [evidence("FUNCTIONAL_AUTHORITY", "complete lifecycle")]
        opportunity = {
            **selected[0], "id": "OPP-001", "authority_status": "NORMATIVE",
            "disposition": "NEW_NORMATIVE_SCENARIO", "target_refs": ["SCN-010"],
            "cross_cutting": True, "continuous_execution": True,
            "coverage_point_refs": ["CP-001", "CP-004"],
        }
        result = audit_scenario_opportunities(selected, [opportunity], scenario_ids={"SCN-010"})
        self.assertEqual(1, result["cross_cutting_opportunities"])

    def test_negative_recovery_opportunity_can_be_question_when_oracle_is_missing(self) -> None:
        selected = [evidence("TECHNICAL_CONTEXT", "manual recovery")]
        opportunity = {
            **selected[0], "id": "OPP-001", "authority_status": "ORACLE_MISSING",
            "disposition": "QUESTION", "target_refs": ["Q-001"],
        }
        result = audit_scenario_opportunities(selected, [opportunity], question_ids={"Q-001"})
        self.assertEqual(1, result["opportunity_dispositions"]["QUESTION"])


if __name__ == "__main__":
    unittest.main()
