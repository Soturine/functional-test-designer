#!/usr/bin/env python3
"""Parallel procedural enrichment and one bounded additive feedback pass."""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from execution_quality import hidden_subtest_signals, hidden_subtest_warnings
from parallel_evidence import EvidenceRecord
from procedural_execution import assert_identity_preserved, synthesize_test_case
from scenario_independence import TestIdentity


PROCEDURAL_RESULT_TYPES = {
    "PROCEDURE_READY",
    "PROCEDURE_GAP",
    "PROCEDURAL_AMBIGUITY",
    "DIVERGENCE",
    "INDEPENDENT_BRANCH_DETECTED",
    "UNSUPPORTED_STEP",
}


class ProceduralAmbiguity(ValueError):
    pass


@dataclass(frozen=True)
class ProceduralResult:
    test_case_id: str
    result_type: str
    case: dict[str, Any]
    question: dict[str, Any] | None = None
    finding: dict[str, Any] | None = None
    new_tc_candidate: dict[str, Any] | None = None
    worker_seconds: float = 0.0


@dataclass(frozen=True)
class ProceduralBatch:
    results: tuple[ProceduralResult, ...]
    metrics: dict[str, Any]


def operator_actions_from_evidence(records: list[EvidenceRecord]) -> list[dict[str, Any]]:
    """Port the manual skill's visible-label path principle without browser coupling."""
    paths = {record.navigation for record in records if record.navigation}
    if not paths:
        return []
    if len(paths) > 1:
        raise ProceduralAmbiguity("Selected procedural evidence contains multiple unresolved paths")
    path = next(iter(paths))
    supporting = next(record for record in records if record.navigation == path)
    visible = set(supporting.visible_labels)
    if not path or any(label not in visible for label in path):
        raise ValueError("Every procedural path segment requires a selected-source visible label")
    source_ref = {"source": supporting.source, "reference": supporting.source_ref}
    actions = []
    for index, label in enumerate(path):
        verb = "Open" if index == 0 else "Select"
        next_label = path[index + 1] if index + 1 < len(path) else label
        actions.append(
            {
                "action": f"{verb} {label}.",
                "expected_result": f"The documented path makes {next_label} available.",
                "evidence_source": source_ref,
                **({"depends_on_previous_step": True} if index else {}),
            }
        )
    return actions


def _source_refs(identity: TestIdentity, pack: dict[str, Any]) -> list[dict[str, str]]:
    refs = [
        {"source": source, "reference": reference}
        for source, reference in identity.normative_source_refs
    ]
    for ref in pack.get("source_refs", []):
        normalized = {"source": str(ref["source"]), "reference": str(ref["reference"])}
        if normalized not in refs:
            refs.append(normalized)
    return refs


def unresolved_case(identity: TestIdentity, pack: dict[str, Any], reason: str) -> dict[str, Any]:
    """Preserve WHAT-to-test while making the missing HOW explicit and non-invented."""
    case = {
        "schema_version": "1.2",
        "id": identity.id,
        "title": identity.title,
        "status": "NEEDS_REVIEW",
        "priority": pack.get("priority", "MEDIUM"),
        "type": "FUNCTIONAL",
        "objective": identity.objective or identity.title,
        "requirement_refs": list(identity.requirement_refs),
        "scenario_refs": [identity.scenario_ref],
        "coverage_point_refs": list(identity.coverage_point_refs),
        "source_refs": _source_refs(identity, pack),
        "preconditions": list(identity.material_preconditions),
        "test_data": deepcopy(pack.get("test_data", [])),
        "steps": [{
            "step": 1,
            "action": "Obtain the documented execution path from an authorized selected source.",
            "expected_result": identity.normative_oracle,
            "needs_clarification": True,
        }],
        "postconditions": deepcopy(pack.get("postconditions", [])),
        "cleanup": deepcopy(pack.get("cleanup", [])),
        "tags": deepcopy(pack.get("tags", [])),
        "notes": [*deepcopy(pack.get("notes", [])), reason],
    }
    assert_identity_preserved(identity, case)
    return case


def _question(identity: TestIdentity, pack: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "related_test_cases": [identity.id],
        "requirement_refs": list(identity.requirement_refs),
        "source_refs": _source_refs(identity, pack),
        "question": pack.get(
            "procedural_question",
            f"Which documented execution path reaches {identity.title}?",
        ),
        "reason": reason,
        "blocking": False,
    }


def procedural_worker(identity: TestIdentity, pack: dict[str, Any]) -> ProceduralResult:
    """Enrich one immutable TestIdentity without deciding or changing Test Design."""
    began = time.perf_counter()
    working = deepcopy(pack)
    records = working.get("manual_evidence_records", [])
    if records and not working.get("actions"):
        try:
            working["actions"] = operator_actions_from_evidence(records)
        except ProceduralAmbiguity:
            reason = "Selected sources expose multiple procedural paths without resolving which one applies."
            return ProceduralResult(
                identity.id,
                "PROCEDURAL_AMBIGUITY",
                unresolved_case(identity, working, reason),
                question=_question(identity, working, reason),
                worker_seconds=time.perf_counter() - began,
            )

    actions = working.get("actions", [])
    hidden = [
        signal
        for action in actions
        for signal in hidden_subtest_signals(str(action.get("action", "")))
    ]
    if hidden or working.get("independent_branch"):
        reason = "Procedural evidence contains an independently rerunnable branch; return it to Scenario Design."
        return ProceduralResult(
            identity.id,
            "INDEPENDENT_BRANCH_DETECTED",
            unresolved_case(identity, working, reason),
            new_tc_candidate=deepcopy(working.get("independent_branch") or {
                "reason": reason,
                "signals": hidden,
                "authority_sufficient": False,
            }),
            worker_seconds=time.perf_counter() - began,
        )
    if working.get("procedural_ambiguity"):
        reason = str(working["procedural_ambiguity"])
        return ProceduralResult(
            identity.id,
            "PROCEDURAL_AMBIGUITY",
            unresolved_case(identity, working, reason),
            question=_question(identity, working, reason),
            worker_seconds=time.perf_counter() - began,
        )
    if not actions:
        reason = "The normative behavior is known, but selected evidence provides no executable path."
        return ProceduralResult(
            identity.id,
            "PROCEDURE_GAP",
            unresolved_case(identity, working, reason),
            question=_question(identity, working, reason),
            worker_seconds=time.perf_counter() - began,
        )

    case = synthesize_test_case(identity, working)
    if working.get("unsupported_step"):
        case["status"] = "NEEDS_REVIEW"
        reason = str(working["unsupported_step"])
        case["notes"].append(reason)
        return ProceduralResult(
            identity.id,
            "UNSUPPORTED_STEP",
            case,
            question=_question(identity, working, reason),
            worker_seconds=time.perf_counter() - began,
        )
    if working.get("divergence"):
        divergence = working["divergence"]
        finding = {
            "type": "IMPLEMENTATION_DIVERGENCE",
            "statement": str(divergence["statement"]),
            "requirement_refs": list(identity.requirement_refs),
            "source_refs": _source_refs(identity, working),
        }
        return ProceduralResult(
            identity.id,
            "DIVERGENCE",
            case,
            finding=finding,
            worker_seconds=time.perf_counter() - began,
        )
    return ProceduralResult(
        identity.id,
        "PROCEDURE_READY",
        case,
        worker_seconds=time.perf_counter() - began,
    )


def run_procedural_tasks(
    tasks: list[tuple[TestIdentity, dict[str, Any]]], *, max_workers: int = 4
) -> ProceduralBatch:
    """Enrich frozen identities concurrently and return deterministic result order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least one")
    ids = [identity.id for identity, _ in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("A frozen Test Case can be enqueued only once per procedural pass")
    lock = threading.Lock()
    active = 0
    maximum = 0

    def work(index: int, identity: TestIdentity, pack: dict[str, Any]):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            return index, procedural_worker(identity, pack)
        finally:
            with lock:
                active -= 1

    began = time.perf_counter()
    results: dict[int, ProceduralResult] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(tasks)))) as executor:
        futures = {
            executor.submit(work, index, identity, pack): index
            for index, (identity, pack) in enumerate(tasks)
        }
        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result
    wall_clock = time.perf_counter() - began
    ordered = tuple(results[index] for index in range(len(tasks)))
    counts = Counter(result.result_type for result in ordered)
    metrics = {
        "procedural_tasks_enqueued": len(tasks),
        "procedural_tasks_completed": len(ordered),
        "procedural_max_concurrency": maximum,
        "procedure_ready": counts["PROCEDURE_READY"],
        "procedure_gaps": counts["PROCEDURE_GAP"],
        "procedural_ambiguities": counts["PROCEDURAL_AMBIGUITY"],
        "procedural_divergences": counts["DIVERGENCE"],
        "independent_branches_detected": counts["INDEPENDENT_BRANCH_DETECTED"],
        "unsupported_steps": counts["UNSUPPORTED_STEP"],
        "new_tc_candidates": sum(result.new_tc_candidate is not None for result in ordered),
        "procedural_wall_clock_seconds": round(wall_clock, 6),
        "procedural_aggregate_worker_seconds": round(
            sum(result.worker_seconds for result in ordered), 6
        ),
    }
    return ProceduralBatch(ordered, metrics)


def reconcile_additive_feedback(
    initial_cases: list[dict[str, Any]],
    results: tuple[ProceduralResult, ...],
    reviewer: Callable[
        [dict[str, Any], set[str]], tuple[TestIdentity, dict[str, Any]] | None
    ] | None = None,
) -> dict[str, Any]:
    """Run one additive-only pass; existing cases and IDs are immutable."""
    original = deepcopy(initial_cases)
    cases = deepcopy(initial_cases)
    questions: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    candidates = [result.new_tc_candidate for result in results if result.new_tc_candidate]
    for result in results:
        if result.question:
            questions.append({"id": f"Q-{len(questions) + 1:03d}", **deepcopy(result.question)})
        if result.finding:
            findings.append({"id": f"FND-{len(findings) + 1:03d}", **deepcopy(result.finding)})

    appended = 0
    pending_follow_up = 0
    existing_ids = {case["id"] for case in cases}
    if reviewer:
        for candidate in candidates:
            approved = reviewer(deepcopy(candidate), set(existing_ids))
            if approved is None:
                continue
            identity, pack = approved
            if identity.id in existing_ids:
                raise ValueError("Additive feedback cannot replace an existing Test Case ID")
            result = procedural_worker(identity, pack)
            cases.append(result.case)
            existing_ids.add(identity.id)
            appended += 1
            if result.new_tc_candidate:
                pending_follow_up += 1

    if len(cases) < len(original):
        raise ValueError("Additive feedback cannot reduce existing Test Case count")
    for before, after in zip(original, cases[: len(original)]):
        for field in ("id", "scenario_refs", "coverage_point_refs", "requirement_refs", "objective"):
            if before.get(field) != after.get(field):
                raise ValueError("Additive feedback changed an existing frozen Test Case")
    return {
        "test_cases": cases,
        "questions": questions,
        "findings": findings,
        "metrics": {
            "new_tc_candidates": len(candidates),
            "new_tcs_appended": appended,
            "pending_additive_follow_up": pending_follow_up,
        },
    }


def automation_execution_audit(case: dict[str, Any], identity: TestIdentity) -> dict[str, Any]:
    """Return an objective readiness classification, never a subjective score."""
    reasons = []
    if case.get("status") != "READY":
        reasons.append("STATUS_NOT_READY")
    if not identity.execution_boundary:
        reasons.append("MISSING_EXECUTION_BOUNDARY")
    if not case.get("preconditions"):
        reasons.append("MISSING_DETERMINISTIC_SETUP")
    if not case.get("test_data"):
        reasons.append("MISSING_TEST_DATA")
    elif any(
        "<" in str(item.get("description", ""))
        for item in case.get("test_data", [])
        if isinstance(item, dict)
    ):
        reasons.append("PLACEHOLDER_TEST_DATA")
    if any(step.get("needs_clarification") for step in case.get("steps", [])):
        reasons.append("UNSUPPORTED_STEP")
    if hidden_subtest_warnings([case]):
        reasons.append("HIDDEN_SUBTEST")
    if not identity.assertions:
        reasons.append("MISSING_TRACEABLE_ASSERTIONS")
    if not case.get("steps") or case["steps"][-1].get("expected_result") != identity.normative_oracle:
        reasons.append("NORMATIVE_ORACLE_NOT_OBSERVABLE")
    return {
        "classification": "AUTOMATION_EXECUTION_READY" if not reasons else "AUTOMATION_EXECUTION_NOT_READY",
        "reasons": reasons,
    }
