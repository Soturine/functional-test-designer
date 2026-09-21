#!/usr/bin/env python3
"""Stable semantic fingerprints for public regression fixtures."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


RUNTIME_KEYS = {
    "generated_at",
    "run_id",
    "started_at",
    "finished_at",
    "elapsed_seconds",
    "wall_clock_seconds",
    "artifact_root",
    "output_path",
    "diagnostics_path",
}


def canonicalize(value: Any) -> Any:
    """Normalize semantic data while removing only declared runtime noise."""
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {
            key: canonicalize(item)
            for key, item in sorted(value.items())
            if key not in RUNTIME_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if isinstance(value, set):
        return sorted(canonicalize(item) for item in value)
    return value


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_snapshots(
    *,
    sources: list[dict[str, Any]],
    source_items: list[dict[str, Any]],
    inventory: dict[str, Any],
    chain: dict[str, Any],
    design: dict[str, Any],
    cases: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Separate frozen semantic identity from intentionally improvable procedure."""
    legacy_identity_fields = {
        "id", "title", "scenario_ref", "scenario_type", "requirement_refs",
        "coverage_point_refs", "normative_source_refs", "normative_oracle", "objective",
        "material_preconditions", "test_data_partition", "assertions", "execution_signature",
        "execution_boundary",
    }
    identities = []
    for identity in design["test_identities"]:
        if dataclasses.is_dataclass(identity):
            raw = dataclasses.asdict(identity)
            identities.append({key: raw[key] for key in raw if key in legacy_identity_fields})
        else:
            identities.append(identity)
    core = {
        "sources": sources,
        "source_items": source_items,
        "claims": inventory["claims"],
        "normative_clauses": chain["normative_clauses"],
        "coverage_points": chain["coverage_points"],
        "claim_destinations": chain["claim_destinations"],
        "candidates": design["candidates"],
        "merge_decisions": design["merge_decisions"],
        "scenarios": design["scenarios"],
        "test_identities": identities,
    }
    procedure = {
        "cases": cases,
        "questions": questions,
        "findings": findings,
        "hidden_subtests": any("subtests" in case for case in cases),
        "schema_versions": sorted({case.get("schema_version") for case in cases}),
    }
    return {
        "core": canonicalize(core),
        "procedure": canonicalize(procedure),
        "core_fingerprint": fingerprint(core),
        "procedure_fingerprint": fingerprint(procedure),
    }


def assert_projection_parity(
    canonical_cases: list[dict[str, Any]], projected_cases: list[dict[str, Any]]
) -> None:
    """Fail when a projection changes canonical Test Case semantics."""
    if canonicalize(canonical_cases) != canonicalize(projected_cases):
        raise ValueError("Public projection differs from canonical Test Case semantics")
