#!/usr/bin/env python3
"""Candidate-first scenario independence and conservative merge decisions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


ALLOWED_MERGE_REASONS = {
    "INSEPARABLE_SAME_EVENT",
    "SHARED_PASS_FAIL_BOUNDARY",
    "SHARED_EXECUTION_OBSERVATIONS",
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


@dataclass(frozen=True)
class AssertionObservation:
    """One atomic oracle observed from a Scenario execution."""

    coverage_point_ref: str
    requirement_ref: str
    oracle: str
    observation_target: str = ""
    evidence_source: tuple[tuple[str, str], ...] = ()
    observation_phase: str = "after_trigger"


@dataclass(frozen=True)
class ExecutionSignature:
    """Semantic execution boundary used only after every CP has a candidate."""

    actor_permission: str
    setup: str
    starting_state: str
    preconditions: tuple[str, ...]
    input_partition: str
    trigger: str
    transaction_event: str
    environment_platform: str
    reset_required: bool
    path_objective: str
    execution_boundary: str


@dataclass(frozen=True)
class TestIdentity:
    """Immutable WHAT-to-test boundary passed to execution synthesis."""

    id: str
    title: str
    scenario_ref: str
    scenario_type: str
    requirement_refs: tuple[str, ...]
    coverage_point_refs: tuple[str, ...]
    normative_source_refs: tuple[tuple[str, str], ...]
    normative_oracle: str
    objective: str = ""
    material_preconditions: tuple[str, ...] = ()
    test_data_partition: str = ""
    assertions: tuple[AssertionObservation, ...] = ()
    execution_signature: ExecutionSignature | None = None
    execution_boundary: str = ""


IDENTITY_FIELDS = (
    "actor",
    "setup",
    "preconditions",
    "state",
    "trigger",
    "behavior",
    "input_partition",
    "oracle",
    "normative_oracle",
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
    "normative_oracle",
    "execution_evidence",
    "reporting_purpose",
    "pass_fail_boundary",
    "continuous_execution",
)


def _semantic_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _semantic_items(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({_semantic_text(value) for value in values if _semantic_text(value)}))


def execution_signature(candidate: dict[str, Any]) -> ExecutionSignature:
    """Build a normalized execution boundary; missing evidence remains visibly empty."""
    actor = candidate.get("actor") or candidate.get("permission")
    transaction = candidate.get("transaction") or candidate.get("event")
    environment = candidate.get("environment") or candidate.get("platform")
    path_objective = candidate.get("execution_path_objective") or candidate.get("objective")
    boundary = candidate.get("execution_boundary") or candidate.get("pass_fail_boundary")
    return ExecutionSignature(
        actor_permission=_semantic_text(actor),
        setup=_semantic_text(candidate.get("setup")),
        starting_state=_semantic_text(candidate.get("starting_state") or candidate.get("state")),
        preconditions=_semantic_items(
            candidate.get("material_preconditions", candidate.get("preconditions", []))
        ),
        input_partition=_semantic_text(candidate.get("input_partition")),
        trigger=_semantic_text(candidate.get("trigger")),
        transaction_event=_semantic_text(transaction),
        environment_platform=_semantic_text(environment),
        reset_required=bool(candidate.get("reset_required", False)),
        path_objective=_semantic_text(path_objective),
        execution_boundary=_semantic_text(boundary),
    )


def _assertion_for(
    coverage_point: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    refs = deepcopy(coverage_point.get("source_refs", []))
    return {
        "coverage_point_ref": str(coverage_point["id"]),
        "requirement_ref": str(coverage_point["requirement_ref"]),
        "oracle": str(profile.get("assertion_oracle", profile.get("normative_oracle", ""))),
        "observation_target": str(profile.get("observation_target", "")),
        "evidence_source": refs,
        "observation_phase": str(profile.get("observation_phase", "after_trigger")),
    }


def candidate_from_coverage_point(
    coverage_point: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Materialize one independently reviewable candidate before any grouping."""
    candidate = deepcopy(profile)
    candidate.setdefault("id", f"CAND-{coverage_point['id']}")
    candidate["coverage_point_refs"] = [coverage_point["id"]]
    candidate.setdefault("requirement_refs", [coverage_point["requirement_ref"]])
    normative_refs = deepcopy(coverage_point.get("source_refs", []))
    contributed_refs = candidate.get("source_refs", [])
    candidate["normative_source_refs"] = normative_refs
    candidate["source_refs"] = normative_refs + [
        ref for ref in contributed_refs if ref not in normative_refs
    ]
    candidate.setdefault("claim_refs", [])
    candidate.setdefault("clause_refs", deepcopy(coverage_point.get("clause_refs", [])))
    candidate.setdefault("can_fail_independently", True)
    candidate.setdefault("assertions", [_assertion_for(coverage_point, profile)])
    candidate["execution_signature"] = execution_signature(candidate)
    return candidate


def _same(candidate: dict[str, Any], other: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(candidate.get(field) == other.get(field) for field in fields)


def merge_reason(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    """Return an objective merge reason, defaulting uncertainty to separation."""
    if _same(left, right, IDENTITY_FIELDS):
        return "TRUE_SEMANTIC_DUPLICATE"

    left_reason = left.get("merge_reason")
    right_reason = right.get("merge_reason")
    if left_reason == right_reason == "SHARED_EXECUTION_OBSERVATIONS":
        family = left.get("execution_family")
        if not family or family != right.get("execution_family"):
            return None
        if (
            left.get("observation_from_same_execution") is not True
            or right.get("observation_from_same_execution") is not True
            or left.get("requires_independent_rerun", True)
            or right.get("requires_independent_rerun", True)
        ):
            return None
        left_signature = left.get("execution_signature") or execution_signature(left)
        right_signature = right.get("execution_signature") or execution_signature(right)
        required = (
            left_signature.actor_permission,
            left_signature.setup,
            left_signature.starting_state,
            left_signature.input_partition,
            left_signature.trigger,
            left_signature.path_objective,
            left_signature.execution_boundary,
        )
        if not all(required) or left_signature != right_signature:
            return None
        return "SHARED_EXECUTION_OBSERVATIONS"

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
                "normative_source_refs",
                "claim_refs",
                "clause_refs",
                "observations",
                "assertions",
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
        "scenario_cohesion_decisions": sum(
            item["reason"] == "SHARED_EXECUTION_OBSERVATIONS" for item in decisions
        ),
        "traceable_assertions": sum(len(item.get("assertions", [])) for item in scenarios),
        "test_cases_generated": len(scenarios),
    }


def build_scenario_pipeline(
    coverage_points: list[dict[str, Any]],
    profiles_by_coverage_point: dict[str, dict[str, Any] | list[dict[str, Any]]],
) -> dict[str, Any]:
    """Run the production CP -> candidate -> merge -> frozen identity boundary."""
    testable = [item for item in coverage_points if item.get("disposition") == "TEST_CASE"]
    candidates: list[dict[str, Any]] = []
    for coverage_point in testable:
        cp_id = coverage_point["id"]
        raw_profiles = profiles_by_coverage_point.get(cp_id)
        if raw_profiles is None:
            raise ValueError(f"Testable Coverage Point {cp_id} has no scenario candidate profile")
        profiles = raw_profiles if isinstance(raw_profiles, list) else [raw_profiles]
        if not profiles:
            raise ValueError(f"Testable Coverage Point {cp_id} has no scenario candidate profile")
        for number, profile in enumerate(profiles, 1):
            candidate = candidate_from_coverage_point(coverage_point, profile)
            if len(profiles) > 1:
                candidate["id"] = f"CAND-{cp_id}-{number:02d}"
            candidates.append(candidate)

    represented = {
        cp_id for candidate in candidates for cp_id in candidate.get("coverage_point_refs", [])
    }
    missing = {item["id"] for item in testable} - represented
    if missing:
        raise ValueError(
            "Testable Coverage Points disappeared before candidate review: "
            + ", ".join(sorted(missing))
        )
    if len(candidates) < len(testable):
        raise ValueError("Scenario candidate count is lower than testable Coverage Point count")

    scenarios, decisions = merge_candidates(candidates)
    reduction = len(candidates) - len(scenarios)
    if reduction != len(decisions):
        raise ValueError(
            "Candidate-to-scenario reduction is not explained by explicit merge decisions"
        )

    identities: list[TestIdentity] = []
    for number, scenario in enumerate(scenarios, 1):
        scenario_id = f"SCN-{number:03d}"
        tc_id = f"TC-{number:03d}"
        scenario["id"] = scenario_id
        scenario["title"] = scenario.get("title") or scenario.get("behavior") or scenario_id
        scenario["type"] = scenario.get("scenario_type", "HAPPY_PATH")
        oracle = scenario.get("normative_oracle")
        if not isinstance(oracle, str) or not oracle.strip():
            raise ValueError(f"{scenario_id} has no normative oracle")
        raw_assertions = scenario.get("assertions", [])
        assertion_cp_refs = {
            str(item.get("coverage_point_ref")) for item in raw_assertions if isinstance(item, dict)
        }
        if assertion_cp_refs != set(scenario.get("coverage_point_refs", [])):
            raise ValueError(f"{scenario_id} does not preserve one assertion per Coverage Point")
        assertions = tuple(
            AssertionObservation(
                coverage_point_ref=str(item["coverage_point_ref"]),
                requirement_ref=str(item["requirement_ref"]),
                oracle=str(item["oracle"]),
                observation_target=str(item.get("observation_target", "")),
                evidence_source=tuple(
                    (str(ref["source"]), str(ref["reference"]))
                    for ref in item.get("evidence_source", [])
                ),
                observation_phase=str(item.get("observation_phase", "after_trigger")),
            )
            for item in raw_assertions
        )
        distinct_oracles = list(dict.fromkeys(item.oracle for item in assertions if item.oracle))
        if len(distinct_oracles) > 1:
            oracle = "\n".join(
                f"{item.coverage_point_ref}: {item.oracle}" for item in assertions
            )
        source_refs = tuple(
            (str(ref["source"]), str(ref["reference"]))
            for ref in scenario.get("normative_source_refs", [])
        )
        identities.append(
            TestIdentity(
                id=tc_id,
                title=str(scenario["title"]),
                scenario_ref=scenario_id,
                scenario_type=str(scenario["type"]),
                requirement_refs=tuple(scenario.get("requirement_refs", [])),
                coverage_point_refs=tuple(scenario.get("coverage_point_refs", [])),
                normative_source_refs=source_refs,
                normative_oracle=oracle,
                objective=str(scenario.get("objective", scenario["title"])),
                material_preconditions=tuple(
                    str(value)
                    for value in scenario.get(
                        "material_preconditions", scenario.get("preconditions", [])
                    )
                ),
                test_data_partition=str(scenario.get("input_partition", "")),
                assertions=assertions,
                execution_signature=scenario.get("execution_signature")
                or execution_signature(scenario),
                execution_boundary=str(
                    scenario.get("execution_boundary", scenario.get("pass_fail_boundary", ""))
                ),
            )
        )

    warnings = audit_multi_cp_scenarios(scenarios)
    observed = metrics(len(coverage_points), candidates, scenarios, decisions)
    observed["testable_coverage_points"] = len(testable)
    observed["possible_scenario_overcompression_warnings"] = len(warnings)
    return {
        "candidates": candidates,
        "merge_decisions": decisions,
        "scenarios": scenarios,
        "test_identities": identities,
        "warnings": warnings,
        "metrics": observed,
    }
