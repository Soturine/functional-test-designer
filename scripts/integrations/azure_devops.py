#!/usr/bin/env python3
"""Preview-first, idempotent Azure DevOps Test Plans adapter contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol


class AzureTransport(Protocol):
    def create_test_case(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_test_case(self, external_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def map_test_case(case: dict[str, Any]) -> dict[str, Any]:
    """Map portable Test Plan concepts plus the execution context an executor needs to run
    the case without the canonical suite at hand: its fixture definitions (test_data), its
    end state and cleanup, and whether state is restored by the case itself or by a harness
    reset (state_contract). The canonical suite remains authoritative."""
    return {
        "local_id": case["id"],
        "title": case["title"],
        "priority": case["priority"],
        "preconditions": list(case.get("preconditions") or []),
        "test_data": [dict(row) for row in case.get("test_data") or []],
        "steps": [
            {"action": step["action"], "expected_result": step.get("expected_result")}
            for step in case.get("steps", [])
        ],
        "postconditions": list(case.get("postconditions") or []),
        "cleanup": list(case.get("cleanup") or []),
        "tags": list(case.get("tags", [])),
        "trace_refs": {
            "requirements": list(case.get("requirement_refs", [])),
            "coverage_points": list(case.get("coverage_point_refs", [])),
            "related_test_cases": list(case.get("related_test_cases") or []),
        },
        "status": case["status"],
        "source_kind": case.get("source_kind", "CANONICAL"),
        "automation": {
            "suitability": case.get("automation_suitability"),
            "readiness": case.get("automation_readiness"),
            "readiness_blockers": list(case.get("readiness_blockers") or []),
            "layer": case.get("automation_layer"),
            "tool_hint": case.get("automation_tool_hint"),
        },
        "execution": {
            "state_contract": case.get("state_contract") or ("SELF_CLEANING" if case.get("cleanup") else "REQUIRES_FIXTURE_RESET"),
            "required_resources": list(case.get("required_resources") or []),
            "environment_requirements": list(case.get("environment_requirements") or []),
            "variants": [dict(v) for v in case.get("execution_variants") or []],
            "request_contract": dict(case["request_contract"]) if case.get("request_contract") else None,
        },
    }


RISK_SUITE_TAGS = (
    "negative", "operator-error", "adversarial", "resilience", "fault-injection",
    "recovery", "concurrency", "e2e", "cross-cutting", "security", "data-integrity",
)


def build_group_suite_mapping(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Azure Test Plan/Suite placement for arbitrary named groups.

    Each group is `{"suite": name, "suite_type": optional, "export_keys": [...]}`.
    One export key may belong to several groups without being cloned — this is the
    generic Azure-side placement mechanism `ftd-azure` uses for requirement-by-
    requirement organization, and the same one `build_suite_mapping` below uses for
    risk-tag static suites. Callers (e.g. azure_export.py) decide what a "group" means
    in their own domain; this function only owns the Azure suite-membership shape.
    """
    memberships: dict[str, list[dict[str, Any]]] = {}
    suite_members: dict[str, list[str]] = {}
    for group in groups:
        suite = group["suite"]
        for key in group.get("export_keys", []):
            memberships.setdefault(key, []).append(
                {"suite": suite, "suite_type": group.get("suite_type", "REQUIREMENT_BASED")}
            )
            suite_members.setdefault(suite, []).append(key)
    # Members keep the order the caller gave (e.g. operational flow); suites keep theirs too.
    return {
        "memberships": [{"local_id": key, "suites": suites} for key, suites in memberships.items()],
        "suite_members": {name: list(dict.fromkeys(keys)) for name, keys in suite_members.items()},
        "canonical_test_cases": len(memberships), "cloned_test_cases": 0,
    }


def build_suite_mapping(
    cases: list[dict[str, Any]],
    *,
    requirement_suite: str,
    risk_suites: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Place one canonical Test Case in several organizational views without cloning it.

    Azure DevOps suites are folders over the same work item. A requirement-backed
    case belongs to its requirement suite and may also appear in a risk-oriented
    static suite; the semantic Test Case is never duplicated to achieve that.
    """
    risk_suites = risk_suites or {tag: f"Operational {tag}" for tag in RISK_SUITE_TAGS}
    unsupported = sorted(set(risk_suites) - set(RISK_SUITE_TAGS))
    if unsupported:
        raise ValueError("Unsupported risk suite tags: " + ", ".join(unsupported))
    suites: dict[str, list[str]] = {}
    memberships: list[dict[str, Any]] = []
    for case in cases:
        local_id = str(case["id"])
        tags = [str(value).strip().casefold() for value in case.get("tags", [])]
        targets = []
        if case.get("requirement_refs"):
            targets.append({"suite": requirement_suite, "suite_type": "REQUIREMENT_BASED"})
        for tag in RISK_SUITE_TAGS:
            if tag in tags and tag in risk_suites:
                targets.append({
                    "suite": risk_suites[tag], "suite_type": "STATIC", "tag": tag,
                })
        if not targets:
            targets.append({"suite": requirement_suite, "suite_type": "REQUIREMENT_BASED"})
        for target in targets:
            suites.setdefault(target["suite"], []).append(local_id)
        memberships.append({
            "local_id": local_id,
            "requirement_refs": list(case.get("requirement_refs", [])),
            "suites": targets,
        })
    return {
        "requirement_suite": requirement_suite,
        "memberships": memberships,
        "suite_members": {name: sorted(dict.fromkeys(ids)) for name, ids in sorted(suites.items())},
        "canonical_test_cases": len({item["local_id"] for item in memberships}),
        "suite_placements": sum(len(item["suites"]) for item in memberships),
        "cloned_test_cases": 0,
    }


def build_preview(
    cases: list[dict[str, Any]], mapping: dict[str, Any], *,
    project: str, plan: str, suite: str, include_needs_review: bool = False,
    external_versions: dict[str, str] | None = None,
    suite_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external_versions = external_versions or {}
    result: dict[str, Any] = {
        "target": {"project": project, "plan": plan, "suite": suite},
        "create": [], "update": [], "unchanged": [], "skipped": [], "conflicts": [],
    }
    if suite_mapping is not None:
        result["suite_mapping"] = suite_mapping
    entries = mapping.get("test_cases", {})
    for case in cases:
        payload = map_test_case(case)
        content_hash = _hash(payload)
        if case["status"] == "BLOCKED" or (case["status"] == "NEEDS_REVIEW" and not include_needs_review):
            result["skipped"].append({"local_id": case["id"], "status": case["status"]})
            continue
        prior = entries.get(case["id"])
        candidate = {"local_id": case["id"], "content_hash": content_hash, "payload": payload}
        if not prior:
            result["create"].append(candidate)
        elif prior.get("content_hash") == content_hash:
            result["unchanged"].append({"local_id": case["id"], "external_id": prior["external_id"]})
        elif external_versions.get(prior["external_id"], prior.get("last_synchronized_version")) != prior.get("last_synchronized_version"):
            result["conflicts"].append({"local_id": case["id"], "external_id": prior["external_id"]})
        else:
            result["update"].append({**candidate, "external_id": prior["external_id"]})
    return result


def apply_preview(preview: dict[str, Any], transport: AzureTransport, *, approved: bool = False) -> list[dict[str, Any]]:
    if not approved:
        return []
    if preview["conflicts"]:
        raise ValueError("Resolve preview conflicts before external writes")
    results = [transport.create_test_case(item["payload"]) for item in preview["create"]]
    results.extend(transport.update_test_case(item["external_id"], item["payload"]) for item in preview["update"])
    return results


def write_fallback_export(root: Path, preview: dict[str, Any]) -> list[Path]:
    destination = root / "exports" / "azure-devops"
    destination.mkdir(parents=True, exist_ok=True)
    documents = {
        "import-plan.json": {"target": preview["target"], "operation": "preview-only"},
        "test-case-payloads.json": {"create": preview["create"], "update": preview["update"]},
        "mapping-preview.json": preview,
    }
    paths = []
    for name, document in documents.items():
        path = destination / name
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _integration_state_path(run_dir: Path) -> Path:
    return Path(run_dir) / "integration-state" / "azure-devops.json"


def persist_integration_state(run_dir: Path, state: dict[str, Any]) -> Path:
    """Persist non-secret idempotency metadata under the private run directory."""
    path = _integration_state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def load_integration_state(run_dir: Path) -> dict[str, Any]:
    """The read side of `persist_integration_state`; empty state when nothing was synced yet."""
    path = _integration_state_path(run_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"test_cases": {}}
