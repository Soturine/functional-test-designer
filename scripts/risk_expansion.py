#!/usr/bin/env python3
"""Evidence-grounded v2.2 risk expansion after normative atomic design."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


PRIMARY_TYPE_BY_RISK = {
    "OPERATOR_ERROR": "NEGATIVE", "MISUSE": "NEGATIVE",
    "ADVERSARIAL_OPERATIONAL": "NEGATIVE", "FAULT_INJECTION": "CHAOS",
    "CROSS_CUTTING": "E2E",
}


def expand_risk_profiles(
    base_profiles: dict[str, dict[str, Any] | list[dict[str, Any]]],
    risk_conditions: list[dict[str, Any]],
    risk_candidates: list[dict[str, Any]],
    *, coverage_point_ids: set[str],
) -> tuple[dict[str, dict[str, Any] | list[dict[str, Any]]], dict[str, Any]]:
    """Append supported derived/exploratory candidates without fabricating policy."""
    profiles = deepcopy(base_profiles)
    conditions = {str(item.get("id")): item for item in risk_conditions}
    appended = 0
    exploratory = 0
    supported = 0
    class_counts: dict[str, int] = {}
    materialized_refs: list[str] = []
    for candidate in risk_candidates:
        risk_ref = str(candidate.get("risk_condition_ref", ""))
        condition = conditions.get(risk_ref)
        if condition is None:
            raise ValueError(f"Risk candidate references unknown condition {risk_ref or '<missing>'}")
        cp_ref = str(candidate.get("coverage_point_ref", ""))
        if cp_ref not in coverage_point_ids:
            raise ValueError(f"Risk candidate {risk_ref} references unknown Coverage Point {cp_ref}")
        profile = deepcopy(candidate.get("profile", {}))
        if not profile:
            raise ValueError(f"Risk candidate {risk_ref} requires a structured profile")
        oracle_support = str(condition.get("oracle_support", ""))
        supported += 1
        if oracle_support == "NORMATIVE":
            if not profile.get("normative_oracle"):
                raise ValueError(f"Derived risk {risk_ref} lacks its supported invariant")
            profile["test_basis"] = "DERIVED"
        elif oracle_support == "CHARACTERIZATION":
            if not profile.get("implementation_oracle"):
                raise ValueError(f"Characterization risk {risk_ref} lacks observed behavior")
            profile["test_basis"] = "CHARACTERIZATION"
        elif oracle_support == "UNDEFINED":
            if profile.get("normative_oracle") or not profile.get("question_refs"):
                raise ValueError(
                    f"Undefined risk {risk_ref} must remain exploratory with a focused Question"
                )
            profile["test_basis"] = "EXPLORATORY"
            profile["primary_type"] = "EXPLORATORY"
            profile["execution_status"] = "EXPLORATORY"
            exploratory += 1
        else:
            raise ValueError(f"Risk condition {risk_ref} has unsupported oracle_support")
        risk_class = str(condition.get("risk_class", "NEGATIVE"))
        mapped_type = PRIMARY_TYPE_BY_RISK.get(risk_class, risk_class)
        if profile.get("primary_type") in {None, "", "FUNCTIONAL"}:
            profile["primary_type"] = mapped_type
        profile.setdefault("secondary_tags", [f"risk:{risk_class.casefold().replace('_', '-')}"])
        profile["expansion_layer"] = "ADDITIVE"
        if candidate.get("evidence_pack"):
            profile["evidence_pack"] = deepcopy(candidate["evidence_pack"])
        profile["risk_condition_ref"] = risk_ref
        class_counts[risk_class] = class_counts.get(risk_class, 0) + 1
        materialized_refs.append(risk_ref)
        existing = profiles.get(cp_ref)
        if existing is None:
            profiles[cp_ref] = [profile]
        elif isinstance(existing, list):
            existing.append(profile)
        else:
            profiles[cp_ref] = [existing, profile]
        appended += 1
    return profiles, {
        "risk_candidates_added": appended,
        "risk_candidates_discovered": len(risk_conditions),
        "risk_candidates_supported": supported,
        "risk_candidates_materialized": appended,
        "risk_candidates_already_covered": 0,
        "risk_candidates_exploratory": exploratory,
        "risk_candidates_rejected": len(risk_conditions) - supported,
        "risk_candidates_unresolved": 0,
        "operator_error_candidates": class_counts.get("OPERATOR_ERROR", 0) + class_counts.get("MISUSE", 0),
        "operator_error_tests": class_counts.get("OPERATOR_ERROR", 0) + class_counts.get("MISUSE", 0),
        "chaos_tests": class_counts.get("CHAOS", 0) + class_counts.get("FAULT_INJECTION", 0),
        "recovery_tests": class_counts.get("RECOVERY", 0),
        "concurrency_tests": class_counts.get("CONCURRENCY", 0) + class_counts.get("RACE_CONDITION", 0),
        "resilience_tests": class_counts.get("RESILIENCE", 0),
        "security_derived_tests": class_counts.get("SECURITY", 0) + class_counts.get("AUTHORIZATION", 0),
        "materialized_risk_refs": materialized_refs,
        "exploratory_policy_gaps": exploratory,
    }
