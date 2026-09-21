#!/usr/bin/env python3
"""Record lightweight, privacy-safe execution diagnostics for a skill run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cross_rf_audit import audit_cross_rf  # noqa: E402
from execution_quality import step_distribution  # noqa: E402
from requirement_groups import requirement_group_map  # noqa: E402
from source_coverage_audit import per_requirement_summary, possible_compound_claims  # noqa: E402


STAGE_NAMES = (
    "scope_resolution",
    "source_read",
    "evidence_normalization",
    "coverage_point_extraction",
    "coverage_extraction_audit",
    "testability_and_questions",
    "test_design_and_scenarios",
    "early_deduplication",
    "evidence_enrichment",
    "execution_path_synthesis",
    "test_case_generation",
    "source_coverage_audit",
    "source_coverage_recovery",
    "source_coverage_verification",
    "cross_rf_audit",
    "json_write",
    "validation",
    "validation_fixes",
    "markdown_render",
    "html_render",
    "final_summary",
)

DIAGNOSTIC_PHASES = (
    "scope_resolution", "source_inventory", "source_collection",
    "evidence_reconciliation", "source_atomicity", "coverage_design",
    "scenario_reasoning", "scenario_engine", "procedural_reasoning",
    "procedural_engine", "validation", "rendering", "integration_export",
)

# Stable conceptual phases make legacy fine-grained timers comparable to v2.1 runs.
STAGE_PHASES = {
    "scope_resolution": "scope_resolution",
    "source_read": "source_collection",
    "evidence_normalization": "source_atomicity",
    "coverage_point_extraction": "coverage_design",
    "coverage_extraction_audit": "coverage_design",
    "testability_and_questions": "coverage_design",
    "test_design_and_scenarios": "scenario_reasoning",
    "early_deduplication": "scenario_engine",
    "evidence_enrichment": "evidence_reconciliation",
    "execution_path_synthesis": "procedural_reasoning",
    "test_case_generation": "procedural_engine",
    "source_coverage_audit": "coverage_design",
    "source_coverage_recovery": "coverage_design",
    "source_coverage_verification": "coverage_design",
    "cross_rf_audit": "scenario_engine",
    "json_write": "integration_export",
    "validation": "validation",
    "validation_fixes": "validation",
    "markdown_render": "rendering",
    "html_render": "rendering",
    "final_summary": "integration_export",
}

SCOPE_PROOF_METRICS = (
    "selected_scope_roots",
    "resolved_scope_paths",
    "files_opened",
    "files_opened_outside_scope",
    "files_skipped_out_of_scope",
    "source_reads",
    "source_rereads",
    "temporary_files_created",
)

AGGREGATION_STRATEGIES = {
    "selected_scope_roots": "set",
    "resolved_scope_paths": "set",
    "files_opened": "last",
    "files_opened_outside_scope": "last",
    "files_skipped_out_of_scope": "last",
    "source_reads": "sum",
    "source_rereads": "sum",
    "temporary_files_created": "sum",
    "normative_clauses_extracted": "last",
    "normative_clauses_mapped": "last",
    "unmapped_normative_clauses": "last",
    "coverage_points": "last",
    "testable_coverage_points": "last",
    "scenario_candidates": "last",
    "scenario_candidates_before_merge": "last",
    "scenario_merge_candidates": "last",
    "scenario_merges_applied": "last",
    "scenario_cohesion_decisions": "last",
    "scenarios_after_merge": "last",
    "multi_cp_scenarios": "last",
    "traceable_assertions": "last",
    "possible_scenario_overcompression_warnings": "last",
    "scenarios_after_dedup": "last",
    "independent_scenarios_preserved": "last",
    "semantic_duplicates_removed": "last",
    "test_cases_generated": "last",
    "steps_generated": "last",
    "individual_json_files_written": "last",
    "json_bytes_written": "last",
    "validator_runs": "sum",
    "validation_fix_rounds": "sum",
    "markdown_files_generated": "last",
    "artifact_root": "last",
    "output_path": "last",
    "diagnostics_path": "last",
    "artifact_root_source": "last",
    "detailed_execution_evidence_available": "last",
    "source_claims_identified": "last",
    "source_claims_represented": "last",
    "source_coverage_gaps": "last",
    "recovered_source_gaps": "last",
    "source_items": "last",
    "atomic_source_claims_identified": "last",
    "atomic_claims_deduplicated": "last",
    "compound_source_items_split": "last",
    "possible_compound_claim_warnings": "last",
    "compound_claims_reviewed": "last",
    "compound_claims_split": "last",
    "compound_claims_kept_atomic": "last",
    "referenced_normative_rules": "last",
    "referenced_rules_resolved_in_scope": "last",
    "referenced_rules_unresolved": "last",
    "applicable_rule_claims": "last",
    "applicable_rule_claims_represented": "last",
    "evidence_map_hits": "sum",
    "evidence_map_misses": "sum",
    "source_files_opened_once": "last",
    "source_files_reopened": "sum",
    "source_reread_reasons": "last",
    "evidence_records_reused": "sum",
    "tc_generation_reuse_hits": "sum",
    "source_analysis_workers_started": "last",
    "source_analysis_workers_completed": "last",
    "source_analysis_max_concurrency": "last",
    "source_files_assigned": "last",
    "source_files_reused_from_evidence_map": "last",
    "duplicate_source_reads": "last",
    "evidence_records_generated": "last",
    "evidence_records_by_role": "last",
    "source_analysis_barrier_wait_seconds": "last",
    "stage_wall_clock_seconds": "sum",
    "aggregate_worker_seconds": "sum",
    "source_analysis_groups": "last",
    "source_analysis_group_barriers": "last",
    "source_analysis_order_constraints": "last",
    "source_analysis_parallel_groups": "last",
    "source_analysis_serialized_groups": "last",
    "source_parallelism_available": "last",
    "source_parallelism_used": "last",
    "source_parallelism_fallback_reason": "last",
    "varied_execution_paths_available": "last",
    "possible_step_underspecification_warnings": "last",
    "hidden_subtest_warnings": "last",
    "procedural_tasks_enqueued": "last",
    "procedural_tasks_completed": "last",
    "procedural_max_concurrency": "last",
    "procedure_ready": "last",
    "procedure_gaps": "last",
    "procedural_ambiguities": "last",
    "procedural_divergences": "last",
    "independent_branches_detected": "last",
    "unsupported_steps": "last",
    "new_tc_candidates": "last",
    "new_tcs_appended": "last",
    "pending_additive_follow_up": "last",
    "procedural_wall_clock_seconds": "last",
    "procedural_aggregate_worker_seconds": "last",
    "procedural_parallelism_available": "last",
    "procedural_parallelism_used": "last",
    "procedural_parallelism_fallback_reason": "last",
    "diagnostics_compatibility_checked": "last",
    "diagnostics_stage_count": "last",
    "diagnostics_metric_count": "last",
    "human_execution_ready": "last",
    "human_execution_not_ready": "last",
    "automation_execution_ready": "last",
    "automation_execution_not_ready": "last",
    "abstract_trigger_warnings": "last",
    "abstract_navigation_warnings": "last",
    "abstract_observation_warnings": "last",
    "placeholder_test_data_warnings": "last",
    "assertion_discrimination_warnings": "last",
    "requested_public_formats": "last",
    "rendered_public_formats": "last",
    "canonical_state_written": "last",
    "source_reads_during_render": "sum",
    "clarifications_applied": "last",
    "clarification_conflicts": "last",
    "mcp_preview_creates": "last",
    "mcp_preview_updates": "last",
    "mcp_preview_unchanged": "last",
    "mcp_preview_skipped": "last",
    "mcp_preview_conflicts": "last",
    "external_writes": "sum",
    "scenario_cohesion_audit_trail": "last",
    "materialized_compound_items_reviewed": "last",
    "materialized_compound_items_unreviewed": "last",
    "one_step_cases": "last",
    "legitimate_one_step_cases": "last",
    "path_compression_warnings": "last",
    "generic_observation_warnings": "last",
    "missing_record_acquisition_rule": "last",
    "missing_execution_surface": "last",
    "missing_intermediate_observation": "last",
    "selected_evidence_behaviors": "last",
    "scenario_opportunities": "last",
    "opportunity_dispositions": "last",
    "divergence_opportunities_linked": "last",
    "test_asset_behaviors_accounted": "last",
    "cross_cutting_opportunities": "last",
    "unaccounted_selected_evidence_behaviors": "last",
}

ABSTRACT_ACTION_PATTERNS = (
    r"\bexecute (?:the )?(?:complete )?flow\b",
    r"\bcomplete (?:the )?(?:process|operation|cycle)\b",
    r"\bvalidate (?:the )?functionality\b",
    r"\bperform (?:the )?(?:process|operation)\b",
    r"\bexecutar (?:o )?fluxo\b",
    r"\brealizar (?:o )?processo\b",
    r"\bcompletar (?:a )?opera[cç][aã]o\b",
    r"\bvalidar (?:a )?funcionalidade\b",
    r"\bfazer (?:a )?(?:sa[ií]da|entrada)\b",
    r"\bprocessar corretamente\b",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def elapsed(started_at: str, finished_at: str) -> float:
    seconds = (parse_timestamp(finished_at) - parse_timestamp(started_at)).total_seconds()
    return round(max(0.0, seconds), 6)


def read_document(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage(document: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAGE_NAMES:
        raise ValueError(f"Unknown stage {name!r}; expected one of: {', '.join(STAGE_NAMES)}")
    for item in document.get("stages", []):
        if item.get("name") == name:
            return item
    raise ValueError(f"Stage {name!r} is absent from the diagnostics document")


def start_run(path: Path) -> dict[str, Any]:
    if path.exists():
        raise ValueError(f"Diagnostics file already exists: {path}")
    started_at = timestamp()
    document = {
        "schema_version": "1.2",
        "run": {
            "diagnostic": True,
            "started_at": started_at,
            "finished_at": None,
            "total_elapsed_seconds": None,
            "timing_available": True,
        },
        "stages": [
            {
                "name": name,
                "phase": STAGE_PHASES[name],
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": None,
                "timing_available": False,
                "status": "pending",
                "what_was_done": [],
                "metrics": {},
                "notes": [],
            }
            for name in STAGE_NAMES
        ],
        "totals": {},
        "scope_proof": {},
        "warnings": [],
        "phase_contract": list(DIAGNOSTIC_PHASES),
        "observed_bottlenecks": [],
        "optimization_candidates": [],
    }
    write_document(path, document)
    return document


def begin_stage(path: Path, name: str) -> dict[str, Any]:
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "pending":
        raise ValueError(f"Stage {name!r} cannot begin from status {item['status']!r}")
    item["started_at"] = timestamp()
    item["status"] = "running"
    write_document(path, document)
    return document


def parse_metric(raw: str) -> tuple[str, Any]:
    if "=" not in raw:
        raise ValueError(f"Metric must use key=value syntax: {raw!r}")
    key, value = raw.split("=", 1)
    if not key.strip():
        raise ValueError("Metric key cannot be empty")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key.strip(), parsed


def end_stage(
    path: Path,
    name: str,
    done: list[str],
    metrics: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    if not 1 <= len(done) <= 5:
        raise ValueError("what_was_done requires between 1 and 5 short entries")
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "running" or not item.get("started_at"):
        raise ValueError(f"Stage {name!r} must be running before it can end")
    finished_at = timestamp()
    item.update(
        {
            "finished_at": finished_at,
            "elapsed_seconds": elapsed(item["started_at"], finished_at),
            "timing_available": True,
            "status": status,
            "what_was_done": done,
            "metrics": metrics or {},
            "notes": notes or [],
        }
    )
    write_document(path, document)
    return document


def skip_stage(path: Path, name: str, done: list[str], notes: list[str] | None = None) -> dict[str, Any]:
    if not 1 <= len(done) <= 5:
        raise ValueError("what_was_done requires between 1 and 5 short entries")
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "pending":
        raise ValueError(f"Stage {name!r} cannot be skipped from status {item['status']!r}")
    item.update(
        {
            "status": "skipped",
            "what_was_done": done,
            "notes": notes or [],
        }
    )
    write_document(path, document)
    return document


def output_totals(output_dir: Path | None) -> dict[str, Any]:
    if output_dir is None:
        return {}
    index = read_document(output_dir / "test-cases.json")
    questions = read_document(output_dir / "questions.json").get("questions", [])
    cases = [read_document(output_dir / entry["file"]) for entry in index.get("test_cases", [])]
    statuses = Counter(case.get("status") for case in cases)
    source_roles = {
        source.get("path"): source.get("role")
        for source in index.get("sources", [])
        if isinstance(source, dict)
    }
    case_roles = [
        {
            source_roles.get(ref.get("source"))
            for ref in case.get("source_refs", [])
            if isinstance(ref, dict) and source_roles.get(ref.get("source"))
        }
        for case in cases
    ]
    step_counts = [len(case.get("steps", [])) for case in cases]
    abstract_actions = sum(
        any(re.search(pattern, str(step.get("action", "")), re.IGNORECASE) for pattern in ABSTRACT_ACTION_PATTERNS)
        for case in cases
        for step in case.get("steps", [])
        if isinstance(step, dict)
    )
    concrete_data_cases = sum(
        any(
            "<" not in str(item.get("description", ""))
            and bool(re.search(r"\d|`|\b[A-Z][A-Z0-9_]{1,}\b", str(item.get("description", ""))))
            for item in case.get("test_data", [])
            if isinstance(item, dict)
        )
        for case in cases
    )
    path_question_count = sum(
        bool(
            re.search(
                r"\b(?:path|route|menu|button|endpoint|caminho|rota|bot[aã]o|como executar)\b",
                str(question.get("question", "")) + " " + str(question.get("reason", "")),
                re.IGNORECASE,
            )
        )
        for question in questions
        if isinstance(question, dict)
    )
    groups = requirement_group_map(index.get("requirements", []))
    coverage_statements = {
        item["id"]: item.get("statement", "") for item in index.get("coverage_points", [])
    }
    roles_by_case = {
        case["id"]: roles for case, roles in zip(cases, case_roles)
    }
    cross_rf = audit_cross_rf(
        cases,
        groups,
        coverage_statements=coverage_statements,
        roles_by_case=roles_by_case,
    )
    requirement_summaries = per_requirement_summary(index, questions)
    source_gaps = sum(item["source_coverage_gaps"] for item in requirement_summaries.values())
    execution_metrics = step_distribution(cases)
    gap_counts_by_group: dict[str, int] = {}
    for requirement_id, summary in requirement_summaries.items():
        label = groups.get(requirement_id, requirement_id)
        gap_counts_by_group[label] = gap_counts_by_group.get(label, 0) + summary["source_coverage_gaps"]
    return {
        "requirements": len(index.get("requirements", [])),
        "coverage_points": len(index.get("coverage_points", [])),
        "scenarios": len(index.get("scenarios", [])),
        "test_cases": len(cases),
        "multi_cp_scenarios": sum(len(case.get("coverage_point_refs", [])) >= 2 for case in cases),
        "steps": sum(len(case.get("steps", [])) for case in cases),
        "ready": statuses["READY"],
        "needs_review": statuses["NEEDS_REVIEW"],
        "blocked": statuses["BLOCKED"],
        "questions": len(questions),
        "markdown_files": len(list((output_dir / "test-cases-md").glob("*.md"))),
        "test_cases_with_one_step": sum(count == 1 for count in step_counts),
        "test_cases_with_multiple_steps": sum(count > 1 for count in step_counts),
        "average_steps_per_test_case": round(sum(step_counts) / len(cases), 2) if cases else 0.0,
        **execution_metrics,
        "test_cases_with_execution_enrichment": sum(
            bool(roles - {"FUNCTIONAL_AUTHORITY"}) for roles in case_roles
        ),
        "test_cases_with_multiple_source_roles": sum(len(roles) > 1 for roles in case_roles),
        "test_cases_with_concrete_test_data": concrete_data_cases,
        "abstract_action_warnings": abstract_actions,
        "execution_path_questions": path_question_count,
        "functional_authority_contributions": sum("FUNCTIONAL_AUTHORITY" in roles for roles in case_roles),
        "technical_context_contributions": sum("TECHNICAL_CONTEXT" in roles for roles in case_roles),
        "implementation_evidence_contributions": sum("IMPLEMENTATION_EVIDENCE" in roles for roles in case_roles),
        "test_asset_contributions": sum("TEST_ASSET" in roles for roles in case_roles),
        "rf_groups": len(set(groups.values())),
        "source_claims_identified": sum(
            item["source_claims_identified"] for item in requirement_summaries.values()
        ),
        "source_claims_represented": sum(
            item["source_claims_represented"] for item in requirement_summaries.values()
        ),
        "atomic_source_claims_identified": sum(
            item["source_claims_identified"] for item in requirement_summaries.values()
        ),
        "possible_compound_claim_warnings": len(
            possible_compound_claims(index.get("normative_clauses", []))
        ),
        "source_coverage_gaps": source_gaps,
        "recovered_source_gaps": 0,
        "rf_groups_with_zero_gaps": sum(value == 0 for value in gap_counts_by_group.values()),
        "rf_groups_with_gaps": sum(value > 0 for value in gap_counts_by_group.values()),
        "cross_rf_tcs": len(cross_rf["same_multi_rf_coverage"]),
        "same_multi_rf_coverage": len(cross_rf["same_multi_rf_coverage"]),
        "duplicate_candidates": cross_rf["duplicate_candidates"],
        "similar_but_distinct": cross_rf["similar_but_distinct"],
        "automatic_merges": 0,
        "automatic_removals": 0,
    }


def observed_metrics(document: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, list[Any]] = {}
    for item in document["stages"]:
        for key, value in item.get("metrics", {}).items():
            values.setdefault(key, []).append(value)
    observed: dict[str, Any] = {}
    for key, entries in values.items():
        strategy = AGGREGATION_STRATEGIES.get(key)
        if strategy is None:
            raise ValueError(f"No aggregation strategy is defined for metric {key!r}")
        if strategy == "sum":
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in entries):
                raise ValueError(f"Metric {key!r} requires numeric values for sum aggregation")
            observed[key] = sum(entries)
        elif strategy == "set":
            if not all(isinstance(value, list) for value in entries):
                raise ValueError(f"Metric {key!r} requires arrays for set aggregation")
            observed[key] = []
            for value in entries:
                for member in value:
                    if member not in observed[key]:
                        observed[key].append(member)
        else:  # last
            observed[key] = entries[-1]
    return observed


def finish_run(
    path: Path,
    output_dir: Path | None = None,
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    document = read_document(path)
    unfinished = [item["name"] for item in document["stages"] if item["status"] in {"pending", "running"}]
    if unfinished:
        raise ValueError("Finish or skip every diagnostic stage first: " + ", ".join(unfinished))
    if candidates and len(candidates) > 3:
        raise ValueError("At most 3 optimization candidates are allowed")

    finished_at = timestamp()
    run = document["run"]
    run["finished_at"] = finished_at
    run["total_elapsed_seconds"] = elapsed(run["started_at"], finished_at)
    document["totals"] = output_totals(output_dir)
    observed = observed_metrics(document)
    document["totals"].update(observed)
    document["aggregation_strategies"] = {
        key: AGGREGATION_STRATEGIES[key] for key in observed
    }
    testable_points = document["totals"].get("testable_coverage_points")
    candidate_count = document["totals"].get("scenario_candidates_before_merge")
    merge_reduction = document["totals"].get("scenario_merges_applied")
    final_scenarios = document["totals"].get("scenarios_after_merge")
    if isinstance(testable_points, int) and isinstance(candidate_count, int):
        if candidate_count < testable_points:
            raise ValueError(
                "scenario_candidates_before_merge is lower than testable_coverage_points"
            )
    if all(isinstance(value, int) for value in (candidate_count, merge_reduction, final_scenarios)):
        if candidate_count - merge_reduction != final_scenarios:
            raise ValueError(
                "candidate-to-scenario reduction is inconsistent with scenario_merges_applied"
            )
    reviewed = document["totals"].get("compound_claims_reviewed")
    split = document["totals"].get("compound_claims_split")
    kept = document["totals"].get("compound_claims_kept_atomic")
    if all(isinstance(value, int) for value in (reviewed, split, kept)) and reviewed != split + kept:
        raise ValueError(
            "compound claim review count differs from SPLIT plus KEEP_ATOMIC decisions"
        )
    identified = document["totals"].get("source_claims_identified")
    represented = document["totals"].get("source_claims_represented")
    gaps = document["totals"].get("source_coverage_gaps")
    if (
        all(isinstance(value, int) for value in (identified, represented, gaps))
        and identified != represented + gaps
    ):
        raise ValueError(
            "source claim lineage differs from represented claims plus coverage gaps"
        )
    measured = [
        item
        for item in document["stages"]
        if item.get("timing_available") and isinstance(item.get("elapsed_seconds"), (int, float))
    ]
    known_stage_time = sum(item["elapsed_seconds"] for item in measured)
    total_elapsed = run["total_elapsed_seconds"]
    unattributed = round(max(0.0, total_elapsed - known_stage_time), 6)
    run["unattributed_seconds"] = unattributed
    run["unattributed_percent"] = round(100 * unattributed / total_elapsed, 2) if total_elapsed else 0.0
    run["run_wall_clock_seconds"] = total_elapsed
    run["sum_stage_wall_seconds"] = round(known_stage_time, 6)
    ordered_measured = sorted(measured, key=lambda item: item["started_at"])
    gaps = []
    for previous, current in zip(ordered_measured, ordered_measured[1:]):
        gap = elapsed(previous["finished_at"], current["started_at"])
        if gap:
            gaps.append({"after": previous["name"], "before": current["name"], "seconds": gap})
    run["inter_stage_gap_seconds"] = round(sum(item["seconds"] for item in gaps), 6)
    run["inter_stage_gaps"] = gaps
    if run["unattributed_percent"] > 20:
        document["warnings"].append(
            {
                "code": "HIGH_UNATTRIBUTED_TIME",
                "message": "More than 20% of elapsed time was outside measured stages; start timers before stage reasoning.",
                "unattributed_percent": run["unattributed_percent"],
            }
        )
    case_count = document["totals"].get("test_cases", 0)
    single_step_count = document["totals"].get("test_cases_with_one_step", 0)
    if (
        observed.get("detailed_execution_evidence_available") is True
        and case_count >= 5
        and single_step_count / case_count >= 0.8
    ):
        document["warnings"].append(
            {
                "code": "POSSIBLE_EXECUTION_UNDER_SPECIFICATION",
                "message": "Detailed selected execution evidence exists, but at least 80% of Test Cases contain one step.",
                "test_cases_with_one_step": single_step_count,
                "test_cases": case_count,
            }
        )
    histogram = document["totals"].get("step_count_histogram", {})
    if (
        observed.get("varied_execution_paths_available") is True
        and case_count >= 5
        and len(histogram) == 1
    ):
        document["totals"]["possible_step_template_bias"] = True
        document["warnings"].append(
            {
                "code": "POSSIBLE_STEP_TEMPLATE_BIAS",
                "message": "Selected evidence contains differently complex paths, but every Test Case has the same step count.",
                "step_count_histogram": histogram,
            }
        )
    else:
        document["totals"]["possible_step_template_bias"] = False
    compound_count = document["totals"].get("possible_compound_claim_warnings", 0)
    if compound_count:
        document["warnings"].append(
            {
                "code": "POSSIBLE_COMPOUND_NORMATIVE_CLAIM",
                "message": "One or more materialized normative claims may contain independently observable outcomes.",
                "count": compound_count,
            }
        )
    multi_action_count = document["totals"].get("multi_action_step_warnings", 0)
    if multi_action_count:
        document["warnings"].append(
            {
                "code": "POSSIBLE_MULTI_ACTION_STEP",
                "message": "One or more steps may compress a documented operational sequence.",
                "count": multi_action_count,
            }
        )
    hidden_subtest_count = document["totals"].get("hidden_subtest_warnings", 0)
    if hidden_subtest_count:
        document["warnings"].append(
            {
                "code": "HIDDEN_SUBTEST",
                "message": "One or more procedural actions compress independently rerunnable variants.",
                "count": hidden_subtest_count,
            }
        )
    scenario_warning_count = document["totals"].get(
        "possible_scenario_overcompression_warnings", 0
    )
    if scenario_warning_count:
        document["warnings"].append(
            {
                "code": "POSSIBLE_SCENARIO_OVERCOMPRESSION",
                "message": "One or more multi-CP scenarios require semantic independence review.",
                "count": scenario_warning_count,
            }
        )
    if (
        document["totals"].get("source_parallelism_available") is True
        and document["totals"].get("source_files_assigned", 0) > 1
        and document["totals"].get("source_analysis_order_constraints", 0) == 0
        and document["totals"].get("source_analysis_max_concurrency", 0) <= 1
    ):
        document["warnings"].append(
            {
                "code": "PARALLELISM_NOT_USED",
                "message": "Independent selected sources were available, but observed source concurrency remained one.",
            }
        )
    document["scope_proof"] = {
        key: observed.get(key, [] if key in {"selected_scope_roots", "resolved_scope_paths"} else 0)
        for key in SCOPE_PROOF_METRICS
    }
    document["scope_proof"]["scope_violation"] = bool(
        document["scope_proof"]["files_opened_outside_scope"]
    )
    for key in ("selected_scope_roots", "resolved_scope_paths", "files_opened", "files_opened_outside_scope"):
        if key in observed and document["totals"].get(key) != document["scope_proof"].get(key):
            raise ValueError(f"totals.{key} differs from scope_proof.{key}")
    if measured and known_stage_time > 0:
        slowest = max(measured, key=lambda item: item["elapsed_seconds"])
        document["observed_bottlenecks"] = [
            {
                "stage": slowest["name"],
                "elapsed_seconds": slowest["elapsed_seconds"],
                "percent_of_known_stage_time": round(100 * slowest["elapsed_seconds"] / known_stage_time, 2),
            }
        ]
    else:
        document["observed_bottlenecks"] = []
    document["optimization_candidates"] = candidates or []
    write_document(path, document)
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create a new diagnostic run")
    start.add_argument("file", type=Path)

    begin = subparsers.add_parser("begin", help="start timing one stage")
    begin.add_argument("file", type=Path)
    begin.add_argument("stage", choices=STAGE_NAMES)

    end = subparsers.add_parser("end", help="finish one timed stage")
    end.add_argument("file", type=Path)
    end.add_argument("stage", choices=STAGE_NAMES)
    end.add_argument("--done", action="append", required=True)
    end.add_argument("--metric", action="append", default=[])
    end.add_argument("--note", action="append", default=[])
    end.add_argument("--status", choices=("completed", "failed"), default="completed")

    skip = subparsers.add_parser("skip", help="record an intentionally skipped stage")
    skip.add_argument("file", type=Path)
    skip.add_argument("stage", choices=STAGE_NAMES)
    skip.add_argument("--done", action="append", required=True)
    skip.add_argument("--note", action="append", default=[])

    finish = subparsers.add_parser("finish", help="finish the run and derive totals")
    finish.add_argument("file", type=Path)
    finish.add_argument("--output", type=Path)
    finish.add_argument("--candidate", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            start_run(args.file)
        elif args.command == "begin":
            begin_stage(args.file, args.stage)
        elif args.command == "end":
            metrics = dict(parse_metric(raw) for raw in args.metric)
            end_stage(args.file, args.stage, args.done, metrics, args.note, args.status)
        elif args.command == "skip":
            skip_stage(args.file, args.stage, args.done, args.note)
        else:
            finish_run(args.file, args.output, args.candidate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: diagnostics updated at {args.file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
