#!/usr/bin/env python3
"""Explain benchmark ideas without using historical suite size as an objective."""

from __future__ import annotations

from typing import Any


DISPOSITIONS = {
    "COVERED_BY", "SPLIT_INTO", "EQUIVALENT_TO", "MERGE_CANDIDATE_WITH", "SUPERSEDED",
    "INVALID_AGAINST_CURRENT_AUTHORITY", "IMPLEMENTATION_SPECIFIC", "KNOWN_GAP", "QUESTION",
    "OUT_OF_SCOPE",
}


def audit_reconciliation(
    benchmark_items: list[dict[str, Any]],
    reconciliations: list[dict[str, Any]],
    *, test_case_ids: set[str], question_ids: set[str],
) -> dict[str, Any]:
    by_item: dict[str, dict[str, Any]] = {}
    for record in reconciliations:
        item_ref = str(record.get("benchmark_item_ref", ""))
        if not item_ref or item_ref in by_item:
            raise ValueError("Every benchmark item requires exactly one reconciliation record")
        disposition = str(record.get("disposition", ""))
        if disposition not in DISPOSITIONS:
            raise ValueError(f"Benchmark item {item_ref} has unsupported disposition {disposition}")
        targets = set(map(str, record.get("target_refs", [])))
        if disposition in {"COVERED_BY", "SPLIT_INTO", "EQUIVALENT_TO", "MERGE_CANDIDATE_WITH"}:
            if not targets or not targets <= test_case_ids:
                raise ValueError(f"Benchmark item {item_ref} does not link valid Test Cases")
        if disposition == "QUESTION" and (not targets or not targets <= question_ids):
            raise ValueError(f"Benchmark item {item_ref} does not link valid Questions")
        if disposition in {"SUPERSEDED", "INVALID_AGAINST_CURRENT_AUTHORITY", "IMPLEMENTATION_SPECIFIC", "KNOWN_GAP", "OUT_OF_SCOPE"} and not str(record.get("reason", "")).strip():
            raise ValueError(f"Benchmark item {item_ref} requires a reason")
        by_item[item_ref] = record
    expected = {str(item.get("id", "")) for item in benchmark_items}
    missing = sorted(expected - set(by_item))
    extra = sorted(set(by_item) - expected)
    if missing or extra:
        raise ValueError(f"Benchmark reconciliation mismatch: missing={missing}, extra={extra}")
    counts = {value: 0 for value in sorted(DISPOSITIONS)}
    for record in reconciliations:
        counts[str(record["disposition"])] += 1
    return {
        "benchmark_items": len(benchmark_items),
        "benchmark_items_reconciled": len(reconciliations),
        "disposition_counts": counts,
        "target_count_used_as_goal": False,
    }
