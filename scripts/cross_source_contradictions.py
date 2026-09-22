#!/usr/bin/env python3
"""Require an explicit disposition for every cross-source contradiction candidate."""

from __future__ import annotations

from collections import Counter
from typing import Any


DISPOSITIONS = {"CONFIRMED_FINDING", "EXPLAINED_NON_CONFLICT", "UNRESOLVED"}


def audit_contradictions(
    candidates: list[dict[str, Any]], finding_ids: set[str], question_ids: set[str]
) -> dict[str, Any]:
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    for item in candidates:
        candidate_id = str(item.get("id", "")).strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError("Every contradiction candidate requires a unique id")
        seen.add(candidate_id)
        if len(item.get("source_refs", [])) < 2:
            raise ValueError(f"Contradiction candidate {candidate_id} requires at least two source refs")
        disposition = str(item.get("disposition", ""))
        if disposition not in DISPOSITIONS:
            raise ValueError(f"Contradiction candidate {candidate_id} requires a disposition")
        if disposition == "CONFIRMED_FINDING" and str(item.get("finding_ref", "")) not in finding_ids:
            raise ValueError(f"Contradiction candidate {candidate_id} requires a valid Finding")
        if disposition == "UNRESOLVED" and str(item.get("question_ref", "")) not in question_ids:
            raise ValueError(f"Contradiction candidate {candidate_id} requires a valid Question")
        if disposition == "EXPLAINED_NON_CONFLICT" and not str(item.get("reason", "")).strip():
            raise ValueError(f"Contradiction candidate {candidate_id} requires a non-conflict explanation")
        counts[disposition] += 1
    return {
        "contradiction_candidates": len(candidates),
        "contradictions_confirmed": counts["CONFIRMED_FINDING"],
        "contradictions_explained": counts["EXPLAINED_NON_CONFLICT"],
        "contradictions_unresolved": counts["UNRESOLVED"],
    }
