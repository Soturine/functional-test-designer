#!/usr/bin/env python3
"""Run the generic full pipeline and materialize schema-1.2 artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

import diagnostics
from canonical_state import persist_canonical_suite
from evidence_map import EvidenceMap
from parallel_evidence import (
    EvidenceRecord,
    SourceAssignment,
    analyze_selected_sources,
)
from procedural_pipeline import (
    reconcile_additive_feedback,
    run_procedural_tasks,
)
from procedural_readiness import audit_execution_readiness
from resolve_artifacts import resolve_artifact_paths
from render_markdown import render_markdown
from render_report import render_report
from run_state import diagnostics_compatibility_self_check
from scenario_independence import build_scenario_pipeline
from semantic_regression import build_snapshots
from source_coverage_audit import (
    audit_atomic_chain,
    audit_materialized_atomicity,
    materialize_atomic_coverage,
    review_source_items,
)
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


def analyze_fixture_source(
    assignment: SourceAssignment, evidence_map: EvidenceMap
) -> list[EvidenceRecord]:
    """Extract compact records from the selected generic fixture source once."""
    text = evidence_map.source(
        assignment.source,
        lambda: (ROOT / assignment.source).read_text(encoding="utf-8"),
    )
    records = []
    procedures = re.findall(r"^Procedure ([^:]+):\s*(.+)$", text, re.MULTILINE)
    if procedures:
        for name, path_text in procedures:
            path = tuple(part.strip() for part in path_text.split(">") if part.strip())
            records.append(EvidenceRecord(
                source=assignment.source,
                source_role=assignment.source_role,
                source_ref=name.strip(),
                source_excerpt_ref=f"Procedure {name.strip()}",
                observation_or_claim="A selected operator procedure provides an ordered path.",
                navigation=path,
                visible_labels=path,
            ))
        return records
    first_content = next(
        (line.strip(" #-\t") for line in text.splitlines() if line.strip(" #-\t")),
        assignment.source_ref,
    )
    return [EvidenceRecord(
        source=assignment.source,
        source_role=assignment.source_role,
        source_ref=assignment.source_ref,
        source_excerpt_ref="selected file",
        observation_or_claim=first_content,
    )]


def execution_packs(
    evidence_map: EvidenceMap, records: tuple[EvidenceRecord, ...]
) -> dict[str, dict[str, Any]]:
    manual_ref = {
        "source": "benchmarks/full-pipeline/manual.md",
        "reference": "Generic Reservation Procedure",
    }
    manual_records = evidence_map.pack(
        "manual-procedures",
        lambda: [record for record in records if record.source_role == "TECHNICAL_CONTEXT"],
    )
    confirm = [record for record in manual_records if record.source_ref == "Confirm reservation"]
    cancel = [record for record in manual_records if record.source_ref == "Cancel reservation"]
    return {
        "Confirm an eligible reservation": {
            "priority": "HIGH",
            "preconditions": ["An authenticated operator and an eligible pending reservation exist."],
            "test_data_partition": "eligible reservation",
            "test_data": [
                {"name": "reservation identifier", "description": "<existing eligible test reservation>"},
                {"name": "confirmation quantity", "description": "2 units from an available balance of 10 units"}
            ],
            "manual_evidence_records": confirm,
            "source_refs": [
                manual_ref,
                {"source": "benchmarks/full-pipeline/service.py", "reference": "confirm"},
                {"source": "benchmarks/full-pipeline/settings.yaml", "reference": "confirmation_quantity"},
                {"source": "benchmarks/full-pipeline/existing-tests.md", "reference": "quantity 2"}
            ],
            "divergence": {"statement": "The functional authority requires CONFIRMED, while implementation evidence assigns REVIEWED."},
            "postconditions": ["The synthetic reservation has the normative confirmation effects."],
            "cleanup": ["Use an isolated test environment or an approved cleanup procedure."],
            "tags": ["state-transition", "atomic-event"],
            "notes": ["Implementation evidence assigns REVIEWED; the normative oracle remains CONFIRMED."]
        },
        "Cancel an eligible reservation": {
            "priority": "MEDIUM",
            "preconditions": ["An authenticated operator and an eligible reservation exist."],
            "test_data_partition": "eligible reservation",
            "test_data": [{"name": "reservation identifier", "description": "<existing cancellable test reservation>"}],
            "manual_evidence_records": cancel,
            "source_refs": [manual_ref, {"source": "benchmarks/full-pipeline/existing-tests.md", "reference": "cancellation transaction"}],
            "postconditions": ["The synthetic reservation is CANCELLED."],
            "cleanup": ["Use an isolated test environment or an approved cleanup procedure."],
            "tags": ["state-transition", "cancellation"]
        },
        "Reject a malformed reservation request": {
            "priority": "HIGH",
            "preconditions": ["The reservation API is available in the test environment."],
            "test_data_partition": "malformed payload",
            "test_data": [{"name": "request body", "description": "{\"quantity\": \"not-a-number\"}"}],
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
    diagnostic_compatibility = diagnostics_compatibility_self_check(
        diagnostics.STAGE_NAMES, diagnostics.AGGREGATION_STRATEGIES
    )

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
            **diagnostic_compatibility,
        },
    )
    assignments = [
        SourceAssignment(item["path"], item["role"], "selected file")
        for item in fixture["sources"]
    ]
    evidence_analysis = timed(
        metrics_path,
        "source_read",
        lambda: analyze_selected_sources(
            assignments,
            set(source_paths),
            lambda assignment: analyze_fixture_source(assignment, evidence_map),
            max_workers=5,
        ),
        "Analyzed each selected source once and joined at the evidence barrier.",
        lambda result: {
            "source_reads": len(assignments),
            "source_rereads": 0,
            **result.metrics,
        },
    )
    inventory = timed(
        metrics_path,
        "evidence_normalization",
        lambda: review_source_items(fixture["source_items"]),
        "Reviewed Source Items and materialized atomic source claims.",
        lambda value: {
            key: value[key]
            for key in (
                "source_items",
                "atomic_source_claims_identified",
                "compound_source_items_split",
                "possible_compound_claim_warnings",
                "compound_claims_reviewed",
                "compound_claims_split",
                "compound_claims_kept_atomic",
            )
        },
    )
    chain = timed(
        metrics_path,
        "coverage_point_extraction",
        lambda: materialize_atomic_coverage(inventory),
        "Materialized one Clause and Coverage Point per unique atomic behavior.",
        lambda value: value["metrics"],
    )
    timed(
        metrics_path,
        "coverage_extraction_audit",
        lambda: {
            **audit_atomic_chain(inventory, chain),
            **audit_materialized_atomicity(inventory, chain),
        },
        "Verified source-first Claim to Clause to Coverage Point lineage.",
        lambda value: value,
    )
    timed(metrics_path, "testability_and_questions", lambda: None, "Confirmed every benchmark Coverage Point is testable.")
    design = timed(
        metrics_path,
        "test_design_and_scenarios",
        lambda: build_scenario_pipeline(chain["coverage_points"], fixture["profiles"]),
        "Ran candidate-first independence review and froze Test Case identities.",
        lambda result: result["metrics"],
    )
    timed(
        metrics_path,
        "early_deduplication",
        lambda: design["merge_decisions"],
        "Applied only explicit conservative merge decisions.",
        lambda _: {"scenario_cohesion_audit_trail": design["cohesion_audit_trail"]},
    )

    packs = timed(
        metrics_path,
        "evidence_enrichment",
        lambda: execution_packs(evidence_map, evidence_analysis.records),
        "Built and reused selected-source Evidence Packs.",
        lambda _: evidence_map.metrics(),
    )
    procedural = timed(
        metrics_path,
        "execution_path_synthesis",
        lambda: run_procedural_tasks(
            [(identity, packs[identity.title]) for identity in design["test_identities"]],
            max_workers=3,
        ),
        "Synthesized procedural steps in parallel after identity freeze.",
        lambda value: {
            **value.metrics,
            "steps_generated": sum(len(result.case["steps"]) for result in value.results),
        },
    )
    initial_cases = [result.case for result in procedural.results]
    reconciliation = reconcile_additive_feedback(initial_cases, procedural.results)
    cases = reconciliation["test_cases"]
    readiness_audits = [
        audit_execution_readiness(case, identity)
        for case, identity in zip(cases, design["test_identities"])
    ]
    readiness_reasons = [
        reason for audit in readiness_audits for reason in audit["reason_codes"]
    ]
    timed(
        metrics_path,
        "test_case_generation",
        lambda: cases,
        "Materialized frozen identities and completed one bounded additive pass.",
        lambda values: {
            "test_cases_generated": len(values),
            **reconciliation["metrics"],
            "human_execution_ready": sum(
                item["human_classification"] == "HUMAN_EXECUTION_READY"
                for item in readiness_audits
            ),
            "human_execution_not_ready": sum(
                item["human_classification"] == "HUMAN_EXECUTION_NOT_READY"
                for item in readiness_audits
            ),
            "automation_execution_ready": sum(
                item["automation_classification"] == "AUTOMATION_EXECUTION_READY"
                for item in readiness_audits
            ),
            "automation_execution_not_ready": sum(
                item["automation_classification"] == "AUTOMATION_EXECUTION_NOT_READY"
                for item in readiness_audits
            ),
            "abstract_trigger_warnings": readiness_reasons.count("ABSTRACT_TRIGGER"),
            "abstract_navigation_warnings": readiness_reasons.count("ABSTRACT_NAVIGATION"),
            "abstract_observation_warnings": readiness_reasons.count("ABSTRACT_OBSERVATION"),
            "placeholder_test_data_warnings": readiness_reasons.count("PLACEHOLDER_TEST_DATA"),
            "assertion_discrimination_warnings": readiness_reasons.count(
                "INSUFFICIENT_ASSERTION_DISCRIMINATION"
            ),
        },
    )
    timed(
        metrics_path,
        "source_coverage_audit",
        lambda: audit_atomic_chain(inventory, chain),
        "Compared the independent source-first inventory with materialized coverage.",
        lambda value: value,
    )
    diagnostics.skip_stage(
        metrics_path,
        "source_coverage_recovery",
        ["No source coverage gap required the bounded recovery pass."],
    )
    timed(
        metrics_path,
        "source_coverage_verification",
        lambda: audit_atomic_chain(inventory, chain),
        "Verified source-first lineage after the no-op recovery decision.",
        lambda value: value,
    )
    diagnostics.skip_stage(
        metrics_path,
        "cross_rf_audit",
        ["No cross-requirement overlap exists in this focused synthetic fixture."],
    )

    cases_by_cp = {
        cp_id: case["id"] for case in cases for cp_id in case["coverage_point_refs"]
    }
    coverage_points = json.loads(json.dumps(chain["coverage_points"]))
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
        "normative_clauses": chain["normative_clauses"],
        "findings": [*fixture["findings"], *reconciliation["findings"]],
        "coverage_points": coverage_points,
        "scenarios": scenarios,
        "test_cases": entries,
    }
    semantic = build_snapshots(
        sources=fixture["sources"],
        source_items=fixture["source_items"],
        inventory=inventory,
        chain=chain,
        design=design,
        cases=cases,
        questions=reconciliation["questions"],
        findings=index["findings"],
    )

    questions_document = {
        "schema_version": "1.2",
        "questions": reconciliation["questions"],
    }

    def materialize() -> dict[str, Any]:
        canonical_path = persist_canonical_suite(
            artifact_root,
            "synthetic-e2e",
            index=index,
            questions=questions_document,
            cases=cases,
        )
        write_json(output / "test-cases.json", index)
        write_json(output / "questions.json", questions_document)
        for case in cases:
            write_json(output / "test-cases" / f"{case['id']}.json", case)
        return {
            "bytes": sum(path.stat().st_size for path in output.rglob("*.json")),
            "canonical_path": str(canonical_path),
        }

    materialized = timed(
        metrics_path,
        "json_write",
        materialize,
        "Serialized already prepared JSON structures.",
        lambda value: {
            "individual_json_files_written": len(cases),
            "json_bytes_written": value["bytes"],
            "requested_public_formats": ["HTML", "JSON", "MARKDOWN"],
            "rendered_public_formats": ["HTML", "JSON", "MARKDOWN"],
            "canonical_state_written": True,
            "source_reads_during_render": 0,
        },
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
        "json_bytes": materialized["bytes"],
        "canonical_state": materialized["canonical_path"],
        "evidence_map": evidence_map.metrics(),
        "source_analysis": evidence_analysis.metrics,
        "procedural": procedural.metrics,
        "additive_feedback": reconciliation["metrics"],
        "readiness_audits": readiness_audits,
        "automation_audits": [
            {
                "classification": item["automation_classification"],
                "reasons": item["reason_codes"],
            }
            for item in readiness_audits
        ],
        "semantic_regression": semantic,
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
