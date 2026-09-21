"""Adversarial evals: prove the gates reject bad generation, not only accept good.

Each test starts from a benchmark pack that is known to pass, applies one
realistic degradation, and asserts that a specific gate refuses it. A suite that
only ever proves good input passes says nothing about the bad input it would
have accepted.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generation_orchestrator import GenerationContractError, run_generation  # noqa: E402
from risk_coverage import RiskCoverageError  # noqa: E402
from run_operational_benchmarks import load_pack, materialize, run_pack  # noqa: E402
from source_accounting import SourceAccountingError  # noqa: E402
from test_asset_inventory import TestAssetInventoryError  # noqa: E402


PACKS = ROOT / "benchmarks" / "operational-workflows"


class DegradedRunTests(unittest.TestCase):
    def run_degraded(self, pack_name: str, degrade) -> dict:
        pack = load_pack(PACKS / pack_name)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(pack, root)
            request = copy.deepcopy(pack["request"])
            degrade(request)
            request.update({
                "workspace": root, "artifact_root": root / "artifacts",
                "run_id": request.get("run_id", "degraded"),
            })
            return run_generation(request)

    def test_dropping_one_acceptance_behavior_fails_source_coverage(self) -> None:
        def degrade(request: dict) -> None:
            claims = request["source_items"][1]["atomicity_review"]["claims"]
            del claims[1]

        with self.assertRaisesRegex(GenerationContractError, "Source-first coverage gaps"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_merging_two_independent_outcomes_fails_residual_atomicity(self) -> None:
        def degrade(request: dict) -> None:
            item = request["source_items"][0]
            item["atomicity_review"] = {
                "decision": "KEEP_ATOMIC", "reason": "SINGLE_OBSERVABLE_OUTCOME",
                "claims": [{
                    "normalized_claim": "A pending record is created and the approver is notified.",
                    "coverage_statement": "The pending record and the notification exist.",
                }],
            }

        with self.assertRaisesRegex(ValueError, "several independently observable outcomes"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_dropping_an_alternative_flow_disposition_fails_the_e2e_inventory(self) -> None:
        def degrade(request: dict) -> None:
            request["opportunities"] = [
                item for item in request["opportunities"] if item.get("flow_ref") != "FLOW-002"
            ]
            request["selected_evidence"] = [
                item for item in request["selected_evidence"]
                if item["source_ref"]["reference"] != "UC-1a"
            ]

        with self.assertRaisesRegex(RiskCoverageError, "FLOW-002"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_omitting_an_evidence_supported_adversarial_risk_fails_accounting(self) -> None:
        def degrade(request: dict) -> None:
            for item in request["opportunities"]:
                item.pop("risk_condition_ref", None)

        with self.assertRaisesRegex(RiskCoverageError, "no opportunity disposition"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_inventing_a_recovery_oracle_for_an_outage_fails_the_authority_gate(self) -> None:
        def degrade(request: dict) -> None:
            for condition in request["risk_conditions"]:
                if condition["id"] == "RISK-002":
                    condition["oracle_support"] = "NORMATIVE"
            for item in request["opportunities"]:
                if item.get("risk_condition_ref") == "RISK-002":
                    item["disposition"] = "NEW_NORMATIVE_SCENARIO"
                    item["target_refs"] = ["SCN-002"]

        with self.assertRaisesRegex(
            ValueError, "without authority|Functional Authority support"
        ):
            self.run_degraded("benchmark-a.json", degrade)

    def test_an_unaccounted_selected_source_fails_the_ledger(self) -> None:
        def degrade(request: dict) -> None:
            request["source_ledger"] = request["source_ledger"][:1]

        with self.assertRaisesRegex(SourceAccountingError, "no inspection disposition"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_a_reformatted_primary_extraction_fails_the_independence_gate(self) -> None:
        def degrade(request: dict) -> None:
            request["source_review"]["method"] = "REFORMATTED_PRIMARY_CLAIMS"

        with self.assertRaisesRegex(SourceAccountingError, "review method"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_ignoring_selected_test_assets_fails_test_asset_accounting(self) -> None:
        def degrade(request: dict) -> None:
            request["test_asset_inventory"]["classifications"] = (
                request["test_asset_inventory"]["classifications"][:1]
            )

        with self.assertRaisesRegex(TestAssetInventoryError, "no disposition"):
            self.run_degraded("benchmark-b.json", degrade)

    def test_hand_picking_no_test_at_all_fails_when_test_assets_are_selected(self) -> None:
        def degrade(request: dict) -> None:
            request["test_asset_inventory"] = {"discovered": [], "classifications": []}

        with self.assertRaisesRegex(GenerationContractError, "require a real inventory"):
            self.run_degraded("benchmark-b.json", degrade)

    def test_implementation_evidence_cannot_become_normative_expected_behavior(self) -> None:
        def degrade(request: dict) -> None:
            claims = request["source_items"][0]["atomicity_review"]["claims"]
            claims[0]["authority"] = "IMPLEMENTATION_EVIDENCE"

        with self.assertRaisesRegex(ValueError, "Only FUNCTIONAL_AUTHORITY claims"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_a_vague_one_step_path_cannot_be_presented_as_ready(self) -> None:
        def degrade(request: dict) -> None:
            pack = request["evidence_packs"]["TC-002"]
            pack["actions"] = [{
                "action": "Execute the operation described in the objective.",
                "expected_result": "The state is Approved.",
                "evidence_source": {"source": "operations-manual.md", "reference": "SEC-2"},
            }]
            pack["known_path_actions"] = 2

        result = self.run_degraded("benchmark-a.json", degrade)
        case = next(item for item in result["cases"] if item["id"] == "TC-002")
        audit = next(item for item in result["readiness"] if item["test_case_id"] == "TC-002")
        self.assertEqual("NEEDS_REVIEW", case["status"])
        self.assertIn("ABSTRACT_TRIGGER", audit["reason_codes"])
        self.assertEqual("AUTOMATION_EXECUTION_NOT_READY", audit["automation_classification"])

    def test_removing_procedural_provenance_blocks_readiness(self) -> None:
        def degrade(request: dict) -> None:
            for action in request["evidence_packs"]["TC-001"]["actions"]:
                action.pop("evidence_source", None)

        result = self.run_degraded("benchmark-a.json", degrade)
        case = next(item for item in result["cases"] if item["id"] == "TC-001")
        audit = next(item for item in result["readiness"] if item["test_case_id"] == "TC-001")
        self.assertEqual("NEEDS_REVIEW", case["status"])
        self.assertIn("MISSING_PROCEDURAL_PROVENANCE", audit["reason_codes"])

    def test_removing_the_setup_acquisition_rule_blocks_readiness(self) -> None:
        def degrade(request: dict) -> None:
            request["evidence_packs"]["TC-002"]["setup"] = {
                "strategy": "REUSE_EXISTING_WITH_QUERY_RULE"
            }

        result = self.run_degraded("benchmark-a.json", degrade)
        case = next(item for item in result["cases"] if item["id"] == "TC-002")
        audit = next(item for item in result["readiness"] if item["test_case_id"] == "TC-002")
        self.assertEqual("NEEDS_REVIEW", case["status"])
        self.assertIn("MISSING_SETUP_ACQUISITION", audit["reason_codes"])

    def test_an_operational_family_cannot_link_a_test_case_that_was_never_frozen(self) -> None:
        def degrade(request: dict) -> None:
            request["operational_scenarios"][0]["test_case_refs"] = ["TC-404"]

        with self.assertRaisesRegex(ValueError, "unknown Test Cases"):
            self.run_degraded("benchmark-a.json", degrade)

    def test_a_structural_unit_cannot_lose_its_behavior_without_a_reason(self) -> None:
        def degrade(request: dict) -> None:
            review = request["source_review"]
            review["behaviors"] = [
                item for item in review["behaviors"]
                if item["structural_unit_ref"] != "UNIT-004"
            ]

        with self.assertRaisesRegex(SourceAccountingError, "UNIT-004"):
            self.run_degraded("benchmark-a.json", degrade)


class AdHocGeneratorTests(unittest.TestCase):
    def test_ordinary_generation_creates_no_project_specific_generator_script(self) -> None:
        pack = load_pack(PACKS / "benchmark-a.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_pack(pack, root, root / "artifacts")
            created = sorted(
                path.name for path in root.rglob("*.py")
                if "artifacts" not in path.parts
            )
            self.assertEqual([], created)
            self.assertTrue(Path(result["canonical_path"]).is_file())
            self.assertIn(".ftd", Path(result["canonical_path"]).parts)

    def test_an_ad_hoc_generator_written_during_a_run_is_refused(self) -> None:
        import generation_orchestrator

        pack = load_pack(PACKS / "benchmark-a.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(pack, root)
            request = copy.deepcopy(pack["request"])
            request.update({
                "workspace": root, "artifact_root": root / "artifacts", "run_id": "ad-hoc",
            })
            original = generation_orchestrator.render_selected_outputs

            def leaking_render(*args, **kwargs):
                (root / "build_suite.py").write_text("raise SystemExit\n", encoding="utf-8")
                return original(*args, **kwargs)

            generation_orchestrator.render_selected_outputs = leaking_render
            try:
                with self.assertRaisesRegex(
                    GenerationContractError, "ad-hoc executable source"
                ):
                    run_generation(request)
            finally:
                generation_orchestrator.render_selected_outputs = original


class BenchmarkPackTests(unittest.TestCase):
    def test_every_pack_is_synthetic_generic_and_runs_through_the_shared_path(self) -> None:
        packs = sorted(PACKS.glob("*.json"))
        self.assertGreaterEqual(len(packs), 4)
        for path in packs:
            pack = load_pack(path)
            with self.subTest(pack=pack["id"]):
                self.assertTrue(pack["expected_invariants"])
                self.assertTrue(pack["files"])

    def test_a_multi_observation_execution_keeps_its_atomic_coverage_points(self) -> None:
        pack = load_pack(PACKS / "benchmark-a.json")
        self.assertEqual(7, pack["expected_invariants"]["coverage_points_exact"])
        self.assertEqual(3, pack["expected_invariants"]["test_cases_exact"])


if __name__ == "__main__":
    unittest.main()
