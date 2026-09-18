#!/usr/bin/env python3
"""Candidate-first scenario independence and conservative merge decisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ALLOWED_MERGE_REASONS = {
    "INSEPARABLE_SAME_EVENT",
    "SHARED_PASS_FAIL_BOUNDARY",
    "TRUE_SEMANTIC_DUPLICATE",
}
FORBIDDEN_MERGE_REASONS = {
    "SAME_RF",
    "SAME_SCREEN",
    "SAME_ACTOR",
    "SAME_SETUP",
    "SAME_EVIDENCE_PACK",
    "SAME_TITLE",
    "FEWER_TESTS",
    "PERFORMANCE_OPTIMIZATION",
}
IDENTITY_FIELDS = (
    "actor",
    "setup",
    "preconditions",
    "state",
    "trigger",
    "behavior",
    "input_partition",
    "oracle",
    "expected_result",
    "execution_evidence",
    "reporting_purpose",
    "nature",
    "pass_fail_boundary",
    "continuous_execution",
)
SHARED_BOUNDARY_FIELDS = (
    "actor",
    "setup",
    "preconditions",
    "state",
    "trigger",
    "objective",
    "oracle",
    "execution_evidence",
    "reporting_purpose",
    "pass_fail_boundary",
    "continuous_execution",
)


def candidate_from_coverage_point(
    coverage_point: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Materialize one independently reviewable candidate before any grouping."""
    candidate = deepcopy(profile)
    candidate.setdefault("id", f"CAND-{coverage_point['id']}")
    candidate["coverage_point_refs"] = [coverage_point["id"]]
    candidate.setdefault("requirement_refs", [coverage_point["requirement_ref"]])
    candidate.setdefault("source_refs", deepcopy(coverage_point.get("source_refs", [])))
    candidate.setdefault("claim_refs", [])
    candidate.setdefault("clause_refs", deepcopy(coverage_point.get("clause_refs", [])))
    candidate.setdefault("can_fail_independently", True)
    return candidate


def _same(candidate: dict[str, Any], other: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(candidate.get(field) == other.get(field) for field in fields)


def merge_reason(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    """Return an objective merge reason, defaulting uncertainty to separation."""
    if _same(left, right, IDENTITY_FIELDS):
        return "TRUE_SEMANTIC_DUPLICATE"

    left_reason = left.get("merge_reason")
    right_reason = right.get("merge_reason")
    if left_reason != right_reason or left_reason not in {
        "INSEPARABLE_SAME_EVENT",
        "SHARED_PASS_FAIL_BOUNDARY",
    }:
        return None
    if left.get("merge_key") is None or left.get("merge_key") != right.get("merge_key"):
        return None
    if left.get("can_fail_independently", True) or right.get("can_fail_independently", True):
        return None
    if left.get("nature") != right.get("nature"):
        return None
    if left.get("input_partition") != right.get("input_partition"):
        return None
    if not _same(left, right, SHARED_BOUNDARY_FIELDS):
        return None
    return str(left_reason)


def _extend_unique(target: dict[str, Any], source: dict[str, Any], field: str) -> None:
    values = target.setdefault(field, [])
    for value in source.get(field, []):
        if value not in values:
            values.append(deepcopy(value))


def merge_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge only proven duplicates or explicitly inseparable same-event observations."""
    scenarios: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for candidate in candidates:
        for scenario in scenarios:
            reason = merge_reason(scenario, candidate)
            if reason is None:
                continue
            decisions.append(
                {
                    "candidate_ids": [scenario["candidate_ids"][0], candidate["id"]],
                    "reason": reason,
                }
            )
            scenario["candidate_ids"].append(candidate["id"])
            if reason not in scenario.setdefault("merge_reasons", []):
                scenario["merge_reasons"].append(reason)
            for field in (
                "coverage_point_refs",
                "requirement_refs",
                "source_refs",
                "claim_refs",
                "clause_refs",
                "observations",
            ):
                _extend_unique(scenario, candidate, field)
            break
        else:
            scenario = deepcopy(candidate)
            scenario["candidate_ids"] = [candidate["id"]]
            scenario.setdefault("observations", [candidate.get("expected_result", "")])
            scenarios.append(scenario)
    return scenarios, decisions


def audit_multi_cp_scenarios(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag multi-CP scenarios lacking an objective coherence decision."""
    warnings = []
    for scenario in scenarios:
        if len(scenario.get("coverage_point_refs", [])) < 2:
            continue
        reasons = {
            scenario.get("merge_reason"),
            *scenario.get("merge_reasons", []),
        }
        reasons.discard(None)
        if not reasons or not reasons <= ALLOWED_MERGE_REASONS:
            warnings.append(
                {
                    "code": "POSSIBLE_SCENARIO_OVERCOMPRESSION",
                    "scenario_id": scenario.get("id") or scenario.get("candidate_ids", [None])[0],
                    "coverage_point_refs": list(scenario.get("coverage_point_refs", [])),
                }
            )
    return warnings


def metrics(
    coverage_point_count: int,
    candidates: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "coverage_points": coverage_point_count,
        "scenario_candidates_before_merge": len(candidates),
        "scenario_merge_candidates": len(decisions),
        "scenario_merges_applied": len(decisions),
        "scenarios_after_merge": len(scenarios),
        "multi_cp_scenarios": sum(
            len(item.get("coverage_point_refs", [])) >= 2 for item in scenarios
        ),
        "possible_scenario_overcompression_warnings": len(
            audit_multi_cp_scenarios(scenarios)
        ),
        "semantic_duplicates_removed": sum(
            item["reason"] == "TRUE_SEMANTIC_DUPLICATE" for item in decisions
        ),
        "test_cases_generated": len(scenarios),
    }
