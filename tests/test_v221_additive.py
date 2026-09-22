from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from additive_expansion import (  # noqa: E402
    apply_test_data_reachability, audit_baseline_preservation,
    audit_semantic_composition, calibrate_priority, priority_metrics,
    snapshot_normative_baseline,
)
from cross_source_contradictions import audit_contradictions  # noqa: E402
from execution_quality import procedure_template_metrics  # noqa: E402
from reference_integrity import audit_evidence_references  # noqa: E402
from requirement_groups import requirement_group_label  # noqa: E402
from risk_expansion import expand_risk_profiles  # noqa: E402
from run_state import RunStateStore  # noqa: E402
from scenario_independence import build_scenario_family_pipeline  # noqa: E402
from source_inventory import (  # noqa: E402
    SourceInventoryError, audit_normative_source_units, audit_source_inventory,
    audit_use_case_flow_accounting,
)
from test_asset_inventory import (  # noqa: E402
    TestAssetInventoryError, audit_test_asset_inventory,
)
from workflow_entrypoints import dispatch  # noqa: E402
from tests.test_workflow_entrypoints import generation_request  # noqa: E402


def cp(number: int, requirement: str = "REQ-001") -> dict:
    return {
        "id": f"CP-{number:03d}", "requirement_ref": requirement,
        "statement": f"Behavior {number}", "clause_refs": [f"CLAUSE-{number:03d}"],
        "source_refs": [{"source": "requirements.md", "reference": f"RF-{number}"}],
        "disposition": "TEST_CASE", "target_refs": [],
    }


def profile(title: str, oracle: str, **extra: object) -> dict:
    value = {
        "title": title, "behavior": title, "scenario_family": "Orders",
        "test_basis": "ACCEPTANCE", "primary_type": "FUNCTIONAL",
        "normative_oracle": oracle, "assertion_oracle": oracle,
        "actor": "operator", "state": "draft", "setup": "order exists",
        "trigger": title, "event": title, "execution_boundary": title,
        "objective": title, "input_partition": title,
    }
    value.update(extra)
    return value


class AdditiveBaselineTests(unittest.TestCase):
    def test_expansion_preserves_normative_ids_and_oracles(self) -> None:
        baseline = build_scenario_family_pipeline(
            [cp(1), cp(2)], {"CP-001": profile("A", "A happens"), "CP-002": profile("B", "B happens")}
        )
        final = build_scenario_family_pipeline(
            [cp(1), cp(2)], {
                "CP-001": [profile("A", "A happens"), profile(
                    "A under concurrency", "A remains unique", test_basis="DERIVED",
                    primary_type="CONCURRENCY", expansion_layer="ADDITIVE",
                )],
                "CP-002": profile("B", "B happens"),
            },
        )
        metrics = audit_baseline_preservation(snapshot_normative_baseline(baseline), final)
        self.assertTrue(metrics["baseline_preserved"])
        self.assertEqual(["TC-001", "TC-002"], [i.id for i in final["test_identities"][:2]])

    def test_removed_normative_test_fails_gate(self) -> None:
        design = build_scenario_family_pipeline([cp(1)], {"CP-001": profile("A", "A happens")})
        baseline = snapshot_normative_baseline(design)
        design["test_identities"] = []
        with self.assertRaisesRegex(ValueError, "baseline changed"):
            audit_baseline_preservation(baseline, design)

    def test_changed_normative_oracle_fails_gate(self) -> None:
        design = build_scenario_family_pipeline([cp(1)], {"CP-001": profile("A", "A happens")})
        baseline = snapshot_normative_baseline(design)
        design["test_identities"][0] = replace(design["test_identities"][0], normative_oracle="Observed B")
        with self.assertRaisesRegex(ValueError, "changed"):
            audit_baseline_preservation(baseline, design)

    def test_scenario_family_regrouping_does_not_change_identity(self) -> None:
        left = build_scenario_family_pipeline([cp(1)], {"CP-001": profile("A", "A happens", scenario_family="One")})
        right = build_scenario_family_pipeline([cp(1)], {"CP-001": profile("A", "A happens", scenario_family="Refined")})
        self.assertEqual(left["test_identities"][0].id, right["test_identities"][0].id)
        self.assertEqual(left["test_identities"][0].normative_oracle, right["test_identities"][0].normative_oracle)

    def test_merge_candidate_has_id_and_never_removes_cases(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1), cp(2)], {"CP-001": profile("A", "A", event="submit"), "CP-002": profile("B", "B", event="submit")}
        )
        self.assertEqual(2, len(design["test_identities"]))
        self.assertEqual("MC-001", design["merge_candidates"][0]["merge_candidate_id"])
        self.assertEqual(0, design["metrics"]["actual_merges"])


class CompletenessAndExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = [{
            "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
            "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED", "reason": "approved",
        }]
        self.ref = [{"source": "requirements.md", "reference": "CU-1"}]

    def test_authority_file_requires_sub_file_normative_units(self) -> None:
        with self.assertRaisesRegex(SourceInventoryError, "no normative-unit inventory"):
            audit_normative_source_units(self.inventory, [])

    def test_normative_authority_cannot_masquerade_as_implementation_evidence(self) -> None:
        with self.assertRaisesRegex(SourceInventoryError, "FUNCTIONAL_AUTHORITY"):
            audit_source_inventory(
                [{"path": "requirements.md", "role": "IMPLEMENTATION_EVIDENCE"}],
                self.inventory,
            )

    def test_structural_index_prevents_silent_normative_unit_omission(self) -> None:
        units = [{
            "id": "NU-001", "path": "requirements.md", "family": "BUSINESS_RULE",
            "disposition": "EXTRACTED", "source_refs": self.ref,
        }]
        with self.assertRaisesRegex(SourceInventoryError, "differ from structural indexing"):
            audit_normative_source_units(self.inventory, units, [{
                "path": "requirements.md", "expected_unit_refs": ["NU-001", "NU-002"],
            }])

    def test_multiple_flows_from_one_use_case_are_accounted_independently(self) -> None:
        units = [{
            "id": "CU-001", "path": "requirements.md", "family": "USE_CASE",
            "disposition": "EXTRACTED", "source_refs": self.ref,
            "expected_flow_refs": ["FLOW-MAIN", "FLOW-ALT"],
        }]
        flows = [
            {"id": "FLOW-MAIN", "use_case_ref": "CU-001"},
            {"id": "FLOW-ALT", "use_case_ref": "CU-001"},
        ]
        result = audit_use_case_flow_accounting(units, flows)
        self.assertEqual(2, result["use_case_flows_extracted"])

    def test_alternative_flow_cannot_disappear_behind_main_flow(self) -> None:
        units = [{
            "id": "CU-001", "path": "requirements.md", "family": "USE_CASE",
            "disposition": "EXTRACTED", "source_refs": self.ref,
            "expected_flow_refs": ["FLOW-MAIN", "FLOW-ALT"],
        }]
        with self.assertRaisesRegex(SourceInventoryError, "missing=FLOW-ALT"):
            audit_use_case_flow_accounting(units, [{"id": "FLOW-MAIN", "use_case_ref": "CU-001"}])

    def test_operator_error_and_known_chaos_materialize_additively(self) -> None:
        base = {"CP-001": profile("Submit", "Submitted")}
        conditions = [
            {"id": "R-1", "risk_class": "OPERATOR_ERROR", "oracle_support": "NORMATIVE"},
            {"id": "R-2", "risk_class": "CHAOS", "oracle_support": "NORMATIVE"},
        ]
        candidates = [
            {"risk_condition_ref": "R-1", "coverage_point_ref": "CP-001", "profile": profile("Wrong resource", "Rejected")},
            {"risk_condition_ref": "R-2", "coverage_point_ref": "CP-001", "profile": profile("Restart", "No duplicate")},
        ]
        expanded, metrics = expand_risk_profiles(base, conditions, candidates, coverage_point_ids={"CP-001"})
        self.assertEqual(2, metrics["risk_candidates_materialized"])
        self.assertEqual(1, metrics["operator_error_tests"])
        self.assertEqual(1, metrics["chaos_tests"])
        self.assertEqual("NEGATIVE", expanded["CP-001"][1]["primary_type"])

    def test_unknown_recovery_policy_remains_exploratory(self) -> None:
        expanded, metrics = expand_risk_profiles(
            {"CP-001": profile("Submit", "Submitted")},
            [{"id": "R-1", "risk_class": "RECOVERY", "oracle_support": "UNDEFINED"}],
            [{"risk_condition_ref": "R-1", "coverage_point_ref": "CP-001", "profile": profile(
                "Response loss", "unused", normative_oracle=None, question_refs=["Q-001"]
            )}], coverage_point_ids={"CP-001"},
        )
        self.assertEqual("EXPLORATORY", expanded["CP-001"][1]["test_basis"])
        self.assertEqual(1, metrics["risk_candidates_exploratory"])


class ChallengeReferenceAndProcedureTests(unittest.TestCase):
    def test_cross_source_contradiction_requires_finding_or_explanation(self) -> None:
        refs = [
            {"source": "requirements.md", "reference": "RF-1"},
            {"source": "service.py", "reference": "constant"},
        ]
        result = audit_contradictions([{
            "id": "CONFLICT-1", "source_refs": refs,
            "disposition": "CONFIRMED_FINDING", "finding_ref": "FND-001",
        }], {"FND-001"}, set())
        self.assertEqual(1, result["contradictions_confirmed"])
        with self.assertRaisesRegex(ValueError, "valid Finding"):
            audit_contradictions([{
                "id": "CONFLICT-1", "source_refs": refs,
                "disposition": "CONFIRMED_FINDING", "finding_ref": "FND-999",
            }], {"FND-001"}, set())

    def test_business_test_asset_requires_targeted_challenge_disposition(self) -> None:
        discovered = [{"reference": "TestOrder::test_duplicate"}]
        with self.assertRaisesRegex(TestAssetInventoryError, "challenge-set disposition"):
            audit_test_asset_inventory(discovered, [{
                "reference": "TestOrder::test_duplicate", "classification": "BUSINESS_RELEVANT",
            }], strict_challenge=True)

    def test_business_test_asset_can_link_existing_atomic_case(self) -> None:
        result = audit_test_asset_inventory(
            [{"reference": "TestOrder::test_duplicate"}], [{
                "reference": "TestOrder::test_duplicate", "classification": "BUSINESS_RELEVANT",
                "disposition": "ALREADY_COVERED_BY", "target_refs": ["TC-001"],
            }], strict_challenge=True,
        )
        self.assertEqual(1, result["test_asset_already_covered"])

    def test_technical_only_asset_is_not_promoted_without_reason(self) -> None:
        with self.assertRaisesRegex(TestAssetInventoryError, "requires a reason"):
            audit_test_asset_inventory(
                [{"reference": "test_cache_key"}], [{
                    "reference": "test_cache_key", "classification": "TECHNICAL_ONLY",
                    "disposition": "TECHNICAL_ONLY",
                }], strict_challenge=True,
            )

    def test_finding_can_mark_fixture_unreachable_without_changing_oracle(self) -> None:
        cases = [{
            "id": "TC-001", "status": "READY", "execution_status": "READY",
            "finding_refs": [], "objective": "Submit valid identifier",
        }]
        result = apply_test_data_reachability(cases, {"TC-001": {
            "unreachable_under_observed_implementation": True,
            "blocking_finding_refs": ["FND-001"],
        }}, {"FND-001"})
        self.assertEqual("NEEDS_REVIEW", cases[0]["status"])
        self.assertEqual(["FND-001"], cases[0]["finding_refs"])
        self.assertEqual(1, result["test_data_unreachable_cases"])

    def test_reachability_audit_does_not_weaken_a_blocked_status(self) -> None:
        cases = [{
            "id": "TC-001", "status": "BLOCKED_REQUIREMENT",
            "execution_status": "BLOCKED_REQUIREMENT", "finding_refs": [],
        }]
        apply_test_data_reachability(cases, {"TC-001": {
            "unreachable_under_observed_implementation": True,
            "blocking_finding_refs": ["FND-001"],
        }}, {"FND-001"})
        self.assertEqual("BLOCKED_REQUIREMENT", cases[0]["status"])
        self.assertEqual("BLOCKED_REQUIREMENT", cases[0]["execution_status"])

    def test_invalid_evidence_path_fails_physical_reference_gate(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            with self.assertRaisesRegex(ValueError, "missing-path"):
                audit_evidence_references(root, [{"path": "missing.md", "role": "FUNCTIONAL_AUTHORITY"}], [
                    {"source": "missing.md", "reference": "RF-1"}
                ])

    def test_semantically_unrelated_e2e_composition_is_rejected(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "REQ-001"), cp(2, "REQ-999")], {
                "CP-001": profile("Atomic", "Done"),
                "CP-002": profile("Journey", "Journey done", test_basis="E2E", primary_type="E2E", composes=["TC-001"]),
            },
        )
        with self.assertRaisesRegex(ValueError, "unrelated-requirement"):
            audit_semantic_composition(design)

    def test_repeated_generic_procedure_templates_are_measured(self) -> None:
        cases = [{"objective": "A", "steps": [{"action": "Observe the result.", "expected_result": "Done"}]} for _ in range(4)]
        metrics = procedure_template_metrics(cases)
        self.assertEqual(1.0, metrics["repeated_action_template_ratio"])
        self.assertGreater(metrics["generic_setup_step_count"], 0)

    def test_distinct_natural_actions_are_not_normalized_into_one_template(self) -> None:
        cases = [
            {"objective": "Search", "steps": [{"action": "Search for the order.", "expected_result": "The order is shown."}]},
            {"objective": "Cancel", "steps": [{"action": "Cancel the reservation.", "expected_result": "The reservation is cancelled."}]},
        ]
        metrics = procedure_template_metrics(cases)
        self.assertEqual(1.0, metrics["unique_action_ratio"])

    def test_priority_flattening_is_visible_and_calibration_uses_impact(self) -> None:
        metrics = priority_metrics([{"priority": "MEDIUM"} for _ in range(10)])
        self.assertTrue(metrics["priority_flattening_warning"])
        self.assertEqual("CRITICAL", calibrate_priority({"impact_signals": ["cross-account leakage"]}))
        self.assertEqual("HIGH", calibrate_priority({"primary_type": "RECOVERY"}))


class PresentationAndRunStateTests(unittest.TestCase):
    def test_requirement_title_falls_back_to_utf8_statement(self) -> None:
        label = requirement_group_label({
            "id": "REQ-001", "statement": "Confirmação da operação",
            "source_refs": [{"source": "requirements.md", "reference": "RF001"}],
        })
        self.assertEqual("RF001 — Confirmação da operação", label)
        self.assertNotIn("Sem título", label)

    def test_superseded_run_cannot_resume_as_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            store = RunStateStore(Path(value), "run-001")
            store.save("VALIDATED", {"canonical_suite": "canonical-suite.json"}, {})
            store.mark_terminal("SUPERSEDED", "A later validated run was published")
            loaded = store.load({})
            self.assertFalse(loaded.reusable)
            self.assertEqual("RUN_SUPERSEDED", loaded.invalidation_reason)

    def test_publishing_a_run_supersedes_an_older_validated_run(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            older = RunStateStore(root, "run-old")
            current = RunStateStore(root, "run-current")
            older.save("VALIDATED", {"canonical_suite": "old.json"}, {})
            current.save("VALIDATED", {"canonical_suite": "current.json"}, {})
            self.assertEqual(
                ["run-old"], current.supersede_other_validated_runs("new canonical run")
            )
            self.assertEqual("SUPERSEDED", older.load({}).run_status)
            self.assertEqual("VALIDATED", current.load({}).run_status)

    def test_shared_runtime_materializes_additive_operator_error_after_frozen_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            request = generation_request(root, root / "artifacts")
            request["schema_version"] = "2.2"
            request["source_inventory"] = [{
                "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
                "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED",
                "reason": "Selected approved requirement.",
            }]
            request["risk_candidate_profiles"] = [{
                "risk_condition_ref": "RISK-001", "coverage_point_ref": "CP-001",
                "profile": profile(
                    "Repeat refresh", "The counter reflects one committed refresh event.",
                    scenario_family="Dashboard misuse", primary_type="NEGATIVE",
                    impact_signals=["data integrity"],
                    material_preconditions=["An operator is authenticated and the dashboard is open."],
                    observation_target="dashboard counter",
                ),
                "evidence_pack": {
                    "priority": "AUTO", "execution_surface": "dashboard",
                    "execution_surface_required": True,
                    "actions": [{
                        "action": "Select Refresh twice without changing the dashboard context.",
                        "expected_result": "The counter reflects one committed refresh event.",
                        "evidence_source": {"source": "requirements.md", "reference": "RF-001"},
                    }],
                    "test_data": [{"name": "counter", "description": "counter = 4"}],
                    "source_refs": [{"source": "requirements.md", "reference": "RF-001"}],
                    "preconditions": [], "postconditions": [], "cleanup": [],
                    "tags": ["operator-error", "misuse"],
                },
            }]
            request["expansion_opportunities"] = [{
                "id": "EXP-001", "risk_condition_ref": "RISK-001",
                "disposition": "MATERIALIZED_AS_TC",
            }]
            request["formats"] = ["JSON", "HTML", "DIAGNOSTICS"]
            result = dispatch("ftd-gen", **request)
            diagnostics = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            self.assertEqual(1, diagnostics["normative_atomic_before_expansion"])
            self.assertEqual(1, diagnostics["normative_atomic_after_expansion"])
            self.assertEqual(1, diagnostics["operator_error_tests"])
            self.assertTrue(diagnostics["baseline_preserved"])
            self.assertEqual(28, len(diagnostics["quality_gates"]))
            self.assertIsNone(diagnostics["source_analysis_time"])
            stages = {item["stage"]: item for item in diagnostics["full_run_provenance"]}
            self.assertEqual("COMPLETE", stages["ORCHESTRATOR_EXECUTION"]["status"])
            self.assertEqual("COMPLETE", stages["EXPANSION"]["status"])
            self.assertEqual("COMPLETE", stages["PROCEDURE_REFINEMENT"]["status"])
            self.assertEqual("COMPLETE", stages["VALIDATION"]["status"])
            self.assertEqual("COMPLETE", stages["RENDERING"]["status"])
            report = (root / "artifacts" / "output" / "report.html").read_text(encoding="utf-8")
            self.assertIn("Operator Error", report)
            self.assertIn("Normative Baseline", report)


if __name__ == "__main__":
    unittest.main()
