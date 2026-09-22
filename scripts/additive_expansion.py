#!/usr/bin/env python3
"""Regression-safe v2.2.1 baseline freeze and additive-expansion audits."""

from __future__ import annotations

import math
from collections import Counter
from copy import deepcopy
from typing import Any


ADDITIVE_DISPOSITIONS = {
    "MATERIALIZED_AS_TC", "ALREADY_COVERED_BY", "CHARACTERIZATION_TC",
    "EXPLORATORY_TC", "QUESTION_REQUIRED", "INVALID_OR_UNSUPPORTED",
    "TECHNICAL_ONLY", "DUPLICATE", "OUT_OF_SCOPE",
}


def normative_profiles(
    profiles: dict[str, dict[str, Any] | list[dict[str, Any]]]
) -> dict[str, dict[str, Any] | list[dict[str, Any]]]:
    """Return only normative Acceptance profiles for the frozen baseline."""
    result: dict[str, dict[str, Any] | list[dict[str, Any]]] = {}
    for cp_ref, raw in profiles.items():
        values = raw if isinstance(raw, list) else [raw]
        accepted = [deepcopy(item) for item in values if item.get("test_basis", "ACCEPTANCE") == "ACCEPTANCE"]
        if not accepted:
            raise ValueError(f"Normative Coverage Point {cp_ref} has no Acceptance candidate")
        result[cp_ref] = accepted if len(accepted) > 1 else accepted[0]
    return result


def snapshot_normative_baseline(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for identity in design["test_identities"]:
        if identity.test_basis != "ACCEPTANCE":
            continue
        snapshot[identity.id] = {
            "coverage_point_refs": tuple(identity.coverage_point_refs),
            "requirement_refs": tuple(identity.requirement_refs),
            "normative_oracle": identity.normative_oracle,
            "objective": identity.objective,
        }
    return snapshot


def audit_baseline_preservation(
    before: dict[str, dict[str, Any]], final_design: dict[str, Any]
) -> dict[str, Any]:
    after = {
        identity.id: {
            "coverage_point_refs": tuple(identity.coverage_point_refs),
            "requirement_refs": tuple(identity.requirement_refs),
            "normative_oracle": identity.normative_oracle,
            "objective": identity.objective,
        }
        for identity in final_design["test_identities"]
        if identity.test_basis == "ACCEPTANCE"
    }
    removed = sorted(set(before) - set(after))
    changed = sorted(test_id for test_id in before.keys() & after.keys() if before[test_id] != after[test_id])
    added = sorted(set(after) - set(before))
    merged_away = max(0, len(before) - len(after))
    valid = not removed and not changed and merged_away == 0 and final_design["metrics"].get("actual_merges") == 0
    if not valid:
        raise ValueError(
            "Normative atomic baseline changed during additive expansion: "
            f"removed={removed}; changed={changed}; merged_away={merged_away}"
        )
    return {
        "normative_atomic_before_expansion": len(before),
        "normative_atomic_after_expansion": len(after),
        "added_normative_tests": len(added),
        "removed_normative_tests": 0,
        "merged_away_normative_tests": 0,
        "changed_normative_oracles": 0,
        "baseline_preserved": True,
    }


def audit_expansion_dispositions(
    candidates: list[dict[str, Any]], materialized_risk_refs: set[str],
    *, required_risk_refs: set[str] | None = None,
) -> dict[str, Any]:
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    unresolved = 0
    accounted_risks: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate.get("id", "")).strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError("Every additive opportunity requires a unique id")
        seen.add(candidate_id)
        disposition = str(candidate.get("disposition", ""))
        if disposition not in ADDITIVE_DISPOSITIONS:
            raise ValueError(f"Additive opportunity {candidate_id} requires an explicit disposition")
        risk_ref = str(candidate.get("risk_condition_ref", ""))
        if risk_ref:
            accounted_risks.add(risk_ref)
        if disposition in {"MATERIALIZED_AS_TC", "CHARACTERIZATION_TC", "EXPLORATORY_TC"}:
            if not risk_ref or risk_ref not in materialized_risk_refs:
                raise ValueError(f"Additive opportunity {candidate_id} claims materialization without a TC profile")
        if disposition == "ALREADY_COVERED_BY" and not candidate.get("target_refs"):
            raise ValueError(f"Additive opportunity {candidate_id} requires existing TC targets")
        if disposition == "QUESTION_REQUIRED" and not candidate.get("question_refs"):
            raise ValueError(f"Additive opportunity {candidate_id} requires a focused Question")
        if disposition in {"INVALID_OR_UNSUPPORTED", "OUT_OF_SCOPE", "TECHNICAL_ONLY", "DUPLICATE"} and not str(candidate.get("reason", "")).strip():
            raise ValueError(f"Additive opportunity {candidate_id} requires a reason")
        counts[disposition] += 1
        unresolved += disposition == "QUESTION_REQUIRED"
    missing_risks = sorted((required_risk_refs or set()) - accounted_risks)
    if missing_risks:
        raise ValueError("Risk candidates have no additive disposition: " + ", ".join(missing_risks))
    rejected_dispositions = {
        "INVALID_OR_UNSUPPORTED", "TECHNICAL_ONLY", "DUPLICATE", "OUT_OF_SCOPE",
    }
    return {
        "expansion_candidates_discovered": len(candidates),
        "expansion_candidates_materialized": sum(counts[value] for value in (
            "MATERIALIZED_AS_TC", "CHARACTERIZATION_TC", "EXPLORATORY_TC"
        )),
        "expansion_candidates_already_covered": counts["ALREADY_COVERED_BY"],
        "expansion_candidates_rejected": sum(counts[value] for value in (
            "INVALID_OR_UNSUPPORTED", "TECHNICAL_ONLY", "DUPLICATE", "OUT_OF_SCOPE"
        )),
        "expansion_candidates_unresolved": unresolved,
        "risk_candidates_discovered": len(required_risk_refs or accounted_risks),
        "risk_candidates_materialized": sum(counts[value] for value in (
            "MATERIALIZED_AS_TC", "CHARACTERIZATION_TC", "EXPLORATORY_TC"
        )),
        "risk_candidates_already_covered": counts["ALREADY_COVERED_BY"],
        "risk_candidates_exploratory": counts["EXPLORATORY_TC"],
        "risk_candidates_rejected": sum(counts[value] for value in rejected_dispositions),
        "risk_candidates_unresolved": counts["QUESTION_REQUIRED"],
        "risk_disposition_complete": True,
    }


def apply_test_data_reachability(
    cases: list[dict[str, Any]], packs: dict[str, dict[str, Any]], finding_ids: set[str]
) -> dict[str, Any]:
    blocked = 0
    for case in cases:
        pack = packs.get(str(case["id"]), {})
        if not pack.get("unreachable_under_observed_implementation"):
            continue
        refs = [str(value) for value in pack.get("blocking_finding_refs", [])]
        if not refs or not set(refs) <= finding_ids:
            raise ValueError(f"{case['id']} has unreachable test data without valid Finding refs")
        case["finding_refs"] = list(dict.fromkeys([*case.get("finding_refs", []), *refs]))
        if case.get("status") == "READY":
            case["status"] = "NEEDS_REVIEW"
        if case.get("execution_status") == "READY":
            case["execution_status"] = "NEEDS_REVIEW"
        blocked += 1
    return {
        "test_data_reachability_checked": len(cases),
        "test_data_unreachable_cases": blocked,
        "test_data_reachability_valid": True,
    }


def audit_semantic_composition(design: dict[str, Any]) -> dict[str, Any]:
    identities = {identity.id: identity for identity in design["test_identities"]}
    errors: list[str] = []
    e2e_count = 0
    for identity in identities.values():
        if identity.test_basis != "E2E":
            continue
        e2e_count += 1
        if not identity.composes:
            errors.append(f"{identity.id}:missing-composition")
            continue
        e2e_requirements = set(identity.requirement_refs)
        for test_id in identity.composes:
            target = identities.get(test_id)
            if target is None or target.test_basis == "E2E" or target.id == identity.id:
                errors.append(f"{identity.id}:{test_id}:invalid-target")
                continue
            if not (e2e_requirements & set(target.requirement_refs)):
                errors.append(f"{identity.id}:{test_id}:unrelated-requirement")
    if errors:
        raise ValueError("Semantically invalid E2E composition: " + ", ".join(errors))
    return {
        "e2e_candidates": e2e_count,
        "e2e_tests": e2e_count,
        "semantic_composition_errors": 0,
        "semantic_composition_valid": True,
    }


def priority_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    distribution = Counter(str(case.get("priority", "MEDIUM")) for case in cases)
    total = len(cases)
    probabilities = [value / total for value in distribution.values() if value] if total else []
    entropy = -sum(value * math.log2(value) for value in probabilities)
    flattened = total >= 5 and max(distribution.values(), default=0) / total >= 0.9
    return {
        "priority_distribution": {key: distribution[key] for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")},
        "priority_entropy": round(entropy, 4),
        "critical_ratio": round(distribution["CRITICAL"] / total, 4) if total else 0.0,
        "high_ratio": round(distribution["HIGH"] / total, 4) if total else 0.0,
        "medium_ratio": round(distribution["MEDIUM"] / total, 4) if total else 0.0,
        "low_ratio": round(distribution["LOW"] / total, 4) if total else 0.0,
        "priority_flattening_warning": flattened,
    }


def calibrate_priority(profile: dict[str, Any]) -> str:
    """Derive a bounded priority from explicit impact signals, never test type alone."""
    signals = {str(value).casefold() for value in profile.get("impact_signals", [])}
    primary_type = str(profile.get("primary_type", "FUNCTIONAL"))
    if signals & {"cross-account leakage", "irreversible corruption", "critical security"}:
        return "CRITICAL"
    if signals & {
        "business flow blocking", "data integrity", "financial impact", "inventory impact",
        "authorization", "recovery impact", "auditability",
    } or primary_type in {"SECURITY", "AUTHORIZATION", "DATA_INTEGRITY", "RECOVERY", "CONCURRENCY"}:
        return "HIGH"
    if signals & {"supporting ui detail", "cosmetic"}:
        return "LOW"
    return "MEDIUM"
