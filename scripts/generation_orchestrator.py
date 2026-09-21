#!/usr/bin/env python3
"""Enforced shared ftd-gen path from scope lock through canonical projections."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from canonical_state import OutputSelection, persist_canonical_suite, render_selected_outputs
from procedural_pipeline import reconcile_additive_feedback, run_procedural_tasks
from procedural_readiness import align_public_status, audit_execution_readiness
from resolve_artifacts import resolve_artifact_paths
from resolve_scope import resolve_selected_scope
from run_state import RunStateStore, source_manifest
from scenario_independence import build_scenario_pipeline
from risk_coverage import audit_flow_coverage, audit_risk_matrix
from scenario_opportunities import audit_scenario_opportunities
from source_accounting import (
    audit_source_review_independence, build_source_ledger, read_telemetry,
)
from test_asset_inventory import audit_test_asset_inventory
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


class GenerationContractError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_generation(request: dict[str, Any]) -> dict[str, Any]:
    """Run every mandatory gate; precomputed free-form handoffs are not accepted."""
    run_began = time.perf_counter()
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
    internal_metrics = store.run_dir / "orchestration-metrics.json"
    metrics: dict[str, Any] = {
        "schema_version": "1", "diagnostic": bool(request.get("diagnostic", False)),
        "started_at": _now(), "timing_available": True, "phases": [],
        "checkpoint_events": [], **read_telemetry(request),
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
            metrics["attributed_stage_seconds"] = round(
                sum(item["wall_clock_seconds"] for item in metrics["phases"]), 6
            )
            metrics["unattributed_seconds"] = round(max(
                0.0, metrics["run_wall_clock_seconds"] - metrics["attributed_stage_seconds"]
            ), 6)
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
    metrics.update({
        "source_files_assigned": collection["files"],
        "source_records_received": collection["records"],
        **collection["ledger"]["metrics"],
    })
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
            **audit_test_asset_inventory(discovered, list(assets.get("classifications", []))),
            **audit_risk_matrix(
                request["risk_conditions"], request["opportunities"], question_ids=question_ids
            ),
            **audit_flow_coverage(request["use_case_flows"], request["opportunities"]),
        }

    opportunity_precheck = phase("scenario_reasoning", review_opportunities)
    store.save("OPPORTUNITY_AUDIT_COMPLETE", {
        "risk_conditions_reviewed": opportunity_precheck["risk_conditions_reviewed"],
        "use_case_flows_reviewed": opportunity_precheck["use_case_flows_reviewed"],
    }, hashes)
    metrics["checkpoint_events"].append(
        {"checkpoint": "OPPORTUNITY_AUDIT_COMPLETE", "event": "created"}
    )
    design = phase(
        "scenario_engine",
        lambda: build_scenario_pipeline(chain["coverage_points"], request["scenario_profiles"]),
    )
    scenario_ids = {item["id"] for item in design["scenarios"]}
    finding_ids = {str(item["id"]) for item in request.get("findings", [])}
    opportunity_audit = audit_scenario_opportunities(
        request["selected_evidence"], request["opportunities"], scenario_ids=scenario_ids,
        finding_ids=finding_ids, question_ids=question_ids,
    )
    store.save("SCENARIOS_FROZEN", {
        "scenario_ids": sorted(scenario_ids), "test_identity_ids": [item.id for item in design["test_identities"]],
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "SCENARIOS_FROZEN", "event": "created"})

    packs = request["evidence_packs"]
    tasks = []
    for identity in design["test_identities"]:
        if identity.id not in packs:
            raise GenerationContractError(f"Frozen identity {identity.id} has no Evidence Pack")
        tasks.append((identity, packs[identity.id]))
    procedural = phase("procedural_reasoning", lambda: run_procedural_tasks(tasks))
    reconciliation = phase(
        "procedural_engine",
        lambda: reconcile_additive_feedback([item.case for item in procedural.results], procedural.results),
    )
    cases = reconciliation["test_cases"]
    readiness = []
    for case, identity in zip(cases, design["test_identities"]):
        pack = packs[identity.id]
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
        readiness.append(audit)
    store.save("PROCEDURAL_COMPLETE", {
        "case_ids": [item["id"] for item in cases],
        "human_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_READY" for item in readiness),
    }, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "PROCEDURAL_COMPLETE", "event": "created"})

    cases_by_cp = {cp: case["id"] for case in cases for cp in case["coverage_point_refs"]}
    points = json.loads(json.dumps(chain["coverage_points"]))
    for point in points:
        point["target_refs"] = [cases_by_cp[point["id"]]]
    entries = [{
        "id": case["id"], "title": case["title"], "status": case["status"],
        "requirement_refs": case["requirement_refs"], "scenario_refs": case["scenario_refs"],
        "coverage_point_refs": case["coverage_point_refs"],
        "file": f"test-cases/{case['id']}.json", "markdown_file": f"test-cases-md/{case['id']}.md",
    } for case in cases]
    findings = [*request.get("findings", []), *reconciliation["findings"]]
    questions = [*request.get("questions", []), *reconciliation["questions"]]
    index = {
        "schema_version": "1.2", "generated_at": request.get("generated_at", _now()),
        "sources": request["sources"], "requirements": request["requirements"],
        "normative_clauses": chain["normative_clauses"], "findings": findings,
        "coverage_points": points,
        "scenarios": [{
            "id": item["id"], "title": item["title"], "type": item["type"],
            "requirement_refs": item["requirement_refs"],
        } for item in design["scenarios"]],
        "test_cases": entries,
    }
    questions_document = {"schema_version": "1.2", "questions": questions}
    canonical_path = phase("validation", lambda: persist_canonical_suite(
        artifact_root, run_id, index=index, questions=questions_document, cases=cases,
    ))
    store.save("VALIDATED", {"canonical_suite": canonical_path.name}, hashes)
    metrics["checkpoint_events"].append({"checkpoint": "VALIDATED", "event": "created"})
    rendered = phase("rendering", lambda: render_selected_outputs(canonical_path, artifact_root, selection))

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
        **opportunity_precheck, **opportunity_audit, **design["metrics"], **procedural.metrics,
        "human_execution_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_READY" for item in readiness),
        "human_execution_not_ready": sum(item["human_classification"] == "HUMAN_EXECUTION_NOT_READY" for item in readiness),
        "automation_execution_ready": sum(item["automation_classification"] == "AUTOMATION_EXECUTION_READY" for item in readiness),
        "automation_execution_not_ready": sum(item["automation_classification"] == "AUTOMATION_EXECUTION_NOT_READY" for item in readiness),
        "cases_missing_setup_acquisition": sum(
            "MISSING_SETUP_ACQUISITION" in item["reason_codes"] for item in readiness
        ),
        "cases_missing_procedural_provenance": sum(
            "MISSING_PROCEDURAL_PROVENANCE" in item["reason_codes"] for item in readiness
        ),
        "finished_at": _now(), "rendered_public_formats": rendered["rendered_public_formats"],
    })
    metrics["run_wall_clock_seconds"] = round(time.perf_counter() - run_began, 6)
    metrics["attributed_stage_seconds"] = round(
        sum(item["wall_clock_seconds"] for item in metrics["phases"]), 6
    )
    metrics["unattributed_seconds"] = round(max(
        0.0, metrics["run_wall_clock_seconds"] - metrics["attributed_stage_seconds"]
    ), 6)
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
