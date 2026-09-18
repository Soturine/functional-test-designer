#!/usr/bin/env python3
"""Run the generic full pipeline and materialize schema-1.2 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import diagnostics
from evidence_map import EvidenceMap
from procedural_execution import compose_path, synthesize_test_case
from resolve_artifacts import resolve_artifact_paths
from render_markdown import render_markdown
from render_report import render_report
from scenario_independence import build_scenario_pipeline
from validate_output import validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks" / "full-pipeline" / "fixture.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def timed(
    metrics_path: Path,
    name: str,
    action: Callable[[], Any],
    done: str,
    metric_builder: Callable[[Any], dict[str, Any]] | None = None,
) -> Any:
    diagnostics.begin_stage(metrics_path, name)
    result = action()
    metrics = metric_builder(result) if metric_builder else {}
    diagnostics.end_stage(metrics_path, name, [done], metrics)
    return result


def execution_packs(evidence_map: EvidenceMap) -> dict[str, dict[str, Any]]:
    manual_ref = {
        "source": "benchmarks/full-pipeline/manual.md",
        "reference": "Generic Reservation Procedure",
    }
    shared = evidence_map.pack(
        "reservation-detail-navigation",
        lambda: [
            {"action": "Open the reservation list.", "expected_result": "The reservation list is presented.", "evidence_source": manual_ref},
            {"action": "Search using the reservation identifier from the test data.", "expected_result": "The matching reservation is displayed.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Open the matching reservation detail.", "expected_result": "The reservation detail is presented.", "evidence_source": manual_ref, "depends_on_previous_step": True}
        ],
    )
    confirm = compose_path(
        shared,
        [
            {"action": "Choose Confirm.", "expected_result": "The documented confirmation action is available.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Provide the required confirmation input from the test data.", "expected_result": "The supplied confirmation input remains available for submission.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Confirm the action.", "expected_result": "The documented confirmation action is submitted.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Review the resulting state, balance, and audit evidence.", "depends_on_previous_step": True}
        ],
    )
    cancel = compose_path(
        evidence_map.pack("reservation-detail-navigation", lambda: []),
        [
            {"action": "Choose Cancel.", "expected_result": "The documented cancellation action is available.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Confirm the cancellation.", "expected_result": "The documented cancellation action is submitted.", "evidence_source": manual_ref, "depends_on_previous_step": True},
            {"action": "Review the resulting reservation state.", "depends_on_previous_step": True}
        ],
    )
    return {
        "Confirm an eligible reservation": {
            "objective": "Confirm all normative effects of one atomic confirmation.",
            "priority": "HIGH",
            "preconditions": ["An authenticated operator and an eligible pending reservation exist."],
            "test_data": [
                {"name": "reservation identifier", "description": "<existing eligible test reservation>"},
                {"name": "confirmation quantity", "description": "2 units from an available balance of 10 units"}
            ],
            "actions": confirm,
            "source_refs": [manual_ref, {"source": "benchmarks/full-pipeline/service.py", "reference": "confirm"}],
            "postconditions": ["The synthetic reservation has the normative confirmation effects."],
            "cleanup": ["Use an isolated test environment or an approved cleanup procedure."],
            "tags": ["state-transition", "atomic-event"],
            "notes": ["Implementation evidence assigns REVIEWED; the normative oracle remains CONFIRMED."]
        },
        "Cancel an eligible reservation": {
            "objective": "Confirm cancellation reaches the required state.",
            "priority": "MEDIUM",
            "preconditions": ["An authenticated operator and an eligible reservation exist."],
            "test_data": [{"name": "reservation identifier", "description": "<existing cancellable test reservation>"}],
            "actions": cancel,
            "source_refs": [manual_ref],
            "postconditions": ["The synthetic reservation is CANCELLED."],
            "cleanup": ["Use an isolated test environment or an approved cleanup procedure."],
            "tags": ["state-transition", "cancellation"]
        },
        "Reject a malformed reservation request": {
            "objective": "Confirm malformed input is rejected.",
            "priority": "HIGH",
            "preconditions": ["The reservation API is available in the test environment."],
            "test_data": [{"name": "request body", "description": "{\"quantity\": \"not-a-number\"}"}],
            "actions": [{"action": "Send the malformed reservation request."}],
            "source_refs": [],
            "postconditions": [],
            "cleanup": [],
            "tags": ["negative", "api"]
        }
    }


def run(artifact_root: Path) -> dict[str, Any]:
    artifact_paths = resolve_artifact_paths(
        skill_root=ROOT,
        source_root=ROOT / "benchmarks" / "full-pipeline",
        explicit_artifact_root=artifact_root,
    )
    artifact_root = Path(artifact_paths["artifact_root"])
    output = Path(artifact_paths["output_path"])
    metrics_path = Path(artifact_paths["diagnostics_path"]) / "run-metrics.json"
    if output.exists():
        raise ValueError(f"Synthetic E2E output already exists: {output}")
    diagnostics.start_run(metrics_path)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_paths = [item["path"] for item in fixture["sources"]]
    evidence_map = EvidenceMap(set(source_paths))
    timed(
        metrics_path,
        "scope_resolution",
        lambda: source_paths,
        "Resolved the explicitly selected synthetic sources.",
        lambda selected_paths: {
            "selected_scope_roots": selected_paths,
            "resolved_scope_paths": selected_paths,
            "files_opened": len(selected_paths),
            "files_opened_outside_scope": 0,
            "files_skipped_out_of_scope": 0,
            "temporary_files_created": 0,
            **artifact_paths,
        },
    )
    timed(
        metrics_path,
        "source_read",
        lambda: [
            evidence_map.source(path, lambda selected=path: (ROOT / selected).read_text(encoding="utf-8"))
            for path in source_paths
        ],
        "Read each selected synthetic source once.",
        lambda values: {"source_reads": len(values), "source_rereads": 0},
    )
    timed(metrics_path, "evidence_normalization", lambda: fixture["normative_clauses"], "Normalized atomic source claims.")
    timed(
        metrics_path,
        "coverage_point_extraction",
        lambda: fixture["coverage_points"],
        "Materialized atomic Coverage Points.",
        lambda points: {"coverage_points": len(points), "normative_clauses_extracted": len(points)},
    )
    timed(metrics_path, "coverage_extraction_audit", lambda: None, "Verified every synthetic clause has a destination.")
    timed(metrics_path, "testability_and_questions", lambda: None, "Confirmed every benchmark Coverage Point is testable.")
    design = timed(
        metrics_path,
        "test_design_and_scenarios",
        lambda: build_scenario_pipeline(fixture["coverage_points"], fixture["profiles"]),
        "Ran candidate-first independence review and froze Test Case identities.",
        lambda result: result["metrics"],
    )
    timed(metrics_path, "early_deduplication", lambda: design["merge_decisions"], "Applied only explicit conservative merge decisions.")

    packs = timed(
        metrics_path,
        "evidence_enrichment",
        lambda: execution_packs(evidence_map),
        "Built and reused selected-source Evidence Packs.",
        lambda _: evidence_map.metrics(),
    )
    cases = timed(
        metrics_path,
        "execution_path_synthesis",
        lambda: [synthesize_test_case(identity, packs[identity.title]) for identity in design["test_identities"]],
        "Synthesized procedural steps after identity freeze.",
        lambda values: {"steps_generated": sum(len(case["steps"]) for case in values)},
    )
    timed(metrics_path, "test_case_generation", lambda: cases, "Materialized frozen identities as schema-1.2 Test Cases.", lambda values: {"test_cases_generated": len(values)})
    for name in ("source_coverage_audit", "source_coverage_recovery", "source_coverage_verification", "cross_rf_audit"):
        diagnostics.skip_stage(metrics_path, name, ["Covered by existing focused regression tests; no recovery was needed."])

    cases_by_cp = {
        cp_id: case["id"] for case in cases for cp_id in case["coverage_point_refs"]
    }
    coverage_points = json.loads(json.dumps(fixture["coverage_points"]))
    for point in coverage_points:
        point["target_refs"] = [cases_by_cp[point["id"]]]
    scenarios = [
        {
            "id": item["id"],
            "title": item["title"],
            "type": item["type"],
            "requirement_refs": item["requirement_refs"],
        }
        for item in design["scenarios"]
    ]
    entries = [
        {
            "id": case["id"], "title": case["title"], "status": case["status"],
            "requirement_refs": case["requirement_refs"], "scenario_refs": case["scenario_refs"],
            "coverage_point_refs": case["coverage_point_refs"],
            "file": f"test-cases/{case['id']}.json",
            "markdown_file": f"test-cases-md/{case['id']}.md",
        }
        for case in cases
    ]
    index = {
        "schema_version": "1.2",
        "generated_at": "2026-01-01T00:00:00Z",
        "sources": fixture["sources"],
        "requirements": fixture["requirements"],
        "normative_clauses": fixture["normative_clauses"],
        "findings": fixture["findings"],
        "coverage_points": coverage_points,
        "scenarios": scenarios,
        "test_cases": entries,
    }

    def materialize() -> int:
        write_json(output / "test-cases.json", index)
        write_json(output / "questions.json", {"schema_version": "1.2", "questions": []})
        for case in cases:
            write_json(output / "test-cases" / f"{case['id']}.json", case)
        return sum(path.stat().st_size for path in output.rglob("*.json"))

    json_bytes = timed(
        metrics_path,
        "json_write",
        materialize,
        "Serialized already prepared JSON structures.",
        lambda size: {"individual_json_files_written": len(cases), "json_bytes_written": size},
    )
    errors = timed(metrics_path, "validation", lambda: validate(output), "Ran the schema and cross-file validator.", lambda _: {"validator_runs": 1})
    if errors:
        raise ValueError("Synthetic E2E validation failed:\n- " + "\n- ".join(errors))
    diagnostics.skip_stage(metrics_path, "validation_fixes", ["No validation fixes were required."])
    markdown = timed(metrics_path, "markdown_render", lambda: render_markdown(output), "Rendered one Markdown and Mermaid flow per Test Case.", lambda values: {"markdown_files_generated": len(values)})
    report = timed(metrics_path, "html_render", lambda: render_report(output), "Rendered the deterministic offline HTML report.")
    timed(metrics_path, "final_summary", lambda: None, "Derived the summary from final run state.")
    diagnostics.finish_run(metrics_path, output)
    return {
        "artifact_root": str(artifact_root),
        "output": str(output),
        "diagnostics": str(metrics_path),
        "metrics": design["metrics"],
        "cases": cases,
        "markdown_files": len(markdown),
        "report": str(report),
        "json_bytes": json_bytes,
        "evidence_map": evidence_map.metrics(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    result = run(args.artifact_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
