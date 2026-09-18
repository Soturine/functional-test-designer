#!/usr/bin/env python3
"""Evidence-grounded procedural synthesis after Test Case identity is frozen."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from execution_quality import hidden_subtest_signals
from scenario_independence import TestIdentity


IDENTITY_FIELDS = (
    "id",
    "title",
    "requirement_refs",
    "scenario_refs",
    "coverage_point_refs",
    "objective",
    "preconditions",
)


def _source_refs(identity: TestIdentity, pack: dict[str, Any]) -> list[dict[str, str]]:
    refs = [
        {"source": source, "reference": reference}
        for source, reference in identity.normative_source_refs
    ]
    for ref in pack.get("source_refs", []):
        normalized = {"source": str(ref["source"]), "reference": str(ref["reference"])}
        if normalized not in refs:
            refs.append(normalized)
    return refs


def compose_path(
    shared_actions: list[dict[str, Any]],
    branch_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reuse navigation without coupling the identities of branching Test Cases."""
    return deepcopy(shared_actions) + deepcopy(branch_actions)


def synthesize_test_case(
    identity: TestIdentity,
    evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    """Add HOW-to-execute fields while retaining immutable WHAT-to-test fields."""
    actions = deepcopy(evidence_pack.get("actions", []))
    if not actions:
        raise ValueError(f"{identity.id} has no supported procedural action")
    steps = []
    for index, item in enumerate(actions, 1):
        if item.get("independent_variant") or hidden_subtest_signals(str(item.get("action", ""))):
            raise ValueError(
                f"{identity.id} action {index} contains an independent variant or hidden subtest; "
                "return it to scenario design"
            )
        if index > 1 and item.get("depends_on_previous_step") is not True:
            raise ValueError(
                f"{identity.id} action {index} lacks dependency on the preceding procedural state"
            )
        is_final = index == len(actions)
        expected = identity.normative_oracle if is_final else item.get("expected_result")
        supported_intermediate = bool(item.get("evidence_source"))
        if not is_final and expected is not None and not supported_intermediate:
            expected = None
        steps.append(
            {
                "step": index,
                "action": str(item["action"]),
                "expected_result": expected,
                "needs_clarification": expected is None,
            }
        )

    frozen_preconditions = list(identity.material_preconditions)
    supplied_preconditions = deepcopy(evidence_pack.get("preconditions", []))
    if frozen_preconditions and supplied_preconditions and supplied_preconditions != frozen_preconditions:
        raise ValueError(f"Procedural synthesis changed frozen preconditions for {identity.id}")
    supplied_partition = str(evidence_pack.get("test_data_partition", ""))
    if identity.test_data_partition and supplied_partition and supplied_partition != identity.test_data_partition:
        raise ValueError(f"Procedural synthesis changed frozen test-data partition for {identity.id}")
    status = "NEEDS_REVIEW" if any(item["needs_clarification"] for item in steps) else "READY"
    objective = identity.objective or evidence_pack.get("objective", identity.title)
    case = {
        "schema_version": "1.2",
        "id": identity.id,
        "title": identity.title,
        "status": status,
        "priority": evidence_pack.get("priority", "MEDIUM"),
        "type": "FUNCTIONAL",
        "objective": objective,
        "requirement_refs": list(identity.requirement_refs),
        "scenario_refs": [identity.scenario_ref],
        "coverage_point_refs": list(identity.coverage_point_refs),
        "source_refs": _source_refs(identity, evidence_pack),
        "preconditions": frozen_preconditions or supplied_preconditions,
        "test_data": deepcopy(evidence_pack.get("test_data", [])),
        "steps": steps,
        "postconditions": deepcopy(evidence_pack.get("postconditions", [])),
        "cleanup": deepcopy(evidence_pack.get("cleanup", [])),
        "tags": deepcopy(evidence_pack.get("tags", [])),
        "notes": deepcopy(evidence_pack.get("notes", [])),
    }
    assert_identity_preserved(identity, case)
    return case


def assert_identity_preserved(identity: TestIdentity, case: dict[str, Any]) -> None:
    expected = {
        "id": identity.id,
        "title": identity.title,
        "requirement_refs": list(identity.requirement_refs),
        "scenario_refs": [identity.scenario_ref],
        "coverage_point_refs": list(identity.coverage_point_refs),
        "objective": identity.objective or case.get("objective"),
        "preconditions": list(identity.material_preconditions) or case.get("preconditions", []),
    }
    changed = [field for field in IDENTITY_FIELDS if case.get(field) != expected[field]]
    if changed:
        raise ValueError("Procedural synthesis changed frozen Test Case identity: " + ", ".join(changed))
    if case["steps"][-1]["expected_result"] != identity.normative_oracle:
        raise ValueError("Procedural synthesis replaced the normative oracle")
