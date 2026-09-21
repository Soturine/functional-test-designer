#!/usr/bin/env python3
"""Objective human and automation executability audits for frozen Test Cases."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from execution_quality import hidden_subtest_warnings, path_compression_warnings
from scenario_independence import TestIdentity


ABSTRACT_TRIGGER_PATTERNS = (
    r"\b(?:execute|perform|carry out|complete) (?:the )?(?:action|operation|process|flow) (?:described|indicated|applicable|appropriate|in the objective)\b",
    r"\b(?:proceed|continue) (?:as|when) applicable\b",
    r"\buse the (?:appropriate|correct) (?:item|record|option)\b",
    r"\b(?:executar|acionar|realizar) (?:a|o) (?:ação|operação|processo|fluxo) (?:descrita|indicado|aplicável|adequado|do objetivo)\b",
    r"\b(?:prosseguir|continuar) conforme (?:necessário|aplicável)\b",
    r"\bselecionar (?:o|a) (?:item|registro|opção) (?:correto|correta|adequado|adequada)\b",
)
ABSTRACT_NAVIGATION_PATTERNS = (
    r"\b(?:navigate|go|access) (?:appropriately|as applicable|the applicable area)\b",
    r"\b(?:navegar|acessar) (?:adequadamente|conforme aplicável|a área aplicável)\b",
)
ABSTRACT_OBSERVATION_PATTERNS = (
    r"\bthe (?:step|flow|next step) (?:becomes|remains|is) available\b",
    r"\bthe next step can be performed\b",
    r"\bvalidate that it worked\b",
    r"\b(?:a etapa|o fluxo) (?:fica disponível|segue normalmente)\b",
    r"\bvalidar que funcionou\b",
)
PLACEHOLDER_DATA_PATTERNS = (
    r"^<.+>$",
    r"\b(?:valid[_ -]?item|existing (?:record|object)|appropriate record|partition[-_ ]?\d+|data defined for the case|availability_balance)\b",
)
DETERMINISTIC_ACQUISITION = re.compile(
    r"\b(?:select|use|choose|locate)\b.+\b(?:with|where|having)\b.+\b(?:record|note|capture)\b.+\bid\b",
    re.IGNORECASE,
)
CONCRETE_VALUE = re.compile(
    r"(?:\b[\w -]+\s*=\s*[^\s,;]+|\b\d+(?:\.\d+)?\b|\{.+\}|\b[A-Z][A-Z0-9_-]{2,}\b)"
)


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def classify_test_data(items: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = []
    classifications = []
    if not items:
        return {"classification": "MISSING", "reasons": ["MISSING_TEST_DATA"], "items": []}
    for item in items:
        text = " ".join(str(item.get(key, "")) for key in ("name", "description", "value")).strip()
        if _matches(text, PLACEHOLDER_DATA_PATTERNS):
            kind = "PLACEHOLDER"
            reasons.append("PLACEHOLDER_TEST_DATA")
        elif DETERMINISTIC_ACQUISITION.search(text):
            kind = "DETERMINISTIC_ACQUISITION"
        elif CONCRETE_VALUE.search(text):
            kind = "CONCRETE"
        else:
            kind = "NONDETERMINISTIC"
            reasons.append("NONDETERMINISTIC_TEST_DATA")
        classifications.append({"description": text, "classification": kind})
    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "classification": "READY" if not unique_reasons else "NOT_READY",
        "reasons": unique_reasons,
        "items": classifications,
    }


def procedural_reason_codes(
    case: dict[str, Any], identity: TestIdentity | None = None,
    execution_context: dict[str, Any] | None = None,
) -> list[str]:
    reasons: list[str] = []
    actions = [str(step.get("action", "")) for step in case.get("steps", [])]
    expected = [step.get("expected_result") for step in case.get("steps", [])]
    if not case.get("preconditions"):
        reasons.append("MISSING_STARTING_CONTEXT")
    if not actions:
        reasons.append("MISSING_TRIGGER")
    for action in actions:
        if _matches(action, ABSTRACT_TRIGGER_PATTERNS):
            reasons.append("ABSTRACT_TRIGGER")
        if _matches(action, ABSTRACT_NAVIGATION_PATTERNS):
            reasons.append("ABSTRACT_NAVIGATION")
    for observation in expected:
        if observation is None:
            reasons.append("MISSING_OBSERVABLE_ASSERTION")
        elif _matches(str(observation), ABSTRACT_OBSERVATION_PATTERNS):
            reasons.append("ABSTRACT_OBSERVATION")
    reasons.extend(classify_test_data(case.get("test_data", []))["reasons"])
    if any(step.get("needs_clarification") for step in case.get("steps", [])):
        reasons.append("PROCEDURE_GAP")
    if hidden_subtest_warnings([case]):
        reasons.append("HIDDEN_SUBTEST")
    context = execution_context or {}
    known_length = int(context.get("known_path_actions", len(actions) or 0))
    if path_compression_warnings([case], {str(case.get("id")): known_length}):
        reasons.append("PATH_COMPRESSION")
    if context.get("execution_surface_required") and not context.get("execution_surface"):
        reasons.append("MISSING_EXECUTION_SURFACE")
    if context.get("record_required") and classify_test_data(case.get("test_data", []))["classification"] != "READY":
        reasons.append("MISSING_RECORD_ACQUISITION_RULE")
    if context.get("intermediate_observation_required") and len(actions) > 1:
        if any(value is None for value in expected[:-1]):
            reasons.append("MISSING_INTERMEDIATE_OBSERVATION")
    if identity is not None:
        if not identity.execution_boundary:
            reasons.append("MISSING_EXECUTION_BOUNDARY")
        if not identity.test_data_partition:
            reasons.append("MISSING_DATA_PARTITION")
        targets = [item.observation_target.strip().casefold() for item in identity.assertions]
        if not identity.assertions:
            reasons.append("MISSING_TRACEABLE_ASSERTIONS")
        elif any(not target for target in targets) or len(targets) != len(set(targets)):
            reasons.append("INSUFFICIENT_ASSERTION_DISCRIMINATION")
        signature = identity.execution_signature
        if signature and not signature.actor_permission:
            reasons.append("MISSING_ACTOR_ACCESS")
        if signature and not signature.starting_state and not identity.material_preconditions:
            reasons.append("MISSING_STARTING_STATE")
        if signature and not signature.trigger:
            reasons.append("MISSING_TRIGGER")
        if not case.get("steps") or case["steps"][-1].get("expected_result") != identity.normative_oracle:
            reasons.append("NORMATIVE_ORACLE_NOT_OBSERVABLE")
    if case.get("status") != "READY":
        reasons.append("STATUS_NOT_READY")
    return list(dict.fromkeys(reasons))


def audit_execution_readiness(
    case: dict[str, Any], identity: TestIdentity | None = None,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons = procedural_reason_codes(case, identity, execution_context)
    human_blockers = set(reasons) - {"MISSING_EXECUTION_BOUNDARY", "MISSING_DATA_PARTITION"}
    return {
        "test_case_id": case.get("id"),
        "human_classification": "HUMAN_EXECUTION_READY" if not human_blockers else "HUMAN_EXECUTION_NOT_READY",
        "automation_classification": "AUTOMATION_EXECUTION_READY" if not reasons else "AUTOMATION_EXECUTION_NOT_READY",
        "reason_codes": reasons,
        "test_data": classify_test_data(case.get("test_data", [])),
        "assertions": [asdict(item) for item in identity.assertions] if identity else [],
    }


def align_public_status(case: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    """Prevent a materially non-executable case from being presented as simply READY."""
    material = {
        "ABSTRACT_TRIGGER", "ABSTRACT_NAVIGATION", "MISSING_OBSERVABLE_ASSERTION",
        "PROCEDURE_GAP", "HIDDEN_SUBTEST", "PATH_COMPRESSION",
        "MISSING_EXECUTION_SURFACE", "MISSING_RECORD_ACQUISITION_RULE",
        "MISSING_INTERMEDIATE_OBSERVATION", "PLACEHOLDER_TEST_DATA",
        "NONDETERMINISTIC_TEST_DATA", "MISSING_TEST_DATA",
    }
    if case.get("status") == "READY" and material.intersection(audit.get("reason_codes", [])):
        case["status"] = "NEEDS_REVIEW"
    return case


def automation_plan(case: dict[str, Any], identity: TestIdentity) -> dict[str, Any]:
    audit = audit_execution_readiness(case, identity)
    return {
        "tc_id": identity.id,
        "classification": audit["automation_classification"],
        "execution_boundary": identity.execution_boundary,
        "preconditions": list(case.get("preconditions", [])),
        "test_data": list(case.get("test_data", [])),
        "ordered_actions": [step.get("action") for step in case.get("steps", [])],
        "assertions": [asdict(item) for item in identity.assertions],
        "cleanup": list(case.get("cleanup", [])),
        "unsupported_details": audit["reason_codes"],
        "provenance": list(case.get("source_refs", [])),
    }
