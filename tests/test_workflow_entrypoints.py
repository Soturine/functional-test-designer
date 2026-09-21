from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generation_orchestrator import GenerationContractError  # noqa: E402
from risk_coverage import RiskCoverageError  # noqa: E402
from source_accounting import SourceAccountingError  # noqa: E402
from workflow_entrypoints import INTENTS, dispatch, dispatch_request, normalize_intent  # noqa: E402


def generation_request(root: Path, artifact: Path) -> dict:
    source = root / "requirements.md"
    source.write_text("Refreshing the dashboard updates the counter.", encoding="utf-8")
    source_ref = {"source": "requirements.md", "reference": "RF-001"}
    return {
        "workspace": root, "selectors": ["requirements.md"], "artifact_root": artifact,
        "run_id": "run-001", "formats": ["HTML", "DIAGNOSTICS"], "diagnostic": True,
        "sources": [{"path": "requirements.md", "role": "FUNCTIONAL_AUTHORITY"}],
        "requirements": [{
            "id": "REQ-001", "statement": "Refresh updates the counter.", "status": "TESTABLE",
            "source_refs": [source_ref],
        }],
        "source_items": [{
            "id": "SRC-001", "requirement_ref": "REQ-001",
            "source_text": "Refreshing the dashboard updates the counter.",
            "source_refs": [source_ref],
            "atomicity_review": {"decision": "KEEP_ATOMIC", "reason": "SINGLE_OBSERVABLE_OUTCOME", "claims": [{
                "normalized_claim": "Refresh updates the counter.",
                "coverage_statement": "The counter is updated.",
            }]},
        }],
        "source_ledger": [{
            "source": "requirements.md", "source_role": "FUNCTIONAL_AUTHORITY",
            "content_type": "text/markdown", "disposition": "INSPECTED_CONTENT",
            "inspection_method": "FULL_TEXT_READ", "evidence_records": 1, "source_behaviors": 1,
        }],
        "source_review": {
            "method": "SUBAGENT_INDEPENDENT",
            "anchoring_inputs_withheld": [
                "final_scenario_count", "final_test_case_count", "desired_suite_size",
            ],
            "structural_units": [{
                "id": "UNIT-001", "kind": "ACCEPTANCE_CRITERION",
                "source": "requirements.md", "reference": "RF-001",
            }],
            "behaviors": [{
                "requirement_ref": "REQ-001", "normalized_claim": "Refresh updates the counter.",
                "structural_unit_ref": "UNIT-001",
            }],
        },
        "evidence_manifest": ["requirements.md"],
        "selected_evidence": [{
            "source_role": "FUNCTIONAL_AUTHORITY", "source_ref": source_ref,
            "meaningful_behavior": True,
        }],
        "opportunities": [{
            "id": "OPP-001", "source_role": "FUNCTIONAL_AUTHORITY", "source_ref": source_ref,
            "authority_status": "NORMATIVE", "disposition": "NEW_NORMATIVE_SCENARIO",
            "target_refs": ["SCN-001"], "risk_condition_ref": "RISK-001",
            "normative_support_refs": [source_ref],
        }],
        "risk_conditions": [{
            "id": "RISK-001", "risk_class": "OPERATOR_ERROR", "dimension": "duplicate_replay",
            "condition_support_refs": [source_ref], "oracle_support": "NORMATIVE",
        }],
        "use_case_flows": [],
        "test_asset_inventory": {"discovered": [], "classifications": []},
        "scenario_profiles": {"CP-001": {
            "title": "Refresh the dashboard counter", "behavior": "Refresh counter",
            "scenario_type": "HAPPY_PATH", "normative_oracle": "The counter is updated.",
            "assertion_oracle": "The counter is updated.", "observation_target": "counter",
            "actor": "operator", "state": "dashboard open", "input_partition": "current counter",
            "trigger": "refresh", "execution_boundary": "one refresh action",
            "objective": "Refresh the dashboard counter.",
            "material_preconditions": ["An operator is authenticated and the dashboard is open."],
        }},
        "evidence_packs": {"TC-001": {
            "priority": "MEDIUM", "execution_surface": "dashboard", "execution_surface_required": True,
            "actions": [{
                "action": "Select Refresh.", "expected_result": "The counter is updated.",
                "evidence_source": source_ref,
            }],
            "test_data": [{"name": "starting counter", "description": "counter = 4"}],
            "source_refs": [source_ref], "preconditions": [], "postconditions": [],
            "cleanup": [], "tags": ["refresh"],
        }},
        "findings": [], "questions": [],
    }


class WorkflowEntrypointTests(unittest.TestCase):
    def test_all_host_wrappers_are_thin_and_share_canonical_intents(self) -> None:
        for intent in INTENTS:
            name = intent.removeprefix("ftd-")
            self.assertTrue((ROOT / "entrypoints" / f"{name}.md").is_file())
            for host in (".cursor", ".claude"):
                text = (ROOT / host / "commands" / f"{intent}.md").read_text(encoding="utf-8")
                self.assertIn("shared core", text)
                self.assertNotIn("Coverage Point", text)

    def test_generation_cannot_fall_back_to_a_free_form_handoff(self) -> None:
        with self.assertRaisesRegex(GenerationContractError, "structured shared-core inputs"):
            dispatch_request("Generate Test Cases from these files and give me only HTML.")

    def test_natural_generation_and_command_use_same_enforced_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            natural = dispatch_request(
                "Generate Test Cases from these files and give me only HTML.",
                **generation_request(root, root / "natural"),
            )
            command = dispatch_request(
                "/ftd-gen requirements.md only HTML",
                **generation_request(root, root / "command"),
            )
        self.assertEqual(
            natural["design"]["metrics"]["test_cases_generated"],
            command["design"]["metrics"]["test_cases_generated"],
        )
        self.assertEqual("ftd-gen", natural["intent"])

    def test_real_generation_initializes_diagnostics_and_persists_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = dispatch("ftd-gen", **generation_request(root, root / "artifacts"))
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            state = json.loads(
                (root / "artifacts" / ".ftd" / "runs" / "run-001" / "run-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual("scope_resolution", diagnostic["phases"][0]["name"])
            self.assertTrue(all(item["timing_available"] for item in diagnostic["phases"]))
            self.assertGreaterEqual(
                diagnostic["run_wall_clock_seconds"], diagnostic["attributed_stage_seconds"]
            )
            self.assertNotIn("claims", diagnostic)
            self.assertEqual("VALIDATED", state["checkpoint"])
            self.assertFalse(list(root.glob("build_*_suite.py")))

    def test_validated_checkpoint_resumes_without_repeating_semantic_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            dispatch("ftd-gen", **request)
            resumed = dispatch("ftd-gen", **request)
            diagnostic = json.loads(Path(resumed["diagnostics"]).read_text(encoding="utf-8"))
            self.assertTrue(resumed["resumed"])
            self.assertEqual("VALIDATED", diagnostic["resumed_from_checkpoint"])
            self.assertEqual(
                ["scope_resolution", "source_inventory", "rendering"],
                [item["name"] for item in diagnostic["phases"]],
            )
            self.assertIn("resumed", {item["event"] for item in diagnostic["checkpoint_events"]})

    def test_changed_selected_source_invalidates_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            dispatch("ftd-gen", **request)
            (root / "requirements.md").write_text(
                "Refreshing the dashboard updates the counter.\n", encoding="utf-8"
            )
            rerun = dispatch("ftd-gen", **request)
            diagnostic = json.loads(Path(rerun["diagnostics"]).read_text(encoding="utf-8"))
            events = diagnostic["checkpoint_events"]
            self.assertIn(
                {"checkpoint": "VALIDATED", "event": "invalidated", "reason": "SOURCE_HASH_CHANGED"},
                events,
            )

    def test_source_first_gap_blocks_scenario_design(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["source_review"]["structural_units"].append({
                "id": "UNIT-002", "kind": "ACCEPTANCE_CRITERION",
                "source": "requirements.md", "reference": "RF-001",
            })
            request["source_review"]["behaviors"].append({
                "requirement_ref": "REQ-001", "normalized_claim": "Refresh records an audit entry.",
                "structural_unit_ref": "UNIT-002",
            })
            with self.assertRaisesRegex(GenerationContractError, "Source-first coverage gaps"):
                dispatch("ftd-gen", **request)

    def test_generation_fails_closed_without_selected_source_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request.pop("source_ledger")
            with self.assertRaisesRegex(GenerationContractError, "source_ledger"):
                dispatch("ftd-gen", **request)

    def test_an_unaccounted_selected_source_blocks_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "legacy-notes.md").write_text("Legacy operator notes.", encoding="utf-8")
            request = generation_request(root, root / "artifacts")
            request["selectors"] = ["requirements.md", "legacy-notes.md"]
            request["evidence_manifest"] = ["legacy-notes.md", "requirements.md"]
            with self.assertRaisesRegex(SourceAccountingError, "no inspection disposition"):
                dispatch("ftd-gen", **request)

    def test_a_source_review_copied_from_primary_claims_blocks_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["source_review"]["behaviors"][0]["derived_from_claim_id"] = "CLAIM-001"
            with self.assertRaisesRegex(SourceAccountingError, "derived from the primary"):
                dispatch("ftd-gen", **request)

    def test_diagnostics_never_fabricate_a_zero_source_read_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = dispatch("ftd-gen", **generation_request(root, root / "artifacts"))
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            self.assertFalse(diagnostic["source_read_telemetry_available"])
            self.assertIsNone(diagnostic["source_reads"])
            self.assertIsNone(diagnostic["source_rereads"])
            self.assertEqual(1, diagnostic["resolved_selected_sources"])
            self.assertEqual(1, diagnostic["sources_inspected_content"])
            self.assertEqual(0, diagnostic["sources_unaccounted"])
            self.assertEqual(1, diagnostic["independent_review_source_behaviors"])
            self.assertEqual(0, diagnostic["source_behavior_gaps"])

    def test_observed_read_telemetry_is_reported_when_the_host_supplies_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["source_read_telemetry"] = {
                "source_reads": 9, "source_rereads": 2, "max_concurrency": 3,
            }
            result = dispatch("ftd-gen", **request)
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            self.assertTrue(diagnostic["source_read_telemetry_available"])
            self.assertEqual(9, diagnostic["source_reads"])
            self.assertEqual(3, diagnostic["source_max_concurrency"])

    def test_source_accounting_and_review_are_resumable_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = dispatch("ftd-gen", **generation_request(root, root / "artifacts"))
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            created = [
                item["checkpoint"] for item in diagnostic["checkpoint_events"]
                if item["event"] == "created"
            ]
            self.assertIn("SOURCE_ACCOUNTING_COMPLETE", created)
            self.assertIn("SOURCE_REVIEW_COMPLETE", created)

    def test_an_evidence_supported_risk_cannot_be_omitted_from_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["risk_conditions"].append({
                "id": "RISK-002", "risk_class": "RESILIENCE", "dimension": "integration",
                "condition_support_refs": [{"source": "requirements.md", "reference": "RF-001"}],
                "oracle_support": "NORMATIVE",
            })
            with self.assertRaisesRegex(RiskCoverageError, "no opportunity disposition"):
                dispatch("ftd-gen", **request)

    def test_an_invented_recovery_oracle_is_refused_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["risk_conditions"][0]["oracle_support"] = "UNDEFINED"
            with self.assertRaisesRegex(RiskCoverageError, "cannot .*normative scenario"):
                dispatch("ftd-gen", **request)

    def test_selected_test_assets_require_a_real_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "legacy_test_flow.py").write_text(
                "def test_rejects_duplicate():\n    assert True\n", encoding="utf-8"
            )
            request = generation_request(root, root / "artifacts")
            request["selectors"] = ["requirements.md", "legacy_test_flow.py"]
            request["evidence_manifest"] = ["legacy_test_flow.py", "requirements.md"]
            request["source_ledger"].append({
                "source": "legacy_test_flow.py", "source_role": "TEST_ASSET",
                "content_type": "text/x-python", "disposition": "INSPECTED_CONTENT",
                "inspection_method": "STATIC_AST_DISCOVERY", "evidence_records": 0,
                "source_behaviors": 0, "test_asset_behaviors": 1,
            })
            with self.assertRaisesRegex(GenerationContractError, "require a real inventory"):
                dispatch("ftd-gen", **request)

    def test_risk_and_flow_review_metrics_reach_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = dispatch("ftd-gen", **generation_request(root, root / "artifacts"))
            diagnostic = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            self.assertEqual(1, diagnostic["risk_conditions_reviewed"])
            self.assertEqual(1, diagnostic["operator_error_opportunities"])
            self.assertEqual(0, diagnostic["unaccounted_risk_conditions"])
            self.assertEqual(0, diagnostic["unaccounted_use_case_flows"])
            self.assertEqual(0, diagnostic["test_asset_missing_dispositions"])
            created = [
                item["checkpoint"] for item in diagnostic["checkpoint_events"]
                if item["event"] == "created"
            ]
            self.assertIn("OPPORTUNITY_AUDIT_COMPLETE", created)

    def test_natural_language_is_primary_for_every_capability(self) -> None:
        examples = {
            "Ask me the important questions that are still ambiguous.": "ftd-clarify",
            "Audit whether the generated TCs are executable by someone who has never seen the product.": "ftd-check",
            "Render the last run as JSON and Markdown.": "ftd-render",
            "Prepare the last suite for Azure DevOps and show me the preview before writing anything.": "ftd-mcp",
        }
        for request, expected in examples.items():
            self.assertEqual(expected, normalize_intent(request))

    def test_slash_and_dollar_forms_are_only_aliases(self) -> None:
        for intent in INTENTS:
            self.assertEqual(intent, normalize_intent(f"/{intent}"))
            self.assertEqual(intent, normalize_intent(f"${intent}"))

    def test_mcp_entrypoint_falls_back_to_deterministic_preview(self) -> None:
        case = {
            "id": "TC-001", "title": "Create order", "priority": "HIGH", "status": "READY",
            "preconditions": [], "steps": [{"action": "Submit", "expected_result": "Created"}],
            "tags": [], "requirement_refs": ["REQ-001"], "coverage_point_refs": ["CP-001"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = dispatch(
                "ftd-mcp", cases=[case], mapping={}, project="Demo", plan="Regression",
                suite="Orders", artifact_root=Path(temporary), mcp_available=False,
            )
            self.assertEqual(1, len(result["create"]))
            self.assertEqual(3, len(result["fallback_exports"]))


if __name__ == "__main__":
    unittest.main()
