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
    normative_oracle: str | None
    objective: str = ""
    material_preconditions: tuple[str, ...] = ()
    test_data_partition: str = ""
    assertions: tuple[AssertionObservation, ...] = ()
    execution_signature: ExecutionSignature | None = None
    execution_boundary: str = ""
    test_basis: str = "ACCEPTANCE"
    primary_type: str = "FUNCTIONAL"
    secondary_tags: tuple[str, ...] = ()
    question_refs: tuple[str, ...] = ()
    finding_refs: tuple[str, ...] = ()
    composes: tuple[str, ...] = ()
    automation_candidate: bool = False
    automation_layer: str = "NONE"
    automation_tool_hint: str = "NONE"
    deterministic: bool = True
    execution_status: str = "READY"


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
    cohesion_audit_trail = []
    for number, decision in enumerate(decisions, 1):
        resulting = next(
            scenario for scenario in scenarios
            if set(decision["candidate_ids"]).issubset(set(scenario["candidate_ids"]))
        )
        signature = resulting.get("execution_signature") or execution_signature(resulting)
        cohesion_audit_trail.append({
            "decision_id": f"COH-{number:03d}",
            "candidate_refs": list(decision["candidate_ids"]),
            "coverage_point_refs": list(resulting.get("coverage_point_refs", [])),
            "execution_signature": {
                "actor_permission": signature.actor_permission,
                "starting_state": signature.starting_state,
                "input_partition": signature.input_partition,
                "trigger": signature.trigger,
                "execution_boundary": signature.execution_boundary,
            },
            "reason": decision["reason"],
            "observation_compatibility": decision["reason"] in ALLOWED_MERGE_REASONS,
            "resulting_scenario": resulting["id"],
        })
    return {
        "candidates": candidates,
        "merge_decisions": decisions,
        "scenarios": scenarios,
        "test_identities": identities,
        "warnings": warnings,
        "metrics": observed,
        "cohesion_audit_trail": cohesion_audit_trail,
    }


V22_TEST_BASES = {
    "ACCEPTANCE", "CHARACTERIZATION", "DERIVED", "EXPLORATORY", "REGRESSION", "E2E",
}
V22_PRIMARY_TYPES = {
    "FUNCTIONAL", "NEGATIVE", "BOUNDARY", "SECURITY", "AUTHORIZATION", "PERFORMANCE",
    "RESILIENCE", "RECOVERY", "CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY",
    "INTEGRATION", "CONTRACT", "DATA_INTEGRITY", "AUDIT", "STATE_TRANSITION", "E2E",
    "FIELD", "HARDWARE_INTEGRATION", "CHAOS", "EXPLORATORY",
}
V22_EXECUTION_STATUSES = {
    "READY", "NEEDS_REVIEW", "BLOCKED_REQUIREMENT", "BLOCKED_IMPLEMENTATION_GAP",
    "BLOCKED_ENVIRONMENT", "BLOCKED_TEST_DATA", "BLOCKED_EXTERNAL_DEPENDENCY", "EXPLORATORY",
}


def _v22_family_key(candidate: dict[str, Any]) -> str:
    explicit = candidate.get("scenario_family") or candidate.get("scenario_family_key")
    if explicit:
        return _semantic_text(explicit)
    requirements = candidate.get("requirement_refs", [])
    return _semantic_text(requirements[0] if requirements else candidate.get("behavior"))


def _v22_merge_suggestions(
    candidates: list[dict[str, Any]], candidate_to_tc: dict[str, str]
) -> list[dict[str, Any]]:
    """Describe possible manual compaction without deleting canonical atomic cases."""
    suggestions: list[dict[str, Any]] = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            same_event = bool(left.get("event")) and left.get("event") == right.get("event")
            same_setup = (
                left.get("actor") == right.get("actor")
                and left.get("setup") == right.get("setup")
                and left.get("state") == right.get("state")
            )
            explicit = (
                left.get("merge_candidate_group")
                and left.get("merge_candidate_group") == right.get("merge_candidate_group")
            )
            if not explicit and not (same_event and same_setup):
                continue
            suggestions.append({
                "test_case_ids": [candidate_to_tc[left["id"]], candidate_to_tc[right["id"]]],
                "reason": "same business event" if same_event else "shared execution setup",
                "shared_setup": same_setup,
                "shared_business_event": same_event,
                "manual_execution_benefit": "HIGH" if same_setup else "MEDIUM",
                "automation_tradeoff": "LOSES_INDEPENDENT_FAILURE_DIAGNOSIS",
                "confidence": "HIGH" if explicit or (same_event and same_setup) else "MEDIUM",
            })
    for number, item in enumerate(suggestions, 1):
        item["merge_candidate_id"] = f"MC-{number:03d}"
    return suggestions


def build_scenario_family_pipeline(
    coverage_points: list[dict[str, Any]],
    profiles_by_coverage_point: dict[str, dict[str, Any] | list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build the v2.2 atomic view: Scenario families organize TCs and never compress them."""
    testable = [item for item in coverage_points if item.get("disposition") == "TEST_CASE"]
    candidates: list[dict[str, Any]] = []
    for coverage_point in testable:
        cp_id = str(coverage_point["id"])
        raw_profiles = profiles_by_coverage_point.get(cp_id)
        if raw_profiles is None:
            raise ValueError(f"Testable Coverage Point {cp_id} has no scenario candidate profile")
        profiles = raw_profiles if isinstance(raw_profiles, list) else [raw_profiles]
        if not profiles:
            raise ValueError(f"Testable Coverage Point {cp_id} has no scenario candidate profile")
        for number, profile in enumerate(profiles, 1):
            candidate = candidate_from_coverage_point(coverage_point, profile)
            candidate["id"] = f"CAND-{cp_id}-{number:02d}" if len(profiles) > 1 else f"CAND-{cp_id}"
            basis = str(candidate.get("test_basis", "ACCEPTANCE"))
            primary_type = str(candidate.get("primary_type", "FUNCTIONAL"))
            execution_status = str(candidate.get("execution_status", "READY"))
            if basis not in V22_TEST_BASES:
                raise ValueError(f"{candidate['id']} has unsupported test_basis {basis}")
            if primary_type not in V22_PRIMARY_TYPES:
                raise ValueError(f"{candidate['id']} has unsupported primary_type {primary_type}")
            if execution_status not in V22_EXECUTION_STATUSES:
                raise ValueError(f"{candidate['id']} has unsupported execution_status {execution_status}")
            oracle = candidate.get("normative_oracle")
            if basis == "ACCEPTANCE" and (not isinstance(oracle, str) or not oracle.strip()):
                raise ValueError(f"{candidate['id']} acceptance test has no normative oracle")
            if basis == "CHARACTERIZATION" and not candidate.get("implementation_oracle"):
                raise ValueError(f"{candidate['id']} characterization test has no implementation oracle")
            if basis == "EXPLORATORY" and oracle:
                raise ValueError(f"{candidate['id']} exploratory test cannot claim a normative oracle")
            candidate["test_basis"] = basis
            candidate["primary_type"] = primary_type
            candidate["execution_status"] = execution_status
            candidate["scenario_family_key"] = _v22_family_key(candidate)
            candidates.append(candidate)

    # Allocate every normative Acceptance identity before additive candidates.
    # Post-baseline expansion can add tests, but cannot renumber the frozen suite.
    candidates.sort(key=lambda item: (
        item.get("test_basis") != "ACCEPTANCE"
        or item.get("expansion_layer") == "ADDITIVE"
    ))

    represented = {cp for item in candidates for cp in item.get("coverage_point_refs", [])}
    missing = {str(item["id"]) for item in testable} - represented
    if missing:
        raise ValueError(
            "Testable Coverage Points disappeared before atomic Test Case design: "
            + ", ".join(sorted(missing))
        )

    family_keys: list[str] = []
    for candidate in candidates:
        if candidate["scenario_family_key"] not in family_keys:
            family_keys.append(candidate["scenario_family_key"])
    family_ids = {key: f"SCN-{number:03d}" for number, key in enumerate(family_keys, 1)}
    candidate_to_tc = {candidate["id"]: f"TC-{number:03d}" for number, candidate in enumerate(candidates, 1)}
    identities: list[TestIdentity] = []
    for candidate in candidates:
        scenario_id = family_ids[candidate["scenario_family_key"]]
        tc_id = candidate_to_tc[candidate["id"]]
        source_refs = tuple(
            (str(ref["source"]), str(ref["reference"]))
            for ref in candidate.get("normative_source_refs", [])
        )
        raw_assertions = candidate.get("assertions", [])
        assertions = tuple(
            AssertionObservation(
                coverage_point_ref=str(item["coverage_point_ref"]),
                requirement_ref=str(item["requirement_ref"]),
                oracle=str(item.get("oracle", "")),
                observation_target=str(item.get("observation_target", "")),
                evidence_source=tuple(
                    (str(ref["source"]), str(ref["reference"]))
                    for ref in item.get("evidence_source", [])
                ),
                observation_phase=str(item.get("observation_phase", "after_trigger")),
            )
            for item in raw_assertions
        )
        final_oracle = candidate.get("normative_oracle")
        if candidate["test_basis"] == "CHARACTERIZATION":
            final_oracle = str(candidate["implementation_oracle"])
        identities.append(TestIdentity(
            id=tc_id,
            title=str(candidate.get("title") or candidate.get("behavior") or tc_id),
            scenario_ref=scenario_id,
            scenario_type="SCENARIO_FAMILY",
            requirement_refs=tuple(candidate.get("requirement_refs", [])),
            coverage_point_refs=tuple(candidate.get("coverage_point_refs", [])),
            normative_source_refs=source_refs,
            normative_oracle=final_oracle if isinstance(final_oracle, str) and final_oracle else None,
            objective=str(candidate.get("objective") or candidate.get("behavior") or candidate.get("title")),
            material_preconditions=tuple(map(str, candidate.get("material_preconditions", []))),
            test_data_partition=str(candidate.get("input_partition", "")),
            assertions=assertions,
            execution_signature=candidate.get("execution_signature") or execution_signature(candidate),
            execution_boundary=str(candidate.get("execution_boundary", "")),
            test_basis=candidate["test_basis"],
            primary_type=candidate["primary_type"],
            secondary_tags=tuple(map(str, candidate.get("secondary_tags", []))),
            question_refs=tuple(map(str, candidate.get("question_refs", []))),
            finding_refs=tuple(map(str, candidate.get("finding_refs", []))),
            composes=tuple(map(str, candidate.get("composes", []))),
            automation_candidate=bool(candidate.get("automation_candidate", False)),
            automation_layer=str(candidate.get("automation_layer", "NONE")),
            automation_tool_hint=str(candidate.get("automation_tool_hint", "NONE")),
            deterministic=bool(candidate.get("deterministic", True)),
            execution_status=candidate["execution_status"],
        ))

    families: list[dict[str, Any]] = []
    for key in family_keys:
        members = [item for item in candidates if item["scenario_family_key"] == key]
        families.append({
            "id": family_ids[key],
            "title": str(members[0].get("scenario_family_title") or members[0].get("scenario_family") or members[0].get("title") or key),
            "type": "SCENARIO_FAMILY",
            "requirement_refs": list(dict.fromkeys(
                ref for item in members for ref in item.get("requirement_refs", [])
            )),
            "coverage_point_refs": list(dict.fromkeys(
                ref for item in members for ref in item.get("coverage_point_refs", [])
            )),
            "test_case_refs": [candidate_to_tc[item["id"]] for item in members],
        })
    suggestions = _v22_merge_suggestions(candidates, candidate_to_tc)
    basis_counts = {basis: sum(item.test_basis == basis for item in identities) for basis in V22_TEST_BASES}
    return {
        "candidates": candidates,
        "merge_decisions": [],
        "merge_candidates": suggestions,
        "scenarios": families,
        "test_identities": identities,
        "warnings": [],
        "cohesion_audit_trail": [],
        "metrics": {
            "coverage_points": len(coverage_points),
            "testable_coverage_points": len(testable),
            "scenario_candidates_before_merge": len(candidates),
            "scenario_merge_candidates": len(suggestions),
            "scenario_merges_applied": 0,
            "scenarios_after_merge": len(families),
            "test_cases_generated": len(identities),
            "atomic_tests": sum(item.test_basis != "E2E" for item in identities),
            "flow_tests": basis_counts["E2E"],
            "e2e_tests": basis_counts["E2E"],
            "derived_tests": basis_counts["DERIVED"],
            "characterization_tests": basis_counts["CHARACTERIZATION"],
            "exploratory_tests": basis_counts["EXPLORATORY"],
            "merge_candidates": len(suggestions),
            "actual_merges": 0,
        },
    }
