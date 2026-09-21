#!/usr/bin/env python3
"""Deterministic operational scenario catalog projected from canonical state.

This is a review catalog, not a second Test Case model. Every row points at
canonical Test Cases that already exist; nothing here creates, renames, or
re-scopes a Test Case, and no field is invented when the selected evidence does
not supply it.
"""

from __future__ import annotations

from typing import Any


CATALOG_FIELDS = (
    ("requirement_refs", "Requirement / CP refs"),
    ("actor", "Actor"),
    ("location", "Location / context"),
    ("tools", "Tools / device"),
    ("starting_state", "Starting state"),
    ("trigger", "Trigger / disturbance"),
    ("risk", "Risk exercised"),
    ("oracle_source", "Expected invariant source"),
    ("recovery", "Recovery / cleanup"),
    ("tags", "Classification"),
    ("readiness", "Readiness"),
    ("open_questions", "Open Questions"),
)
UNSUPPORTED = "Not supported by the selected evidence"


def _value(family: dict[str, Any], key: str) -> str:
    raw = family.get(key)
    if isinstance(raw, (list, tuple)):
        items = [str(item) for item in raw if str(item).strip()]
        return ", ".join(items) if items else UNSUPPORTED
    text = str(raw or "").strip()
    return text or UNSUPPORTED


def build_operational_catalog(
    families: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate that each catalog family points only at canonical Test Cases."""
    case_ids = {str(case["id"]) for case in cases}
    readiness_by_case = {str(case["id"]): str(case.get("status", "")) for case in cases}
    rows: list[dict[str, Any]] = []
    for family in families:
        family_id = str(family.get("id", "")).strip()
        if not family_id:
            raise ValueError("Every operational scenario family requires an id")
        links = [str(item) for item in family.get("test_case_refs", [])]
        unknown = sorted(set(links) - case_ids)
        if unknown:
            raise ValueError(
                f"Operational scenario family {family_id} links unknown Test Cases: "
                + ", ".join(unknown)
            )
        if not links:
            raise ValueError(f"Operational scenario family {family_id} links no Test Case")
        row = dict(family)
        row["id"] = family_id
        row["test_case_refs"] = links
        row.setdefault("readiness", sorted({readiness_by_case[item] for item in links}))
        rows.append(row)
    rows.sort(key=lambda item: item["id"])
    return {"families": rows, "family_count": len(rows)}


def render_operational_scenarios(catalog: dict[str, Any]) -> str:
    """Render the catalog markdown deterministically from canonical state alone."""
    families = catalog.get("families", [])
    lines = [
        "# Operational scenario catalog",
        "",
        (
            "Review projection of adversarial, resilience and end-to-end scenario families. "
            "Each family links canonical Test Cases; it never redefines them."
        ),
        "",
        f"Scenario families: {len(families)}",
        "",
    ]
    if not families:
        lines.append("No operational scenario family was supported by the selected evidence.")
        lines.append("")
        return "\n".join(lines)

    for family in families:
        lines.append(f"## {family['id']} — {_value(family, 'title')}")
        lines.append("")
        lines.append(f"- Test Cases: {', '.join(family['test_case_refs'])}")
        for key, label in CATALOG_FIELDS:
            lines.append(f"- {label}: {_value(family, key)}")
        lines.append("")
    return "\n".join(lines)
