#!/usr/bin/env python3
"""Derive deterministic presentation groups from existing requirement metadata."""

from __future__ import annotations

import re
from typing import Any


RF_PATTERN = re.compile(r"(?<![A-Z0-9])RF[\s_-]*([0-9]+)(?![A-Z0-9])", re.IGNORECASE)
E2E_TAGS = {"e2e", "end-to-end", "cross-rf"}


def original_rf_identifier(requirement: dict[str, Any]) -> str | None:
    """Return the first source-grounded RF identifier without inventing one."""
    candidates = [
        ref.get("reference", "")
        for ref in requirement.get("source_refs", [])
        if isinstance(ref, dict)
    ]
    candidates.append(requirement.get("statement", ""))
    for candidate in candidates:
        match = RF_PATTERN.search(str(candidate))
        if match:
            return "RF" + match.group(1)
    return None


def requirement_group_map(requirements: list[dict[str, Any]]) -> dict[str, str]:
    return {
        requirement["id"]: original_rf_identifier(requirement) or requirement["id"]
        for requirement in requirements
    }


def case_group(
    case: dict[str, Any],
    groups_by_requirement: dict[str, str],
    requirement_order: dict[str, int] | None = None,
) -> tuple[str, list[str], tuple[int, str]]:
    """Return primary group, related groups, and a stable presentation sort key."""
    requirement_order = requirement_order or {}
    refs = sorted(
        case.get("requirement_refs", []),
        key=lambda value: (requirement_order.get(value, 10**9), value),
    )
    labels: list[str] = []
    for ref in refs:
        label = groups_by_requirement.get(ref, ref)
        if label not in labels:
            labels.append(label)
    tags = {str(tag).casefold() for tag in case.get("tags", [])}
    if len(labels) > 1 and tags & E2E_TAGS:
        primary = "Cross-RF / End-to-End"
        related = labels
    else:
        primary = labels[0] if labels else "Unmapped"
        related = labels[1:]
    first_order = min((requirement_order.get(ref, 10**9) for ref in refs), default=10**9)
    return primary, related, (first_order, case.get("id", ""))
