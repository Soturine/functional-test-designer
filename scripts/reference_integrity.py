#!/usr/bin/env python3
"""Physical and role-aware evidence-reference validation inside selected scope."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def _walk_refs(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "source" in value and "reference" in value:
            yield value
        for child in value.values():
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def audit_evidence_references(
    workspace: Path,
    selected_sources: list[dict[str, Any]],
    documents: list[Any],
) -> dict[str, Any]:
    """Reject stale, outside-scope, role-mismatched, or invalid line references."""
    root = workspace.resolve()
    roles = {str(item["path"]): str(item["role"]) for item in selected_sources}
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    line_counts: dict[str, int] = {}
    for document in documents:
        for ref in _walk_refs(document):
            checked += 1
            source = str(ref.get("source", ""))
            if source not in roles:
                errors.append(f"{source}:outside-selected-scope")
                continue
            path = (root / source).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                errors.append(f"{source}:outside-workspace")
                continue
            if not path.is_file():
                errors.append(f"{source}:missing-path")
                continue
            expected_role = str(ref.get("expected_role", ""))
            if expected_role and expected_role != roles[source]:
                errors.append(f"{source}:role-mismatch:{expected_role}!={roles[source]}")
            start = ref.get("line_start")
            end = ref.get("line_end", start)
            if start is not None:
                if source not in line_counts:
                    line_counts[source] = len(path.read_text(encoding="utf-8").splitlines())
                if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > line_counts[source]:
                    errors.append(f"{source}:invalid-line-range:{start}-{end}")
            if not str(ref.get("reference", "")).strip():
                warnings.append(f"{source}:empty-semantic-reference")
    if errors:
        raise ValueError("Evidence reference integrity failed: " + ", ".join(sorted(set(errors))))
    return {
        "evidence_references_checked": checked,
        "invalid_evidence_paths": 0,
        "syntactic_reference_errors": 0,
        "evidence_path_errors": 0,
        "semantic_reference_warnings": len(set(warnings)),
        "semantic_reference_errors": 0,
        "evidence_reference_integrity_valid": True,
    }
