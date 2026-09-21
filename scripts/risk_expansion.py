#!/usr/bin/env python3
"""Evidence-grounded v2.2 risk expansion after normative atomic design."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def expand_risk_profiles(
    base_profiles: dict[str, dict[str, Any] | list[dict[str, Any]]],
    risk_conditions: list[dict[str, Any]],
    risk_candidates: list[dict[str, Any]],
    *, coverage_point_ids: set[str],
) -> tuple[dict[str, dict[str, Any] | list[dict[str, Any]]], dict[str, int]]:
    """Append supported derived/exploratory candidates without fabricating policy."""
    profiles = deepcopy(base_profiles)
    conditions = {str(item.get("id")): item for item in risk_conditions}
    appended = 0
    exploratory = 0
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
        profile.setdefault("primary_type", str(condition.get("risk_class", "NEGATIVE")))
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
        "exploratory_policy_gaps": exploratory,
    }
