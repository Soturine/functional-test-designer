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
    """Map only portable Test Plan concepts; the canonical suite remains authoritative."""
    return {
        "local_id": case["id"],
        "title": case["title"],
        "priority": case["priority"],
        "preconditions": list(case.get("preconditions", [])),
        "steps": [
            {"action": step["action"], "expected_result": step.get("expected_result")}
            for step in case.get("steps", [])
        ],
        "tags": list(case.get("tags", [])),
        "trace_refs": {
            "requirements": list(case.get("requirement_refs", [])),
            "coverage_points": list(case.get("coverage_point_refs", [])),
        },
        "status": case["status"],
    }


RISK_SUITE_TAGS = (
    "negative", "operator-error", "adversarial", "resilience", "fault-injection",
    "recovery", "concurrency", "e2e", "cross-cutting", "security", "data-integrity",
)


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


def persist_integration_state(run_dir: Path, state: dict[str, Any]) -> Path:
    """Persist non-secret idempotency metadata under the private run directory."""
    path = run_dir / "integration-state" / "azure-devops.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path
