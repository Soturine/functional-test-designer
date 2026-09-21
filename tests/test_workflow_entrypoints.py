from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generation_orchestrator import GenerationContractError  # noqa: E402
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
        "source_first_claims": [{
            "requirement_ref": "REQ-001", "normalized_claim": "Refresh updates the counter."
        }],
        "evidence_manifest": ["requirements.md"],
        "selected_evidence": [{
            "source_role": "FUNCTIONAL_AUTHORITY", "source_ref": source_ref,
            "meaningful_behavior": True,
        }],
        "opportunities": [{
            "id": "OPP-001", "source_role": "FUNCTIONAL_AUTHORITY", "source_ref": source_ref,
            "authority_status": "NORMATIVE", "disposition": "NEW_NORMATIVE_SCENARIO",
            "target_refs": ["SCN-001"],
        }],
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
            request["source_first_claims"].append({
                "requirement_ref": "REQ-001", "normalized_claim": "Refresh records an audit entry."
            })
            with self.assertRaisesRegex(GenerationContractError, "Source-first coverage gaps"):
                dispatch("ftd-gen", **request)

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
