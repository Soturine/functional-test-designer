#!/usr/bin/env python3
"""Small, evidence-grounded clarification sessions with explicit provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


IMPACT_ORDER = {
    "oracle": 0, "actor_permission": 1, "starting_state": 2, "trigger": 3,
    "input_partition": 4, "execution_boundary": 5, "side_effect": 6,
    "procedure": 7, "test_data": 8, "environment": 9,
    "observability": 10, "automation_feasibility": 11,
}
STOP_WORDS = {"stop", "done", "proceed", "skip"}


def rank_questions(questions: Iterable[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Return the highest-impact unique questions without inventing missing context."""
    unique: dict[str, dict[str, Any]] = {}
    for question in questions:
        key = str(question.get("id") or question.get("question", "")).strip()
        if key:
            unique.setdefault(key, dict(question))
    ranked = sorted(
        unique.values(),
        key=lambda item: (
            IMPACT_ORDER.get(str(item.get("category", "")).casefold(), 99),
            str(item.get("id", "")),
        ),
    )
    return ranked[: max(0, min(limit, 5))]


def record_answer(
    question: dict[str, Any], answer: str, *, authoritative_correction: bool = False
) -> dict[str, Any]:
    normalized = answer.strip()
    return {
        "question_id": question.get("id"),
        "question": question.get("question"),
        "answer": normalized,
        "affected_refs": list(question.get("affected_refs", [])),
        "source_role": "USER_CLARIFICATION",
        "authority_interpretation": (
            "AUTHORITATIVE_CORRECTION" if authoritative_correction else "SUPPLEMENTAL_EVIDENCE"
        ),
        "conflict_requires_review": bool(
            question.get("approved_authority_answer")
            and normalized != question.get("approved_authority_answer")
            and not authoritative_correction
        ),
    }


def should_stop(answer: str) -> bool:
    return answer.strip().casefold() in STOP_WORDS


def persist_clarifications(run_dir: Path, answers: list[dict[str, Any]]) -> Path:
    path = run_dir / "clarifications.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"answers": answers}, indent=2) + "\n", encoding="utf-8")
    return path


def privacy_safe_metrics(answers: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "clarifications_applied": len(answers),
        "clarification_conflicts": sum(bool(item.get("conflict_requires_review")) for item in answers),
    }
