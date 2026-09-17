#!/usr/bin/env python3
"""Classify cross-requirement overlap without merging or deleting Test Cases."""

from __future__ import annotations

import json
import re
from itertools import combinations
from typing import Any


SAME_MULTI_RF_COVERAGE = "SAME_MULTI_RF_COVERAGE"
DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
SIMILAR_BUT_DISTINCT = "SIMILAR_BUT_DISTINCT"


def normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def semantic_signature(
    case: dict[str, Any],
    coverage_statements: dict[str, str] | None = None,
    source_roles: set[str] | None = None,
) -> str:
    coverage_statements = coverage_statements or {}
    payload = {
        "objective": normalized(case.get("objective", "")),
        "preconditions": sorted(normalized(value) for value in case.get("preconditions", [])),
        "test_data": sorted(
            (normalized(item.get("name", "")), normalized(item.get("description", "")))
            for item in case.get("test_data", [])
            if isinstance(item, dict)
        ),
        "steps": [
            (normalized(step.get("action", "")), normalized(step.get("expected_result", "")))
            for step in case.get("steps", [])
            if isinstance(step, dict)
        ],
        "postconditions": sorted(normalized(value) for value in case.get("postconditions", [])),
        "coverage": sorted(
            normalized(coverage_statements.get(cp_id, cp_id))
            for cp_id in case.get("coverage_point_refs", [])
        ),
        "source_roles": sorted(source_roles or set()),
        "status": case.get("status"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def trigger_oracle_signature(case: dict[str, Any]) -> tuple[str, str]:
    steps = [step for step in case.get("steps", []) if isinstance(step, dict)]
    if not steps:
        return "", ""
    return normalized(steps[-1].get("action", "")), normalized(steps[-1].get("expected_result", ""))


def classify_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    coverage_statements: dict[str, str] | None = None,
    left_roles: set[str] | None = None,
    right_roles: set[str] | None = None,
) -> str | None:
    if semantic_signature(left, coverage_statements, left_roles) == semantic_signature(
        right, coverage_statements, right_roles
    ):
        return DUPLICATE_CANDIDATE
    left_trigger, left_oracle = trigger_oracle_signature(left)
    right_trigger, right_oracle = trigger_oracle_signature(right)
    if left_trigger and left_trigger == right_trigger and left_oracle and left_oracle == right_oracle:
        return SIMILAR_BUT_DISTINCT
    return None


def audit_cross_rf(
    cases: list[dict[str, Any]],
    groups_by_requirement: dict[str, str],
    *,
    coverage_statements: dict[str, str] | None = None,
    roles_by_case: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    roles_by_case = roles_by_case or {}
    same_multi = []
    primary_group: dict[str, str] = {}
    for case in cases:
        labels = [groups_by_requirement.get(ref, ref) for ref in case.get("requirement_refs", [])]
        unique = list(dict.fromkeys(labels))
        primary_group[case["id"]] = unique[0] if unique else "Unmapped"
        if len(unique) > 1:
            same_multi.append({"classification": SAME_MULTI_RF_COVERAGE, "test_case_ids": [case["id"]]})

    pairs = []
    for left, right in combinations(cases, 2):
        if primary_group[left["id"]] == primary_group[right["id"]]:
            continue
        classification = classify_pair(
            left,
            right,
            coverage_statements=coverage_statements,
            left_roles=roles_by_case.get(left["id"], set()),
            right_roles=roles_by_case.get(right["id"], set()),
        )
        if classification:
            pairs.append({"classification": classification, "test_case_ids": [left["id"], right["id"]]})
    return {
        "same_multi_rf_coverage": same_multi,
        "pairs": pairs,
        "duplicate_candidates": sum(item["classification"] == DUPLICATE_CANDIDATE for item in pairs),
        "similar_but_distinct": sum(item["classification"] == SIMILAR_BUT_DISTINCT for item in pairs),
        "automatic_merges": 0,
        "automatic_removals": 0,
    }
