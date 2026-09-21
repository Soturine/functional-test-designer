#!/usr/bin/env python3
"""Read-only audits over an existing canonical suite."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from procedural_readiness import audit_execution_readiness


VALID_FOCI = {"everything", "procedure", "automation", "cohesion", "coverage", "outputs"}


def check_suite(
    cases: list[dict[str, Any]], *, focus: str = "everything",
    cohesion_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit without mutation, regeneration, splitting, or source reads."""
    focus = focus.casefold().strip()
    if focus not in VALID_FOCI:
        raise ValueError(f"Unsupported check focus: {focus}")
    before = deepcopy(cases)
    audits = [audit_execution_readiness(case) for case in cases]
    findings = []
    if focus in {"everything", "procedure", "automation"}:
        for audit in audits:
            reasons = audit["reason_codes"]
            if reasons:
                findings.append({
                    "test_case_id": audit["test_case_id"],
                    "reason_codes": reasons,
                    "evidence": "Existing canonical Test Case fields",
                    "recommended_next_action": "Clarify or enrich only the unsupported procedural details.",
                })
    decisions = deepcopy(cohesion_decisions or []) if focus in {"everything", "cohesion"} else []
    if cases != before:
        raise AssertionError("Read-only suite audit mutated the canonical cases")
    return {
        "focus": focus,
        "findings": findings,
        "cohesion_decisions": decisions,
        "source_reads": 0,
        "suite_mutated": False,
    }
