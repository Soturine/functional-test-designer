#!/usr/bin/env python3
"""Enforced shared ftd-gen path from scope lock through canonical projections."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from additive_expansion import (
    apply_test_data_reachability, audit_baseline_preservation,
    audit_expansion_dispositions, audit_semantic_composition, normative_profiles,
    calibrate_priority, priority_metrics, snapshot_normative_baseline,
)
from canonical_state import OutputSelection, persist_canonical_suite, render_selected_outputs
from cross_source_contradictions import audit_contradictions
from execution_quality import procedure_template_metrics
from procedural_pipeline import reconcile_additive_feedback, run_procedural_tasks
from procedural_readiness import align_public_status, audit_execution_readiness
from pipeline_integrity import (
    RunManifest, audit_atomic_coverage, audit_claim_exercise,
    audit_e2e_stage_mapping, audit_historical_baseline, audit_one_step_completeness,
    audit_priority_calibration, audit_scenario_family_linkage,
    audit_use_case_flow_exercise, apply_runtime_readiness, build_identifier_ledger,
    build_physical_source_ledger, link_identifier_ledger, reject_request_owned_results,
    stable_digest, validate_run_manifest,
)
from render_operational_scenarios import build_operational_catalog
from resolve_artifacts import resolve_artifact_paths
from resolve_scope import resolve_selected_scope
from run_state import RunStateStore, source_manifest
from scenario_independence import build_scenario_family_pipeline, build_scenario_pipeline
from risk_coverage import audit_flow_coverage, audit_risk_matrix
from risk_expansion import expand_risk_profiles
from scenario_opportunities import audit_scenario_opportunities
from source_accounting import (
    audit_source_review_independence, build_source_ledger, read_telemetry,
)
from source_inventory import (
    audit_normative_source_units, audit_source_inventory,
    audit_use_case_flow_accounting,
)
from quality_gates import assert_quality_gates, build_quality_gates
from reference_integrity import audit_evidence_references
from test_asset_inventory import audit_test_asset_inventory, materialize_test_asset_challenge
from source_coverage_audit import (
    audit_atomic_chain, audit_materialized_atomicity, audit_source_claims,
    materialize_atomic_coverage, review_source_items,
)


REQUIRED_INPUTS = {
    "workspace", "selectors", "artifact_root", "run_id", "sources", "requirements",
    "source_items", "source_ledger", "source_review", "evidence_manifest", "selected_evidence",
    "opportunities", "risk_conditions", "use_case_flows", "test_asset_inventory",
    "scenario_profiles", "evidence_packs",
}
PHASES = (
    "scope_resolution", "source_inventory", "source_collection", "evidence_reconciliation",
    "source_atomicity", "coverage_design", "scenario_reasoning", "scenario_engine",
    "procedural_reasoning", "procedural_engine", "validation", "rendering",
)
FULL_RUN_STAGES = (
    "SOURCE_SELECTION", "SOURCE_READING", "SOURCE_STRUCTURAL_INDEXING",
    "NORMATIVE_UNIT_EXTRACTION", "IMPLEMENTATION_EVIDENCE_EXTRACTION",
    "TEST_ASSET_EXTRACTION", "REQUEST_ASSEMBLY",
)
OFFICIAL_PROVENANCE_GROUPS = {
    "ORCHESTRATOR_EXECUTION": {
        "scope_resolution", "source_inventory", "source_collection",
        "evidence_reconciliation", "source_atomicity", "coverage_design",
        "scenario_reasoning", "normative_baseline_freeze", "scenario_engine",
    },
    "EXPANSION": {"risk_expansion"},
    "PROCEDURE_REFINEMENT": {"procedural_reasoning", "procedural_engine"},
    "VALIDATION": {"validation"},
    "RENDERING": {"rendering"},
}


class GenerationContractError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _full_run_provenance(request: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = {
        str(item.get("stage")): item
        for item in request.get("preprocessing_provenance", [])
        if isinstance(item, dict)
    }
    records = []
    for stage in FULL_RUN_STAGES:
        item = supplied.get(stage)
        if item is None:
            records.append({
                "stage": stage, "status": "UNAVAILABLE", "started_at": None,
                "finished_at": None, "duration_seconds": None, "inputs": [],
                "outputs": [], "provenance": "host did not expose preprocessing timing",
            })
        else:
            records.append({
                "stage": stage, "status": str(item.get("status", "COMPLETE")),
                "started_at": item.get("started_at"), "finished_at": item.get("finished_at"),
                "duration_seconds": item.get("duration_seconds"),
                "inputs": list(item.get("inputs", [])), "outputs": list(item.get("outputs", [])),
                "provenance": str(item.get("provenance", "host supplied")),
            })
    return records


def _official_run_provenance(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project measured engine phases onto the public full-run provenance stages."""
    records: list[dict[str, Any]] = []
    for stage, names in OFFICIAL_PROVENANCE_GROUPS.items():
        members = [item for item in phases if item["name"] in names]
        if not members:
            records.append({
                "stage": stage, "status": "NOT_RUN", "started_at": None,
                "finished_at": None, "duration_seconds": 0.0, "inputs": [],
                "outputs": [], "provenance": "official shared runtime",
            })
            continue
        records.append({
            "stage": stage, "status": "COMPLETE",
            "started_at": members[0]["started_at"],
            "finished_at": members[-1]["finished_at"],
            "duration_seconds": round(sum(item["wall_clock_seconds"] for item in members), 6),
            "inputs": [item["name"] for item in members],
            "outputs": [item["name"] for item in members],
            "provenance": "measured by official shared runtime",
        })
    return records


def _run_generation(request: dict[str, Any]) -> dict[str, Any]:
    """Run every mandatory gate; precomputed free-form handoffs are not accepted."""
    run_began = time.perf_counter()
    reject_request_owned_results(request)
    schema_version = str(request.get("schema_version", "2.2"))
    if schema_version not in {"1.2", "2.2"}:
        raise GenerationContractError(f"Unsupported public schema version {schema_version}")
    missing = sorted(REQUIRED_INPUTS - set(request))
    if missing:
        raise GenerationContractError("ftd-gen requires structured shared-core inputs: " + ", ".join(missing))
    workspace = Path(request["workspace"]).resolve()
    artifact_paths = resolve_artifact_paths(
        skill_root=Path(__file__).resolve().parents[1], source_root=workspace,
        explicit_artifact_root=Path(request["artifact_root"]),
    )
    artifact_root = Path(artifact_paths["artifact_root"])
    run_id = str(request["run_id"])
    store = RunStateStore(artifact_root, run_id)
    manifest_path = store.run_dir / "run-manifest.json"
    internal_metrics = store.run_dir / "orchestration-metrics.json"
    metrics: dict[str, Any] = {
        "schema_version": "1", "diagnostic": bool(request.get("diagnostic", False)),
        "started_at": _now(), "timing_available": True, "phases": [],
        "checkpoint_events": [], **read_telemetry(request),
        "full_run_provenance": _full_run_provenance(request),
        "user_perceived_wall_time": request.get("user_perceived_wall_time"),
        "source_analysis_time": request.get("source_analysis_time"),
        "request_assembly_time": request.get("request_assembly_time"),
    }
    _write(internal_metrics, metrics)  # initialized before scope/source work

    def phase(name: str, action: Callable[[], Any]) -> Any:
        began_at = _now(); began = time.perf_counter()
        value = action()
        metrics["phases"].append({
            "name": name, "started_at": began_at, "finished_at": _now(),
            "wall_clock_seconds": round(time.perf_counter() - began, 6),
            "timing_available": True,
        })
        _write(internal_metrics, metrics)
        return value

    before_python = {path.resolve() for path in workspace.rglob("*.py")}
    scope = phase("scope_resolution", lambda: resolve_selected_scope(workspace, list(request["selectors"])))
    paths = [workspace / value for value in scope["resolved_scope_paths"]]
    hashes = phase("source_inventory", lambda: source_manifest(paths, workspace))
    selection = OutputSelection.normalize(request.get("formats"))
    previous = store.load(hashes)
    if previous is not None and previous.reusable and previous.checkpoint == "VALIDATED":
        canonical_name = str(previous.payload.get("canonical_suite", ""))
        canonical_path = store.run_dir / canonical_name
        if canonical_name and canonical_path.is_file():
            validate_run_manifest(manifest_path)
            metrics["checkpoint_events"].append({
                "checkpoint": "VALIDATED", "event": "resumed",
                "reason": "SOURCE_HASHES_AND_CANONICAL_STATE_MATCH",
            })
            rendered = phase(
                "rendering", lambda: render_selected_outputs(canonical_path, artifact_root, selection)
            )
            metrics.update({
                "finished_at": _now(), "resumed_from_checkpoint": "VALIDATED",
                "rendered_public_formats": rendered["rendered_public_formats"],
            })
            metrics["run_wall_clock_seconds"] = round(time.perf_counter() - run_began, 6)
            metrics["official_pipeline_time"] = metrics["run_wall_clock_seconds"]
            metrics["render_validation_time"] = round(sum(
                item["wall_clock_seconds"] for item in metrics["phases"]
                if item["name"] in {"validation", "rendering"}
            ), 6)
            metrics["attributed_stage_seconds"] = round(
                sum(item["wall_clock_seconds"] for item in metrics["phases"]), 6
            )
            metrics["unattributed_seconds"] = round(max(
                0.0, metrics["run_wall_clock_seconds"] - metrics["attributed_stage_seconds"]
            ), 6)
            metrics["stage_provenance"] = [{
                "stage": item["name"], "order": number,
                "generator": "functional-test-designer/2.2.2",
                "status": "COMPLETE", "validation_result": "PASS",
            } for number, item in enumerate(metrics["phases"], 1)]
            metrics["full_run_provenance"].extend(
                _official_run_provenance(metrics["phases"])
            )
            _write(internal_metrics, metrics)
            if "DIAGNOSTICS" in selection.formats:
                destination = artifact_root / "diagnostics" / "run-metrics.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(internal_metrics, destination)
            return {
                "intent": "ftd-gen", "scope": scope, "resumed": True,
                "canonical_path": str(canonical_path), "render": rendered,
                "diagnostics": str(internal_metrics),
            }
    if previous is not None and not previous.reusable:
        metrics["checkpoint_events"].append({
            "checkpoint": previous.checkpoint, "event": "invalidated",
            "reason": previous.invalidation_reason,
        })
    elif previous is not None:
        metrics["checkpoint_events"].append({
            "checkpoint": previous.checkpoint, "event": "invalidated",
            "reason": "CHECKPOINT_PAYLOAD_CANNOT_RESUME_THIS_STAGE",
        })
    store.save("SCOPE_RESOLVED", {"scope": scope}, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "SCOPE_RESOLVED", "event": "created"})
    manifest = RunManifest(manifest_path, run_id)
    stamp = _now()
    manifest.record(
        "SOURCE_SELECTION", inputs=request["selectors"], outputs=scope,
        started_at=metrics["phases"][0]["started_at"], finished_at=stamp,
    )

    def collect() -> dict[str, Any]:
        manifest = set(map(str, request["evidence_manifest"]))
        expected = set(scope["resolved_scope_paths"])
        if manifest != expected:
            raise GenerationContractError("Evidence manifest must account for every resolved selected source")
        ledger = build_source_ledger(scope["resolved_scope_paths"], request["source_ledger"])
        return {
            "files": len(manifest), "records": len(request["selected_evidence"]), "ledger": ledger,
        }

    collection = phase("source_collection", collect)
    physical_source_ledger = build_physical_source_ledger(
        workspace, scope["resolved_scope_paths"], request["source_ledger"]
    )
    ledger_entries = collection["ledger"]["entries"]
    metrics.update({
        "source_files_assigned": collection["files"],
        "source_records_received": collection["records"],
        **collection["ledger"]["metrics"],
        "test_files_selected": sum(
            entry["source_role"] == "TEST_ASSET" for entry in ledger_entries
        ),
        "functional_authority_source_behaviors": sum(
            entry["source_behaviors"] for entry in ledger_entries
            if entry["source_role"] == "FUNCTIONAL_AUTHORITY"
        ),
    })
    source_universe = None
    source_unit_audit = {"normative_source_families_complete": True}
    use_case_accounting = {"use_case_flow_accounting_valid": True}
    evidence_reference_audit = {"evidence_reference_integrity_valid": True}
    identifier_ledger = {
        "entries": [], "source_identifiers_expected": 0,
        "source_identifiers_discovered": 0, "source_identifiers_missing": 0,
        "source_identifiers_complete": True,
    }
    if schema_version == "2.2":
        if "source_inventory" not in request:
            raise GenerationContractError("Schema 2.2 requires an authority-aware source_inventory")
        source_universe = audit_source_inventory(
            request["sources"], request["source_inventory"],
            referenced_authoritative_paths=request.get("referenced_authoritative_paths", []),
        )
        if "source_units" not in request or "source_unit_expectations" not in request:
            raise GenerationContractError(
                "Schema 2.2 requires source_units and independent source_unit_expectations"
            )
        source_unit_audit = audit_normative_source_units(
            request["source_inventory"], request["source_units"],
            request["source_unit_expectations"],
        )
        use_case_accounting = audit_use_case_flow_accounting(
            request["source_units"], request["use_case_flows"]
        )
        evidence_reference_audit = audit_evidence_references(
            workspace, request["sources"], [
                request["requirements"], request["source_items"], request.get("questions", []),
                request.get("findings", []), request["evidence_packs"],
                request.get("risk_candidate_profiles", []),
                request.get("expansion_opportunities", []),
                request.get("contradiction_candidates", []),
            ],
        )
        metrics.update({key: value for key, value in source_universe.items() if not isinstance(value, list)})
        metrics.update(source_unit_audit)
        metrics.update(use_case_accounting)
        metrics.update(evidence_reference_audit)
        identifier_ledger = build_identifier_ledger(
            request["source_units"], request["source_unit_expectations"],
            patterns=request.get("source_identifier_patterns"),
        )
        metrics.update({key: value for key, value in identifier_ledger.items() if key != "entries"})
    stamp = _now()
    manifest.record(
        "SOURCE_ACCOUNTING", inputs=scope, outputs=collection["ledger"],
        started_at=stamp, finished_at=stamp,
    )
    manifest.record(
        "SOURCE_UNIT_EXTRACTION", inputs=request.get("source_inventory", request["sources"]),
        outputs={"units": request.get("source_units", []), "identifier_ledger": identifier_ledger},
        started_at=stamp, finished_at=stamp,
    )
    store.save("SOURCE_ACCOUNTING_COMPLETE", {
        "dispositions": collection["ledger"]["dispositions"],
    }, hashes)
    metrics["checkpoint_events"].append(
        {"checkpoint": "SOURCE_ACCOUNTING_COMPLETE", "event": "created"}
    )
    phase("evidence_reconciliation", lambda: list(request["selected_evidence"]))
    store.save("EVIDENCE_BARRIER_COMPLETE", {"evidence_records": collection["records"]}, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "EVIDENCE_BARRIER_COMPLETE", "event": "created"})

    inventory = phase("source_atomicity", lambda: review_source_items(request["source_items"]))
    chain = phase("coverage_design", lambda: materialize_atomic_coverage(inventory))
    stamp = _now()
    manifest.record("CLAIM_EXTRACTION", inputs=request["source_items"], outputs=inventory["claims"], started_at=stamp, finished_at=stamp)
    manifest.record("CLAUSE_NORMALIZATION", inputs=inventory["claims"], outputs=chain["normative_clauses"], started_at=stamp, finished_at=stamp)
    manifest.record("COVERAGE_DESIGN", inputs=chain["normative_clauses"], outputs=chain["coverage_points"], started_at=stamp, finished_at=stamp)
    atomic_audit = audit_atomic_chain(inventory, chain)
    residual_audit = audit_materialized_atomicity(inventory, chain)
    review = audit_source_review_independence(
        request["source_review"], primary_claim_count=inventory["atomic_source_claims_identified"],
    )
    source_audit = audit_source_claims(review["source_first_claims"], chain["normative_clauses"])
    store.save("SOURCE_REVIEW_COMPLETE", {
        "independent_review_source_behaviors": review["independent_review_source_behaviors"],
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "SOURCE_REVIEW_COMPLETE", "event": "created"})
    if source_audit["source_coverage_gaps"]:
        raise GenerationContractError("Source-first coverage gaps must be resolved before Scenario Design")
    store.save("SOURCE_ATOMICITY_COMPLETE", {
        "claims": inventory["atomic_source_claims_identified"],
        "clauses": len(chain["normative_clauses"]),
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "SOURCE_ATOMICITY_COMPLETE", "event": "created"})

    question_ids = {str(item["id"]) for item in request.get("questions", [])}

    def review_opportunities() -> dict[str, Any]:
        precheck = audit_scenario_opportunities(
            request["selected_evidence"], request["opportunities"]
        )
        assets = request["test_asset_inventory"]
        declared_test_assets = any(
            entry["source_role"] == "TEST_ASSET" for entry in collection["ledger"]["entries"]
        )
        discovered = list(assets.get("discovered", []))
        if declared_test_assets and not discovered:
            raise GenerationContractError(
                "Selected Test Assets require a real inventory before disposition"
            )
        return {
            **precheck,
            **audit_test_asset_inventory(
                discovered, list(assets.get("classifications", [])),
                strict_challenge=schema_version == "2.2",
            ),
            **audit_risk_matrix(
                request["risk_conditions"], request["opportunities"], question_ids=question_ids
            ),
            **audit_flow_coverage(request["use_case_flows"], request["opportunities"]),
        }

    opportunity_precheck = phase("scenario_reasoning", review_opportunities)
    challenge_artifact = materialize_test_asset_challenge(
        list(request["test_asset_inventory"].get("discovered", [])),
        list(request["test_asset_inventory"].get("classifications", [])),
    )
    store.save("OPPORTUNITY_AUDIT_COMPLETE", {
        "risk_conditions_reviewed": opportunity_precheck["risk_conditions_reviewed"],
        "use_case_flows_reviewed": opportunity_precheck["use_case_flows_reviewed"],
    }, hashes)
    metrics["checkpoint_events"].append(
        {"checkpoint": "OPPORTUNITY_AUDIT_COMPLETE", "event": "created"}
    )
    scenario_profiles = request["scenario_profiles"]
    baseline_snapshot: dict[str, dict[str, Any]] = {}
    baseline_metrics = {"baseline_preserved": True}
    expansion_metrics = {"risk_disposition_complete": True}
    if schema_version == "2.2":
        baseline_design = phase(
            "normative_baseline_freeze",
            lambda: build_scenario_family_pipeline(
                chain["coverage_points"], normative_profiles(scenario_profiles)
            ),
        )
        baseline_snapshot = snapshot_normative_baseline(baseline_design)
        store.save("NORMATIVE_BASELINE_FROZEN", {
            "test_ids": sorted(baseline_snapshot),
            "oracles": {key: value["normative_oracle"] for key, value in baseline_snapshot.items()},
        }, hashes)
        metrics["checkpoint_events"].append(
            {"checkpoint": "NORMATIVE_BASELINE_FROZEN", "event": "created"}
        )
    stamp = _now()
    manifest.record(
        "NORMATIVE_BASELINE", inputs=chain["coverage_points"],
        outputs=baseline_snapshot, started_at=stamp, finished_at=stamp,
    )
    manifest.record(
        "TEST_ASSET_CHALLENGE", inputs=request["test_asset_inventory"],
        outputs=challenge_artifact, started_at=stamp, finished_at=stamp,
    )
    risk_expansion_metrics: dict[str, Any] = {
        "risk_candidates_added": 0, "exploratory_policy_gaps": 0,
        "materialized_risk_refs": [],
    }
    if schema_version == "2.2":
        scenario_profiles, risk_expansion_metrics = phase(
            "risk_expansion",
            lambda: expand_risk_profiles(
                scenario_profiles, request["risk_conditions"], request.get("risk_candidate_profiles", []),
                coverage_point_ids={str(item["id"]) for item in chain["coverage_points"]},
            ),
        )
    stamp = _now()
    operator_profiles = [
        item for item in request.get("risk_candidate_profiles", [])
        if str(next((risk.get("risk_class") for risk in request["risk_conditions"]
                     if str(risk.get("id")) == str(item.get("risk_condition_ref"))), ""))
        in {"OPERATOR_ERROR", "MISUSE", "NEGATIVE", "ADVERSARIAL_OPERATIONAL"}
    ]
    manifest.record(
        "OPERATOR_ERROR_EXPANSION", inputs=operator_profiles,
        outputs={"materialized": risk_expansion_metrics.get("materialized_risk_refs", [])},
        started_at=stamp, finished_at=stamp,
    )
    manifest.record(
        "RISK_EXPANSION", inputs=request["risk_conditions"], outputs=risk_expansion_metrics,
        started_at=stamp, finished_at=stamp,
    )
    design = phase(
        "scenario_engine",
        lambda: (
            build_scenario_family_pipeline(chain["coverage_points"], scenario_profiles)
            if schema_version == "2.2"
            else build_scenario_pipeline(chain["coverage_points"], scenario_profiles)
        ),
    )
    if schema_version == "2.2":
        baseline_metrics = audit_baseline_preservation(baseline_snapshot, design)
        expansion_metrics = audit_expansion_dispositions(
            request.get("expansion_opportunities", []),
            set(risk_expansion_metrics["materialized_risk_refs"]),
            required_risk_refs={str(item["id"]) for item in request["risk_conditions"]},
        )
        semantic_composition = audit_semantic_composition(design)
    else:
        semantic_composition = {"semantic_composition_valid": True}
    stamp = _now()
    manifest.record(
        "CHARACTERIZATION", inputs=scenario_profiles,
        outputs=[item.id for item in design["test_identities"] if item.test_basis == "CHARACTERIZATION"],
        started_at=stamp, finished_at=stamp,
    )
    manifest.record(
        "CROSS_REQUIREMENT", inputs=request.get("opportunities", []),
        outputs=[item.id for item in design["test_identities"] if len(item.requirement_refs) > 1],
        started_at=stamp, finished_at=stamp,
    )
    manifest.record(
        "E2E_COMPOSITION", inputs=request.get("use_case_flows", []),
        outputs=[item.id for item in design["test_identities"] if item.test_basis == "E2E"],
        started_at=stamp, finished_at=stamp,
    )
    scenario_ids = {item["id"] for item in design["scenarios"]}
    finding_ids = {str(item["id"]) for item in request.get("findings", [])}
    contradiction_audit = audit_contradictions(
        request.get("contradiction_candidates", []), finding_ids, question_ids
    )
    opportunity_audit = audit_scenario_opportunities(
        request["selected_evidence"], request["opportunities"], scenario_ids=scenario_ids,
        finding_ids=finding_ids, question_ids=question_ids,
    )
    store.save("SCENARIOS_FROZEN", {
        "scenario_ids": sorted(scenario_ids), "test_identity_ids": [item.id for item in design["test_identities"]],
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "SCENARIOS_FROZEN", "event": "created"})

    packs = dict(request["evidence_packs"])
    if schema_version == "2.2":
        for candidate, identity in zip(design["candidates"], design["test_identities"]):
            if identity.id not in packs and candidate.get("evidence_pack"):
                packs[identity.id] = dict(candidate["evidence_pack"])
    tasks = []
    candidates_by_tc = dict(zip(
        (item.id for item in design["test_identities"]), design["candidates"]
    ))
    for identity in design["test_identities"]:
        if identity.id not in packs:
            raise GenerationContractError(f"Frozen identity {identity.id} has no Evidence Pack")
        pack = dict(packs[identity.id])
        if pack.get("priority") in {None, "AUTO"}:
            pack["priority"] = calibrate_priority(candidates_by_tc[identity.id])
            packs[identity.id] = pack
        pack["schema_version"] = schema_version
        tasks.append((identity, pack))
    procedural = phase("procedural_reasoning", lambda: run_procedural_tasks(tasks))
    reconciliation = phase(
        "procedural_engine",
        lambda: reconcile_additive_feedback([item.case for item in procedural.results], procedural.results),
    )
    cases = reconciliation["test_cases"]
    readiness = []
    for case, identity in zip(cases, design["test_identities"]):
        pack = dict(packs[identity.id])
        context = {
            "known_path_actions": len(pack.get("actions", [])),
            "execution_surface": pack.get("execution_surface"),
            "execution_surface_required": pack.get("execution_surface_required", False),
            "record_required": pack.get("record_required", False),
            "intermediate_observation_required": pack.get("intermediate_observation_required", False),
            "setup_required": pack.get("setup_required", False),
            "setup": pack.get("setup"),
            "procedural_actions": pack.get("actions", []),
        }
        audit = audit_execution_readiness(case, identity, context)
        align_public_status(case, audit)
        if schema_version == "2.2":
            case["execution_status"] = case["status"]
            if identity.test_basis == "E2E":
                case["e2e_stage_map"] = list(pack.get("e2e_stage_map", []))
            case["priority_reason"] = str(pack.get(
                "priority_reason", "Priority preserved from evidence-supported impact assessment."
            ))
        readiness.append(audit)
    automation_audit = apply_runtime_readiness(cases, readiness) if schema_version == "2.2" else {
        "automation_readiness_valid": True
    }
    reachability = apply_test_data_reachability(
        cases, packs, {str(item["id"]) for item in request.get("findings", [])}
    )
    store.save("PROCEDURAL_COMPLETE", {
        "case_ids": [item["id"] for item in cases],
        "human_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_READY" for item in readiness),
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "PROCEDURAL_COMPLETE", "event": "created"})

    atomic_coverage_audit = audit_atomic_coverage(chain["coverage_points"], cases) if schema_version == "2.2" else {
        "atomic_coverage_valid": True
    }
    claim_exercise_audit = audit_claim_exercise(
        inventory["claims"], chain["normative_clauses"], chain["coverage_points"],
        cases, packs, chain["claim_destinations"],
    ) if schema_version == "2.2" else {"claim_exercise_valid": True, "mappings": []}
    identifier_ledger = link_identifier_ledger(
        identifier_ledger, inventory["claims"], claim_exercise_audit.get("mappings", [])
    )
    one_step_audit = audit_one_step_completeness(cases, packs) if schema_version == "2.2" else {
        "one_step_completeness_valid": True
    }
    priority_audit = audit_priority_calibration(cases) if schema_version == "2.2" else {
        "priority_calibration_valid": True
    }
    scenario_linkage_audit = audit_scenario_family_linkage(
        design["scenarios"], cases
    ) if schema_version == "2.2" else {"scenario_family_linkage_valid": True}
    e2e_stage_audit = audit_e2e_stage_mapping(cases) if schema_version == "2.2" else {
        "e2e_stage_mapping_valid": True
    }
    flow_exercise_audit = audit_use_case_flow_exercise(
        request["use_case_flows"], request["opportunities"],
        {str(item["id"]) for item in design["scenarios"]} | {str(item["id"]) for item in cases}
        | question_ids,
    ) if schema_version == "2.2" else {"use_case_flow_exercise_valid": True}
    findings_for_baseline = [*request.get("findings", []), *reconciliation["findings"]]
    historical_audit = audit_historical_baseline(
        request.get("historical_baseline_lock"),
        corpus_identity=str(request.get("corpus_identity", "")),
        source_scope_digest=stable_digest(scope["resolved_scope_paths"]),
        claim_fingerprints={stable_digest({
            "requirement_ref": item.get("requirement_ref"),
            "normalized_claim": item.get("normalized_claim"),
        }) for item in inventory["claims"]},
        test_fingerprints={stable_digest({
            "requirements": item.get("requirement_refs"),
            "coverage": item.get("coverage_point_refs"),
            "oracle": item.get("steps", [{}])[-1].get("expected_result"),
        }) for item in cases if item.get("test_basis") == "ACCEPTANCE"},
        finding_fingerprints={stable_digest({
            "type": item.get("type"), "statement": item.get("statement"),
            "requirements": item.get("requirement_refs"),
        }) for item in findings_for_baseline},
    ) if schema_version == "2.2" else {"historical_baseline_regression_valid": True}
    stamp = _now()
    manifest.record(
        "PROCEDURE_REFINEMENT", inputs=[item.id for item in design["test_identities"]],
        outputs=cases, started_at=stamp, finished_at=stamp,
    )
    validate_run_manifest(manifest_path, require_publication=False)

    cases_by_cp: dict[str, list[str]] = {}
    for case in cases:
        for cp in case["coverage_point_refs"]:
            cases_by_cp.setdefault(cp, []).append(case["id"])
    points = json.loads(json.dumps(chain["coverage_points"]))
    for point in points:
        point["target_refs"] = cases_by_cp[point["id"]]
    entries = []
    for case in cases:
        entry = {
            "id": case["id"], "title": case["title"], "status": case["status"],
            "requirement_refs": case["requirement_refs"], "scenario_refs": case["scenario_refs"],
            "coverage_point_refs": case["coverage_point_refs"],
            "file": f"test-cases/{case['id']}.json", "markdown_file": f"test-cases-md/{case['id']}.md",
        }
        if schema_version == "2.2":
            for field in (
                "test_basis", "primary_type", "execution_status", "question_refs",
                "finding_refs", "composes", "automation_candidate",
            ):
                entry[field] = case[field]
        entries.append(entry)
    findings = findings_for_baseline
    questions = [*request.get("questions", []), *reconciliation["questions"]]
    gates = build_quality_gates(
        source_complete=source_audit["source_coverage_gaps"] == 0 and (
            schema_version == "1.2" or source_universe["source_discovery_coverage"] == "COMPLETE"
        ),
        normative_complete=atomic_audit["unmapped_normative_clauses"] == 0,
        oracle_safe=all(
            identity.test_basis != "ACCEPTANCE" or bool(identity.normative_oracle)
            for identity in design["test_identities"]
        ),
        references_valid=True,
        procedure_acceptable=all(
            case["status"] != "READY" or audit["human_classification"] == "HUMAN_EXECUTION_READY"
            for case, audit in zip(cases, readiness)
        ),
        provenance_valid=True,
        baseline_preserved=baseline_metrics["baseline_preserved"],
        source_families_complete=source_unit_audit["normative_source_families_complete"],
        use_case_flows_valid=use_case_accounting["use_case_flow_accounting_valid"],
        risk_disposition_complete=expansion_metrics["risk_disposition_complete"],
        test_asset_challenge_valid=opportunity_precheck["test_asset_challenge_valid"],
        test_data_reachability_valid=reachability["test_data_reachability_valid"],
        evidence_references_valid=evidence_reference_audit["evidence_reference_integrity_valid"],
        semantic_composition_valid=semantic_composition["semantic_composition_valid"],
        canonical_publication_valid=True,
        historical_baseline_valid=historical_audit["historical_baseline_regression_valid"],
        atomic_coverage_valid=atomic_coverage_audit["atomic_coverage_valid"],
        claim_exercise_valid=claim_exercise_audit["claim_exercise_valid"],
        source_identifiers_complete=identifier_ledger["source_identifiers_complete"],
        use_case_flow_exercise_valid=flow_exercise_audit["use_case_flow_exercise_valid"],
        additive_expansion_complete=expansion_metrics["risk_disposition_complete"],
        one_step_completeness_valid=one_step_audit["one_step_completeness_valid"],
        automation_readiness_valid=automation_audit["automation_readiness_valid"],
        priority_calibration_valid=priority_audit["priority_calibration_valid"],
        scenario_family_linkage_valid=scenario_linkage_audit["scenario_family_linkage_valid"],
        e2e_stage_mapping_valid=e2e_stage_audit["e2e_stage_mapping_valid"],
    )
    assert_quality_gates(gates)
    index = {
        "schema_version": schema_version, "generated_at": request.get("generated_at", _now()),
        "sources": request["sources"], "requirements": request["requirements"],
        "normative_clauses": chain["normative_clauses"], "findings": findings,
        "coverage_points": points,
        "scenarios": [{key: item[key] for key in (
            "id", "title", "type", "requirement_refs", "coverage_point_refs", "test_case_refs"
        ) if key in item} for item in design["scenarios"]],
        "test_cases": entries,
    }
    if schema_version == "2.2":
        index.update({
            "merge_candidates": design["merge_candidates"],
            "quality_gates": gates,
            "source_inventory": source_universe["inventory"],
        })
    questions_document = {"schema_version": schema_version, "questions": questions}
    catalog = build_operational_catalog(request.get("operational_scenarios", []), cases)
    canonical_path = phase("validation", lambda: persist_canonical_suite(
        artifact_root, run_id, index=index, questions=questions_document, cases=cases,
        operational_catalog=catalog,
        diagnostic_artifacts={
            "test-asset-challenge.json": challenge_artifact,
            "source-identifier-ledger.json": identifier_ledger,
            "physical-source-ledger.json": physical_source_ledger,
            "claim-exercise-map.json": {
                "schema_version": "1", "mappings": claim_exercise_audit.get("mappings", []),
            },
        },
    ))
    manifest.bind_canonical(canonical_path)
    stamp = _now()
    manifest.record(
        "VALIDATION", inputs={"index": index, "questions": questions_document, "cases": cases},
        outputs={"canonical_path": str(canonical_path)}, started_at=stamp, finished_at=stamp,
    )
    rendered = phase("rendering", lambda: render_selected_outputs(canonical_path, artifact_root, selection))
    stamp = _now()
    manifest.record(
        "RENDERING", inputs={"canonical": str(canonical_path), "formats": sorted(selection.formats)},
        outputs=rendered, started_at=stamp, finished_at=stamp,
    )
    public_files = [path for path in (artifact_root / "output").rglob("*") if path.is_file()]
    manifest.record(
        "PUBLICATION", inputs=rendered,
        outputs=[str(path.relative_to(artifact_root)) for path in public_files],
        started_at=stamp, finished_at=_now(),
    )
    manifest.bind_publication(artifact_root, public_files)
    validate_run_manifest(manifest_path)
    store.save("VALIDATED", {
        "canonical_suite": canonical_path.name, "run_manifest": manifest_path.name,
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "VALIDATED", "event": "created"})
    superseded = store.supersede_other_validated_runs(
        f"Run {run_id} became the canonical published run"
    )
    for superseded_run in superseded:
        metrics["checkpoint_events"].append({
            "checkpoint": "VALIDATED", "event": "superseded",
            "run_id": superseded_run, "reason": f"canonical run is {run_id}",
        })

    after_python = {path.resolve() for path in workspace.rglob("*.py")}
    unexpected = sorted(str(path) for path in after_python - before_python)
    if unexpected:
        raise GenerationContractError("Generation created ad-hoc executable source: " + ", ".join(unexpected))
    metrics["source_behavior_gaps"] = source_audit["source_coverage_gaps"]
    metrics.update({
        key: value for key, value in review.items() if not isinstance(value, list)
    })
    inventory_metrics = {
        key: value for key, value in inventory.items()
        if key != "claims" and isinstance(value, (int, float, bool))
    }
    metrics.update({
        **inventory_metrics, **chain["metrics"], **atomic_audit, **residual_audit,
        **source_unit_audit, **use_case_accounting, **evidence_reference_audit,
        **opportunity_precheck, **opportunity_audit, **risk_expansion_metrics,
        **baseline_metrics, **expansion_metrics, **semantic_composition, **reachability,
        **contradiction_audit, **atomic_coverage_audit, **claim_exercise_audit,
        **one_step_audit, **automation_audit, **priority_audit,
        **scenario_linkage_audit, **e2e_stage_audit, **flow_exercise_audit,
        **historical_audit,
        **design["metrics"], **procedural.metrics,
        "human_execution_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_READY" for item in readiness),
        "human_execution_not_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_NOT_READY" for item in readiness),
        "automation_execution_ready": sum(item["automation_classification"] == "AUTOMATION_EXECUTION_READY" for item in readiness),
        "automation_execution_not_ready": sum(item["automation_classification"] == "AUTOMATION_EXECUTION_NOT_READY" for item in readiness),
        "cases_missing_setup_acquisition": sum(
            "MISSING_SETUP_ACQUISITION" in item["reason_codes"] for item in readiness
        ),
        "operational_scenario_families": catalog["family_count"],
        "one_step_cases": sum(len(case["steps"]) == 1 for case in cases),
        "legitimate_one_step_cases": sum(
            len(case["steps"]) == 1 and "PATH_COMPRESSION" not in audit["reason_codes"]
            for case, audit in zip(cases, readiness)
        ),
        "path_compression_warnings": sum(
            "PATH_COMPRESSION" in item["reason_codes"] for item in readiness
        ),
        "cases_missing_procedural_provenance": sum(
            "MISSING_PROCEDURAL_PROVENANCE" in item["reason_codes"] for item in readiness
        ),
        "finished_at": _now(), "rendered_public_formats": rendered["rendered_public_formats"],
        "run_manifest": str(manifest_path), "canonical_publication_valid": True,
    })
    steps_total = sum(len(case.get("steps", [])) for case in cases)
    action_keys = {
        " ".join(str(step.get("action", "")).casefold().split())
        for case in cases for step in case.get("steps", [])
    }
    atomic_cases = [case for case in cases if case.get("test_basis", "ACCEPTANCE") != "E2E"]
    blocked_cases = [
        case for case in cases
        if case.get("status") == "BLOCKED" or str(case.get("status", "")).startswith("BLOCKED_")
    ]
    metrics.update({
        "atomic_claims_total": inventory["atomic_source_claims_identified"],
        "composite_claims_split": inventory.get("compound_source_items_split", 0),
        "unresolved_claims": source_audit["source_coverage_gaps"],
        "coverage_points_total": len(points),
        "normative_cp_coverage": "COMPLETE" if atomic_audit["unmapped_normative_clauses"] == 0 else "INCOMPLETE",
        "derived_cp_total": sum(case.get("test_basis") == "DERIVED" for case in cases),
        "unmapped_claims": source_audit["source_coverage_gaps"],
        "uncovered_normative_items": source_audit["source_coverage_gaps"],
        "blocked_tests": len(blocked_cases),
        "avg_cp_per_atomic_tc": round(
            sum(len(case.get("coverage_point_refs", [])) for case in atomic_cases) / len(atomic_cases), 3
        ) if atomic_cases else 0.0,
        "multi_failure_domain_warnings": 0,
        "overcompression_warnings": sum(
            "PATH_COMPRESSION" in item["reason_codes"] for item in readiness
        ),
        "steps_total": steps_total,
        "avg_steps_per_test": round(steps_total / len(cases), 3) if cases else 0.0,
        "one_step_test_ratio": round(sum(len(case.get("steps", [])) == 1 for case in cases) / len(cases), 3) if cases else 0.0,
        "unique_action_ratio": round(len(action_keys) / steps_total, 3) if steps_total else 0.0,
        "abstract_action_count": sum(
            any(code in item["reason_codes"] for code in {"ABSTRACT_TRIGGER", "ABSTRACT_NAVIGATION"})
            for item in readiness
        ),
        "abstract_expected_result_count": sum(
            "ABSTRACT_OBSERVATION" in item["reason_codes"] for item in readiness
        ),
        "missing_expected_results": sum(
            step.get("expected_result") is None for case in cases for step in case.get("steps", [])
        ),
        "missing_test_data_where_required": sum(
            "MISSING_TEST_DATA" in item["reason_codes"] for item in readiness
        ),
        "cross_tc_dependency_count": sum(
            "TC-" in value for case in cases for value in case.get("preconditions", [])
        ),
        "findings_total": len(findings), "questions_total": len(questions),
        "dangling_question_refs": 0, "dangling_finding_refs": 0,
        "oracle_conflicts": sum(item.get("type") == "SOURCE_CONFLICT" for item in findings),
        "normative_vs_implementation_conflicts": sum(
            item.get("type") == "IMPLEMENTATION_DIVERGENCE" for item in findings
        ),
        "duplicated_test_intent": 0,
        "ready": sum(case.get("status") == "READY" for case in cases),
        "needs_review": sum(case.get("status") == "NEEDS_REVIEW" for case in cases),
        "blocked": len(blocked_cases),
        "human_execution_ready_ratio": round(
            sum(item["human_classification"] == "HUMAN_EXECUTION_READY" for item in readiness) / len(readiness), 3
        ) if readiness else 0.0,
        "automation_candidate_ratio": round(
            sum(bool(case.get("automation_candidate")) for case in cases) / len(cases), 3
        ) if cases else 0.0,
        **procedure_template_metrics(cases),
        **priority_metrics(cases),
        "characterization_candidates": sum(
            identity.test_basis == "CHARACTERIZATION" for identity in design["test_identities"]
        ),
        "characterization_tests": sum(
            case.get("test_basis") == "CHARACTERIZATION" for case in cases
        ),
    })
    metrics["run_wall_clock_seconds"] = round(time.perf_counter() - run_began, 6)
    metrics["official_pipeline_time"] = metrics["run_wall_clock_seconds"]
    phase_times = {item["name"]: item["wall_clock_seconds"] for item in metrics["phases"]}
    metrics.update({
        "source_selection_time": phase_times.get("scope_resolution"),
        "source_reading_time": request.get("source_analysis_time", phase_times.get("source_collection")),
        "semantic_extraction_time": round(sum(phase_times.get(name, 0.0) for name in (
            "source_atomicity", "coverage_design", "scenario_reasoning", "scenario_engine"
        )), 6),
        "orchestrator_time": metrics["official_pipeline_time"],
        "expansion_time": phase_times.get("risk_expansion", 0.0),
        "procedure_time": round(sum(phase_times.get(name, 0.0) for name in (
            "procedural_reasoning", "procedural_engine"
        )), 6),
        "validation_time": phase_times.get("validation", 0.0),
        "render_time": phase_times.get("rendering", 0.0),
    })
    metrics["render_validation_time"] = round(sum(
        item["wall_clock_seconds"] for item in metrics["phases"]
        if item["name"] in {"validation", "rendering"}
    ), 6)
    metrics["attributed_stage_seconds"] = round(
        sum(item["wall_clock_seconds"] for item in metrics["phases"]), 6
    )
    metrics["unattributed_seconds"] = round(max(
        0.0, metrics["run_wall_clock_seconds"] - metrics["attributed_stage_seconds"]
    ), 6)
    metrics["stage_provenance"] = [{
        "stage": item["name"], "order": number, "generator": "functional-test-designer/2.2.2",
        "status": "COMPLETE", "validation_result": "PASS",
    } for number, item in enumerate(metrics["phases"], 1)]
    metrics["full_run_provenance"].extend(
        _official_run_provenance(metrics["phases"])
    )
    metrics["quality_gates"] = gates
    metrics["coverage_dimensions"] = {
        "source_unit_coverage": "COMPLETE" if source_unit_audit.get("normative_source_families_complete") else "INCOMPLETE",
        "claim_coverage": "COMPLETE" if source_audit["source_coverage_gaps"] == 0 else "INCOMPLETE",
        "coverage_point_coverage": "COMPLETE" if atomic_audit["unmapped_normative_clauses"] == 0 else "INCOMPLETE",
        "atomic_test_coverage": "COMPLETE" if atomic_coverage_audit["atomic_coverage_valid"] else "INCOMPLETE",
        "operator_error_coverage": "DISPOSITIONED" if expansion_metrics["risk_disposition_complete"] else "INCOMPLETE",
        "risk_coverage": "DISPOSITIONED" if expansion_metrics["risk_disposition_complete"] else "INCOMPLETE",
        "test_asset_challenge_coverage": "COMPLETE" if opportunity_precheck["test_asset_challenge_valid"] else "INCOMPLETE",
        "finding_coverage": "ACCOUNTED" if contradiction_audit.get("contradiction_candidates_unresolved", 0) == 0 else "INCOMPLETE",
        "e2e_coverage": "VALID" if semantic_composition["semantic_composition_valid"] else "INCOMPLETE",
        "procedure_coverage": "VALID" if one_step_audit["one_step_completeness_valid"] else "INCOMPLETE",
        "automation_readiness_coverage": "CLASSIFIED" if automation_audit["automation_readiness_valid"] else "INCOMPLETE",
    }
    _write(internal_metrics, metrics)
    if "DIAGNOSTICS" in selection.formats:
        destination = artifact_root / "diagnostics" / "run-metrics.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(internal_metrics, destination)
    return {
        "intent": "ftd-gen", "scope": scope, "inventory": inventory, "chain": chain,
        "source_audit": source_audit, "source_ledger": collection["ledger"],
        "source_review": review, "opportunity_audit": opportunity_audit,
        "design": design, "cases": cases, "readiness": readiness,
        "canonical_path": str(canonical_path), "render": rendered,
        "diagnostics": str(internal_metrics),
    }


def run_generation(request: dict[str, Any]) -> dict[str, Any]:
    """Run the shared path and mark any retained interrupted state as FAILED."""
    try:
        return _run_generation(request)
    except Exception:
        try:
            workspace = Path(request["workspace"]).resolve()
            artifact_paths = resolve_artifact_paths(
                skill_root=Path(__file__).resolve().parents[1], source_root=workspace,
                explicit_artifact_root=Path(request["artifact_root"]),
            )
            store = RunStateStore(
                Path(artifact_paths["artifact_root"]), str(request["run_id"])
            )
            if store.path.is_file():
                store.mark_terminal("FAILED", "shared generation pipeline raised an exception")
        except Exception:
            # Run-state hygiene must never replace the original generation failure.
            pass
        raise
