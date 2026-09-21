#!/usr/bin/env python3
"""Account for selected-evidence scenario opportunities without promoting authority."""

from __future__ import annotations

from typing import Any


SOURCE_ROLES = {
    "FUNCTIONAL_AUTHORITY", "IMPLEMENTATION_EVIDENCE", "TECHNICAL_CONTEXT", "TEST_ASSET",
}
DISPOSITIONS = {
    "COVERED_BY_EXISTING_SCENARIO", "NEW_NORMATIVE_SCENARIO", "DIVERGENCE_SCENARIO",
    "IMPLEMENTATION_CHARACTERIZATION", "QUESTION", "FINDING", "NOT_TESTABLE", "OUT_OF_SCOPE",
}
NON_NORMATIVE_ROLES = {"IMPLEMENTATION_EVIDENCE", "TECHNICAL_CONTEXT", "TEST_ASSET"}


def _ref_key(value: dict[str, Any]) -> tuple[str, str]:
    ref = value.get("source_ref", value)
    return str(ref.get("source", "")), str(ref.get("reference", ""))


def audit_scenario_opportunities(
    selected_evidence: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    *, scenario_ids: set[str] | None = None, finding_ids: set[str] | None = None,
    question_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Require one defensible disposition per meaningful selected-evidence behavior."""
    scenario_ids = scenario_ids or set()
    finding_ids = finding_ids or set()
    question_ids = question_ids or set()
    meaningful = {_ref_key(item) for item in selected_evidence if item.get("meaningful_behavior", True)}
    accounted: set[tuple[str, str]] = set()
    counts = {value: 0 for value in sorted(DISPOSITIONS)}
    divergence_linked = 0
    test_assets_accounted = 0
    cross_cutting = 0
    for item in opportunities:
        role = str(item.get("source_role", ""))
        disposition = str(item.get("disposition", ""))
        key = _ref_key(item)
        if role not in SOURCE_ROLES or not all(key):
            raise ValueError("Every opportunity requires a supported source_role and source_ref")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"Opportunity {item.get('id')} requires a supported disposition")
        if key in accounted:
            raise ValueError(f"Selected evidence opportunity is dispositioned more than once: {key}")
        accounted.add(key)
        counts[disposition] += 1
        target_refs = set(map(str, item.get("target_refs", [])))
        authority = str(item.get("authority_status", ""))
        if role in NON_NORMATIVE_ROLES and disposition == "NEW_NORMATIVE_SCENARIO":
            if not item.get("normative_support_refs"):
                raise ValueError("Non-normative evidence cannot create a normative scenario without authority")
        if authority == "DIVERGENCE":
            if disposition not in {"DIVERGENCE_SCENARIO", "FINDING", "QUESTION", "NOT_TESTABLE"}:
                raise ValueError("Every divergence requires an explicit coverage disposition")
            if disposition == "DIVERGENCE_SCENARIO" and not (target_refs & scenario_ids):
                raise ValueError("Divergence scenario disposition requires a linked Scenario")
            if not (set(map(str, item.get("finding_refs", []))) & finding_ids):
                raise ValueError("Every divergence opportunity requires a linked Finding")
            divergence_linked += 1
        if disposition in {"COVERED_BY_EXISTING_SCENARIO", "NEW_NORMATIVE_SCENARIO", "DIVERGENCE_SCENARIO"}:
            if scenario_ids and not (target_refs & scenario_ids):
                raise ValueError(f"Opportunity {item.get('id')} does not link an existing Scenario")
        if disposition == "QUESTION" and question_ids and not (target_refs & question_ids):
            raise ValueError(f"Opportunity {item.get('id')} does not link an existing Question")
        if disposition == "FINDING" and finding_ids and not (target_refs & finding_ids):
            raise ValueError(f"Opportunity {item.get('id')} does not link an existing Finding")
        if disposition in {"NOT_TESTABLE", "OUT_OF_SCOPE"} and not item.get("reason"):
            raise ValueError(f"Opportunity {item.get('id')} requires a reason")
        if role == "TEST_ASSET":
            test_assets_accounted += 1
        if item.get("cross_cutting"):
            if not item.get("continuous_execution") or len(item.get("coverage_point_refs", [])) < 2:
                raise ValueError("Cross-cutting/E2E opportunity requires a continuous traced execution")
            cross_cutting += 1
    missing = sorted(meaningful - accounted)
    if missing:
        raise ValueError(
            "Meaningful selected evidence disappeared before opportunity disposition: "
            + ", ".join(f"{source}#{reference}" for source, reference in missing)
        )
    return {
        "selected_evidence_behaviors": len(meaningful),
        "scenario_opportunities": len(opportunities),
        "opportunity_dispositions": counts,
        "divergence_opportunities_linked": divergence_linked,
        "test_asset_behaviors_accounted": test_assets_accounted,
        "cross_cutting_opportunities": cross_cutting,
        "unaccounted_selected_evidence_behaviors": 0,
    }
