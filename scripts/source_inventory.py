#!/usr/bin/env python3
"""Authority-aware source universe and completeness gates for schema 2.2."""

from __future__ import annotations

from typing import Any


AUTHORITIES = {
    "NORMATIVE_PRIMARY", "NORMATIVE_SECONDARY", "IMPLEMENTATION", "OPERATIONAL",
    "HISTORICAL", "SUPPORTING", "BENCHMARK_ONLY", "UNKNOWN",
}
NORMATIVE_AUTHORITIES = {"NORMATIVE_PRIMARY", "NORMATIVE_SECONDARY"}
SOURCE_FAMILIES = {
    "FUNCTIONAL_REQUIREMENT", "BUSINESS_RULE", "ACCEPTANCE_CRITERIA", "USE_CASE",
    "PRECONDITION", "POSTCONDITION", "ALTERNATIVE_FLOW", "EXCEPTION_FLOW", "NFR",
    "SECURITY", "PERFORMANCE", "INTEGRATION_CONTRACT", "ADR", "API_CONTRACT",
    "USER_MANUAL", "ARCHITECTURE", "IMPLEMENTATION", "CONFIGURATION", "DOMAIN_MODEL",
    "OPERATIONAL", "TEST_ASSET", "OTHER",
}


class SourceInventoryError(ValueError):
    pass


def audit_source_inventory(
    selected_sources: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    *,
    referenced_authoritative_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Account for the selected source universe before semantic extraction."""
    selected = {str(item.get("path", "")) for item in selected_sources}
    by_path: dict[str, dict[str, Any]] = {}
    for item in inventory:
        path = str(item.get("path", ""))
        if path not in selected:
            raise SourceInventoryError(f"Source inventory path {path} is outside selected scope")
        if path in by_path:
            raise SourceInventoryError(f"Source inventory path {path} is duplicated")
        authority = str(item.get("authority", ""))
        family = str(item.get("family", ""))
        disposition = str(item.get("disposition", ""))
        reason = str(item.get("reason", "")).strip()
        if authority not in AUTHORITIES:
            raise SourceInventoryError(f"Source {path} has unsupported authority {authority}")
        if family not in SOURCE_FAMILIES:
            raise SourceInventoryError(f"Source {path} has unsupported family {family}")
        if disposition not in {"INCLUDED", "EXCLUDED"}:
            raise SourceInventoryError(f"Source {path} requires INCLUDED or EXCLUDED disposition")
        if not reason:
            raise SourceInventoryError(f"Source {path} requires an inclusion/exclusion reason")
        if authority in NORMATIVE_AUTHORITIES and disposition == "EXCLUDED":
            raise SourceInventoryError(f"Authoritative source {path} cannot be silently excluded")
        by_path[path] = item
    missing = sorted(selected - set(by_path))
    if missing:
        raise SourceInventoryError("Selected sources absent from source inventory: " + ", ".join(missing))
    references = set(map(str, referenced_authoritative_paths or []))
    omitted = sorted(references - selected)
    if omitted:
        raise SourceInventoryError(
            "Referenced authoritative sources were not selected or dispositioned: " + ", ".join(omitted)
        )
    included = [item for item in inventory if item["disposition"] == "INCLUDED"]
    normative = [item for item in included if item["authority"] in NORMATIVE_AUTHORITIES]
    implementation = [item for item in included if item["authority"] == "IMPLEMENTATION"]
    return {
        "source_files_discovered": len(inventory),
        "source_items_total": len(included),
        "normative_items": len(normative),
        "implementation_items": len(implementation),
        "source_items_excluded": len(inventory) - len(included),
        "source_discovery_coverage": "COMPLETE",
        "authoritative_source_families": sorted({item["family"] for item in normative}),
        "inventory": inventory,
    }
