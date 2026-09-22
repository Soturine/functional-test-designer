#!/usr/bin/env python3
"""Evidence-grounded adversarial, resilience, recovery, and E2E opportunity review.

The question this pass answers is how a real operator, device, integration,
concurrent process, or environment can make a documented workflow fail. It is a
review matrix, not a generator: a dimension only becomes a candidate when the
selected evidence supports both the condition and a defensible oracle, and an
undefined expected behavior becomes a characterization candidate plus a focused
Question rather than an invented recovery rule.

Accepted scenarios stay ordinary Test Cases. There is no parallel object model.
"""

from __future__ import annotations

from typing import Any


OPERATOR_RISK_CLASSES = {
    "NEGATIVE", "MISUSE", "OPERATOR_ERROR", "ADVERSARIAL_OPERATIONAL", "SECURITY",
}
INFRASTRUCTURE_RISK_CLASSES = {"RESILIENCE", "FAULT_INJECTION", "RECOVERY"}
FLOW_RISK_CLASSES = {"E2E", "CROSS_CUTTING"}
OTHER_RISK_CLASSES = {
    "CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY", "DATA_INTEGRITY",
    "INTEGRATION", "FIELD", "HARDWARE_INTEGRATION", "CHAOS", "AUTHORIZATION",
}
RISK_CLASSES = (
    OPERATOR_RISK_CLASSES | INFRASTRUCTURE_RISK_CLASSES | FLOW_RISK_CLASSES | OTHER_RISK_CLASSES
)

RISK_DIMENSIONS = (
    "actor", "authorization", "object_identity", "starting_state", "value_boundary",
    "sequence_order", "duplicate_replay", "concurrency", "integration", "device",
    "location", "time_timeout", "interruption_recovery", "cross_account_tenant",
    "unexpected_object",
)

FLOW_KINDS = {"MAIN_FLOW", "ALTERNATIVE_FLOW", "EXCEPTION_FLOW"}
FLOW_DISPOSITIONS = {
    "E2E_SCENARIO", "COVERED_BY_ATOMIC_SCENARIOS", "QUESTION", "NOT_TESTABLE", "OUT_OF_SCOPE",
}
ORACLE_SUPPORT = {"NORMATIVE", "CHARACTERIZATION", "UNDEFINED"}


class RiskCoverageError(ValueError):
    """Raised when a risk or flow review is unaccounted for or invents behavior."""


def _refs(value: Any) -> list[str]:
    return [str(item) for item in (value or [])]


def audit_risk_matrix(
    risk_conditions: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    *,
    question_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Give every evidence-supported risk condition exactly one explicit destination.

    A condition whose expected behavior the selected evidence does not define may
    still be worth executing, but only as a characterization candidate carrying a
    focused Question. It never acquires an invented normative oracle.
    """
    question_ids = question_ids or set()
    by_risk: dict[str, dict[str, Any]] = {}
    for item in opportunities:
        risk_ref = str(item.get("risk_condition_ref", "")).strip()
        if risk_ref:
            if risk_ref in by_risk:
                raise RiskCoverageError(f"Risk condition {risk_ref} is dispositioned more than once")
            by_risk[risk_ref] = item

    counts = {value: 0 for value in sorted(RISK_CLASSES)}
    dimensions = {value: 0 for value in RISK_DIMENSIONS}
    characterization = 0
    for condition in risk_conditions:
        condition_id = str(condition.get("id", "")).strip()
        if not condition_id:
            raise RiskCoverageError("Every risk condition requires an id")
        risk_class = str(condition.get("risk_class", ""))
        if risk_class not in RISK_CLASSES:
            raise RiskCoverageError(f"Risk condition {condition_id} requires a supported risk_class")
        dimension = str(condition.get("dimension", ""))
        if dimension not in RISK_DIMENSIONS:
            raise RiskCoverageError(f"Risk condition {condition_id} requires a supported dimension")
        if not condition.get("condition_support_refs"):
            raise RiskCoverageError(
                f"Risk condition {condition_id} is not supported by the selected evidence"
            )
        oracle_support = str(condition.get("oracle_support", ""))
        if oracle_support not in ORACLE_SUPPORT:
            raise RiskCoverageError(
                f"Risk condition {condition_id} requires an explicit oracle_support"
            )
        opportunity = by_risk.get(condition_id)
        if opportunity is None:
            raise RiskCoverageError(
                f"Evidence-supported risk condition {condition_id} has no opportunity disposition"
            )
        disposition = str(opportunity.get("disposition", ""))
        if oracle_support == "UNDEFINED":
            if disposition not in {"IMPLEMENTATION_CHARACTERIZATION", "QUESTION", "NOT_TESTABLE"}:
                raise RiskCoverageError(
                    f"Risk condition {condition_id} has no defined expected behavior and cannot "
                    "become a normative scenario"
                )
            if disposition != "NOT_TESTABLE":
                linked = set(_refs(opportunity.get("question_refs"))) | set(
                    _refs(opportunity.get("target_refs"))
                )
                if question_ids and not (linked & question_ids):
                    raise RiskCoverageError(
                        f"Risk condition {condition_id} requires a focused Question for its "
                        "undefined expected behavior"
                    )
            characterization += disposition == "IMPLEMENTATION_CHARACTERIZATION"
        elif oracle_support == "NORMATIVE" and disposition == "NEW_NORMATIVE_SCENARIO":
            if not opportunity.get("normative_support_refs"):
                raise RiskCoverageError(
                    f"Risk condition {condition_id} needs Functional Authority support for a "
                    "normative expected result"
                )
        counts[risk_class] += 1
        dimensions[dimension] += 1

    orphan = sorted(set(by_risk) - {str(item.get("id")) for item in risk_conditions})
    if orphan:
        raise RiskCoverageError(
            "Opportunities reference unknown risk conditions: " + ", ".join(orphan)
        )
    return {
        "risk_conditions_reviewed": len(risk_conditions),
        "risk_dimensions_exercised": sum(bool(value) for value in dimensions.values()),
        "adversarial_opportunities": sum(counts[value] for value in sorted(OPERATOR_RISK_CLASSES)),
        "negative_opportunities": counts["NEGATIVE"],
        "operator_error_opportunities": counts["OPERATOR_ERROR"],
        "misuse_opportunities": counts["MISUSE"],
        "security_opportunities": counts["SECURITY"],
        "resilience_opportunities": counts["RESILIENCE"] + counts["FAULT_INJECTION"],
        "recovery_opportunities": counts["RECOVERY"],
        "concurrency_opportunities": counts["CONCURRENCY"],
        "data_integrity_opportunities": counts["DATA_INTEGRITY"],
        "e2e_opportunities": counts["E2E"] + counts["CROSS_CUTTING"],
        "characterization_risk_candidates": characterization,
        "unaccounted_risk_conditions": 0,
        "risk_class_counts": counts,
        "risk_dimension_counts": dimensions,
    }


def audit_flow_coverage(
    flows: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Review documented main, alternative, and exception flows for E2E coverage.

    Atomic Coverage Point coverage does not prove workflow coverage, and an
    alternative flow is reviewed on its own rather than assumed to be covered by
    the main flow. An E2E Test Case stays one continuous rerunnable execution
    whose checkpoints trace back to atomic Coverage Points.
    """
    by_flow: dict[str, dict[str, Any]] = {}
    for item in opportunities:
        flow_ref = str(item.get("flow_ref", "")).strip()
        if flow_ref:
            if flow_ref in by_flow:
                raise RiskCoverageError(f"Flow {flow_ref} is dispositioned more than once")
            by_flow[flow_ref] = item

    counts = {value: 0 for value in sorted(FLOW_KINDS)}
    e2e_scenarios = 0
    for flow in flows:
        flow_id = str(flow.get("id", "")).strip()
        if not flow_id:
            raise RiskCoverageError("Every use-case flow requires an id")
        kind = str(flow.get("kind", ""))
        if kind not in FLOW_KINDS:
            raise RiskCoverageError(f"Flow {flow_id} requires a supported kind")
        if not flow.get("source_refs"):
            raise RiskCoverageError(f"Flow {flow_id} requires selected-evidence source_refs")
        opportunity = by_flow.get(flow_id)
        if opportunity is None:
            raise RiskCoverageError(f"Documented flow {flow_id} has no E2E review disposition")
        disposition = str(opportunity.get("flow_disposition", ""))
        if disposition not in FLOW_DISPOSITIONS:
            raise RiskCoverageError(f"Flow {flow_id} requires a supported flow_disposition")
        if disposition == "E2E_SCENARIO":
            if not opportunity.get("continuous_execution"):
                raise RiskCoverageError(
                    f"Flow {flow_id} is not one continuous rerunnable execution"
                )
            if len(_refs(opportunity.get("coverage_point_refs"))) < 2:
                raise RiskCoverageError(
                    f"Flow {flow_id} requires traced checkpoints across at least two Coverage Points"
                )
            e2e_scenarios += 1
        elif disposition in {"NOT_TESTABLE", "OUT_OF_SCOPE"} and not opportunity.get("reason"):
            raise RiskCoverageError(f"Flow {flow_id} requires a reason")
        counts[kind] += 1

    orphan = sorted(set(by_flow) - {str(item.get("id")) for item in flows})
    if orphan:
        raise RiskCoverageError("Opportunities reference unknown flows: " + ", ".join(orphan))
    return {
        "use_case_flows_reviewed": len(flows),
        "main_flows_reviewed": counts["MAIN_FLOW"],
        "alternative_flows_reviewed": counts["ALTERNATIVE_FLOW"],
        "exception_flows_reviewed": counts["EXCEPTION_FLOW"],
        "e2e_scenarios_promoted": e2e_scenarios,
        "unaccounted_use_case_flows": 0,
    }
