from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline_integrity import (  # noqa: E402
    PipelineIntegrityError, RunManifest, STAGE_SEQUENCE, apply_runtime_readiness,
    audit_atomic_coverage, audit_claim_exercise, audit_e2e_stage_mapping, audit_historical_baseline,
    audit_one_step_completeness, audit_priority_calibration,
    audit_scenario_family_linkage, audit_use_case_flow_exercise,
    build_identifier_ledger, build_physical_source_ledger,
    reject_request_owned_results, validate_run_manifest,
)
from test_asset_inventory import materialize_test_asset_challenge  # noqa: E402
from source_inventory import SourceInventoryError, audit_normative_source_units  # noqa: E402
from tests.test_workflow_entrypoints import generation_request  # noqa: E402
from workflow_entrypoints import dispatch  # noqa: E402


def acceptance(tc: str, cp: list[str]) -> dict:
    return {
        "id": tc, "test_basis": "ACCEPTANCE", "coverage_point_refs": cp,
        "steps": [{"action": "Submit the record.", "expected_result": "The record is accepted."}],
        "priority": "HIGH", "priority_reason": "Core business transaction.",
    }


class RuntimeOwnershipTests(unittest.TestCase):
    def test_request_cannot_assert_runtime_gate_results(self) -> None:
        with self.assertRaisesRegex(PipelineIntegrityError, "runtime-owned"):
            reject_request_owned_results({"quality_gates": []})

    def test_manifest_requires_the_exact_official_stage_chain(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "run-manifest.json"
            manifest = RunManifest(path, "run-1")
            now = "2026-01-01T00:00:00Z"
            with self.assertRaisesRegex(PipelineIntegrityError, "expected SOURCE_SELECTION"):
                manifest.record("CLAIM_EXTRACTION", inputs=[], outputs=[], started_at=now, finished_at=now)

    def test_manifest_detects_stage_record_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            canonical = root / "canonical.json"
            canonical.write_text("{}", encoding="utf-8")
            manifest = RunManifest(root / "run-manifest.json", "run-1")
            now = "2026-01-01T00:00:00Z"
            for stage in STAGE_SEQUENCE:
                manifest.record(stage, inputs=[], outputs=[], started_at=now, finished_at=now)
            manifest.bind_canonical(canonical)
            manifest.bind_publication(root, [canonical])
            document = json.loads(manifest.path.read_text(encoding="utf-8"))
            document["stages"][3]["output_digest"] = "tampered"
            manifest.path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(PipelineIntegrityError, "modified"):
                validate_run_manifest(manifest.path)

    def test_public_output_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            canonical = root / "canonical.json"; canonical.write_text("{}", encoding="utf-8")
            public = root / "output.json"; public.write_text("{}", encoding="utf-8")
            manifest = RunManifest(root / "run-manifest.json", "run-1")
            now = "2026-01-01T00:00:00Z"
            for stage in STAGE_SEQUENCE:
                manifest.record(stage, inputs=[], outputs=[], started_at=now, finished_at=now)
            manifest.bind_canonical(canonical); manifest.bind_publication(root, [public])
            public.write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaisesRegex(PipelineIntegrityError, "Published artifact"):
                validate_run_manifest(manifest.path)


class SemanticGateTests(unittest.TestCase):
    def test_each_testable_cp_requires_exactly_one_acceptance_tc(self) -> None:
        points = [{"id": "CP-001", "disposition": "TEST_CASE"}]
        with self.assertRaisesRegex(PipelineIntegrityError, "acceptance-count=0"):
            audit_atomic_coverage(points, [])
        self.assertTrue(audit_atomic_coverage(points, [acceptance("TC-001", ["CP-001"])])["atomic_coverage_valid"])

    def test_multi_cp_acceptance_requires_indivisible_contract(self) -> None:
        points = [{"id": value, "disposition": "TEST_CASE"} for value in ("CP-001", "CP-002")]
        with self.assertRaisesRegex(PipelineIntegrityError, "acceptance-must-exercise-one-cp"):
            audit_atomic_coverage(points, [acceptance("TC-001", ["CP-001", "CP-002"])])
        case = acceptance("TC-001", ["CP-001", "CP-002"])
        case["atomicity_exception"] = {
            "reason": "INDIVISIBLE_CONTRACT", "shared_failure_domain": "one audit event",
            "claim_ids": ["CLAIM-001", "CLAIM-002"],
        }
        self.assertTrue(audit_atomic_coverage(points, [case])["atomic_coverage_valid"])

    def test_expected_identifier_cannot_disappear(self) -> None:
        with self.assertRaisesRegex(PipelineIntegrityError, "RF-002"):
            build_identifier_ledger(
                [{"id": "NU-1", "path": "req.md", "source_refs": [{"reference": "RF-001"}]}],
                [{"path": "req.md", "expected_identifiers": ["RF-001", "RF-002"]}],
            )

    def test_historical_baseline_requires_reconciliation(self) -> None:
        lock = {
            "corpus_identity": "demo", "source_scope_digest": "scope",
            "claim_fingerprints": ["old"], "normative_test_fingerprints": [],
            "known_finding_fingerprints": [], "reconciliations": [],
        }
        with self.assertRaisesRegex(PipelineIntegrityError, "intent disappeared"):
            audit_historical_baseline(
                lock, corpus_identity="demo", source_scope_digest="scope",
                claim_fingerprints=set(), test_fingerprints=set(), finding_fingerprints=set(),
            )

    def test_scenario_family_cp_links_equal_member_union(self) -> None:
        scenarios = [{"id": "SCN-001", "coverage_point_refs": ["CP-001"], "test_case_refs": ["TC-001"]}]
        self.assertTrue(audit_scenario_family_linkage(scenarios, [acceptance("TC-001", ["CP-001"])])["scenario_family_linkage_valid"])
        scenarios[0]["coverage_point_refs"] = ["CP-999"]
        with self.assertRaisesRegex(PipelineIntegrityError, "linkage mismatch"):
            audit_scenario_family_linkage(scenarios, [acceptance("TC-001", ["CP-001"])])

    def test_use_case_flow_requires_observable_target(self) -> None:
        flow = [{"id": "FLOW-1"}]
        opportunity = [{"flow_ref": "FLOW-1", "flow_disposition": "E2E_SCENARIO", "target_refs": ["SCN-1"]}]
        with self.assertRaisesRegex(PipelineIntegrityError, "not-exercised"):
            audit_use_case_flow_exercise(flow, opportunity, {"SCN-2"})

    def test_e2e_requires_semantic_stage_map_for_every_composed_atomic(self) -> None:
        cases = [acceptance("TC-001", ["CP-001"]), {
            **acceptance("TC-002", ["CP-002"]), "test_basis": "E2E", "composes": ["TC-001"],
            "e2e_stage_map": [],
        }]
        with self.assertRaisesRegex(PipelineIntegrityError, "E2E stage"):
            audit_e2e_stage_mapping(cases)

    def test_one_step_case_cannot_compress_documented_multi_action_path(self) -> None:
        case = acceptance("TC-001", ["CP-001"])
        with self.assertRaisesRegex(PipelineIntegrityError, "One-step"):
            audit_one_step_completeness([case], {"TC-001": {"actions": [{}, {}]}})

    def test_automation_false_has_machine_readable_blocker(self) -> None:
        case = acceptance("TC-001", ["CP-001"])
        case.update({"automation_layer": "UI", "automation_tool_hint": "PLAYWRIGHT", "deterministic": True})
        audit = [{"automation_classification": "AUTOMATION_EXECUTION_NOT_READY", "reason_codes": ["PATH_COMPRESSION"]}]
        apply_runtime_readiness([case], audit)
        self.assertFalse(case["automation_candidate"])
        self.assertEqual("PATH_COMPRESSION", case["automation_blocker"])

    def test_priority_requires_a_reason(self) -> None:
        case = acceptance("TC-001", ["CP-001"]); case.pop("priority_reason")
        with self.assertRaisesRegex(PipelineIntegrityError, "Priority lacks"):
            audit_priority_calibration([case])

    def test_missing_implementation_cannot_remove_normative_source_unit(self) -> None:
        inventory = [{
            "path": "req.md", "authority": "NORMATIVE_PRIMARY", "disposition": "INCLUDED",
        }]
        units = [{
            "id": "NU-001", "path": "req.md", "family": "FUNCTIONAL_REQUIREMENT",
            "disposition": "NOT_TESTABLE", "reason": "implementation is missing",
            "source_refs": [{"source": "req.md", "reference": "RF-1"}],
        }]
        with self.assertRaisesRegex(SourceInventoryError, "cannot disappear"):
            audit_normative_source_units(inventory, units)

    def test_performance_claim_requires_a_measurable_observation_contract(self) -> None:
        claims = [{"id": "CLAIM-001"}]
        clauses = [{"id": "CLAUSE-001", "destination_type": "COVERAGE_POINT"}]
        points = [{"id": "CP-001", "clause_refs": ["CLAUSE-001"]}]
        case = acceptance("TC-001", ["CP-001"]); case["primary_type"] = "PERFORMANCE"
        with self.assertRaisesRegex(PipelineIntegrityError, "performance_observation"):
            audit_claim_exercise(
                claims, clauses, points, [case], {"TC-001": {}},
                {"CLAIM-001": "CLAUSE-001"},
            )


class ArtifactAndIntegrationTests(unittest.TestCase):
    def test_physical_source_ledger_records_real_hash_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / "req.md").write_text("RF-1", encoding="utf-8")
            ledger = build_physical_source_ledger(root, ["req.md"], [{
                "source": "req.md", "disposition": "INSPECTED_CONTENT", "evidence_records": 1,
            }])
            self.assertEqual(64, len(ledger["entries"][0]["sha256"]))
            self.assertTrue(ledger["entries"][0]["exists"])

    def test_test_asset_challenge_is_auditable_even_when_empty(self) -> None:
        self.assertEqual([], materialize_test_asset_challenge([], [])["behaviors"])

    def test_real_generation_publishes_manifest_and_internal_audits(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); artifact = root / "artifacts"
            request = generation_request(root, artifact)
            request["schema_version"] = "2.2"
            request["source_inventory"] = [{
                "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
                "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED", "reason": "approved",
            }]
            request["formats"] = ["JSON", "HTML", "DIAGNOSTICS"]
            result = dispatch("ftd-gen", **request)
            manifest = artifact / ".ftd" / "runs" / "run-001" / "run-manifest.json"
            self.assertEqual(list(STAGE_SEQUENCE), [item["stage"] for item in validate_run_manifest(manifest)["stages"]])
            self.assertTrue((artifact / "diagnostics" / "test-asset-challenge.json").is_file())
            self.assertTrue((artifact / "diagnostics" / "source-identifier-ledger.json").is_file())
            self.assertEqual("2.2", json.loads((artifact / "output" / "test-cases.json").read_text(encoding="utf-8"))["schema_version"])
            recorded = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))["run_manifest"]
            self.assertEqual(manifest.resolve(), Path(recorded).resolve())


if __name__ == "__main__":
    unittest.main()
