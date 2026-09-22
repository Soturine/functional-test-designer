#!/usr/bin/env python3
"""Authority-aware source universe and completeness gates for schema 2.2."""

from __future__ import annotations

from typing import Any
import re


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
NORMATIVE_UNIT_FAMILIES = {
    "FUNCTIONAL_REQUIREMENT", "BUSINESS_RULE", "ACCEPTANCE_CRITERIA", "USE_CASE",
    "MAIN_FLOW", "ALTERNATIVE_FLOW", "EXCEPTION_FLOW", "PRECONDITION",
    "POSTCONDITION", "NFR", "SECURITY", "PERFORMANCE", "STATE_TRANSITION",
    "INTEGRATION_CONTRACT", "ADR",
}
UNIT_DISPOSITIONS = {
    "EXTRACTED", "QUESTION", "FINDING", "OUT_OF_SCOPE", "NOT_TESTABLE",
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
    selected_roles = {
        str(item.get("path", "")): str(item.get("role", "")) for item in selected_sources
    }
    selected = set(selected_roles)
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
        if authority in NORMATIVE_AUTHORITIES and selected_roles[path] != "FUNCTIONAL_AUTHORITY":
            raise SourceInventoryError(
                f"Normative source {path} must be selected as FUNCTIONAL_AUTHORITY"
            )
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


def audit_normative_source_units(
    inventory: list[dict[str, Any]], source_units: list[dict[str, Any]],
    expectations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prove completeness below the file level for every included authority source."""
    normative_paths = {
        str(item["path"]): item
        for item in inventory
        if item.get("authority") in NORMATIVE_AUTHORITIES
        and item.get("disposition") == "INCLUDED"
    }
    by_id: dict[str, dict[str, Any]] = {}
    units_by_path: dict[str, list[dict[str, Any]]] = {path: [] for path in normative_paths}
    for unit in source_units:
        unit_id = str(unit.get("id", "")).strip()
        path = str(unit.get("path", "")).strip()
        family = str(unit.get("family", "")).strip()
        disposition = str(unit.get("disposition", "")).strip()
        if not unit_id or unit_id in by_id:
            raise SourceInventoryError("Every normative source unit requires a unique id")
        if path not in normative_paths:
            raise SourceInventoryError(f"Normative source unit {unit_id} is outside included authority sources")
        if family not in NORMATIVE_UNIT_FAMILIES:
            raise SourceInventoryError(f"Normative source unit {unit_id} has unsupported family {family}")
        if disposition not in UNIT_DISPOSITIONS:
            raise SourceInventoryError(f"Normative source unit {unit_id} requires an explicit disposition")
        if not unit.get("source_refs"):
            raise SourceInventoryError(f"Normative source unit {unit_id} requires source_refs")
        if any(str(ref.get("source", "")) != path for ref in unit["source_refs"]):
            raise SourceInventoryError(
                f"Normative source unit {unit_id} has evidence outside its declared path"
            )
        if disposition in {"OUT_OF_SCOPE", "NOT_TESTABLE"} and not str(unit.get("reason", "")).strip():
            raise SourceInventoryError(f"Normative source unit {unit_id} requires a reason")
        if disposition in {"OUT_OF_SCOPE", "NOT_TESTABLE"} and re.search(
            r"\b(?:implementation|code|endpoint|screen|ui)\b.*\b(?:missing|absent|not found|unavailable)\b",
            str(unit.get("reason", "")), re.IGNORECASE,
        ):
            raise SourceInventoryError(
                f"Normative source unit {unit_id} cannot disappear because implementation is unavailable"
            )
        by_id[unit_id] = unit
        units_by_path[path].append(unit)
    missing_paths = sorted(path for path, units in units_by_path.items() if not units)
    if missing_paths:
        raise SourceInventoryError(
            "Included authority sources have no normative-unit inventory: " + ", ".join(missing_paths)
        )
    if expectations is not None:
        expected_paths = [str(item.get("path", "")) for item in expectations]
        if len(expected_paths) != len(set(expected_paths)):
            raise SourceInventoryError("Structural unit expectations contain duplicate paths")
        by_expected_path = {str(item.get("path", "")): item for item in expectations}
        missing_expectations = sorted(set(normative_paths) - set(by_expected_path))
        if missing_expectations:
            raise SourceInventoryError(
                "Authority sources have no structural unit expectation: "
                + ", ".join(missing_expectations)
            )
        for path, item in by_expected_path.items():
            if path not in normative_paths:
                raise SourceInventoryError(f"Structural unit expectation {path} is outside authority scope")
            expected_ids = {str(value) for value in item.get("expected_unit_refs", [])}
            actual_ids = {str(unit["id"]) for unit in units_by_path[path]}
            if not expected_ids or expected_ids != actual_ids:
                raise SourceInventoryError(
                    f"Normative units for {path} differ from structural indexing: "
                    f"missing={sorted(expected_ids - actual_ids)}; unexpected={sorted(actual_ids - expected_ids)}"
                )
    counts = {family: 0 for family in sorted(NORMATIVE_UNIT_FAMILIES)}
    for unit in source_units:
        counts[str(unit["family"])] += 1
    return {
        "normative_units_total": len(source_units),
        "normative_sections_discovered": len(source_units),
        "business_rules_discovered": counts["BUSINESS_RULE"],
        "use_cases_discovered": counts["USE_CASE"],
        "main_flows_discovered": counts["MAIN_FLOW"],
        "alternative_flows_discovered": counts["ALTERNATIVE_FLOW"],
        "exception_flows_discovered": counts["EXCEPTION_FLOW"],
        "nfrs_discovered": counts["NFR"],
        "security_constraints_discovered": counts["SECURITY"],
        "performance_constraints_discovered": counts["PERFORMANCE"],
        "normative_source_families_complete": True,
        "normative_unit_family_counts": counts,
    }


def audit_use_case_flow_accounting(
    source_units: list[dict[str, Any]], flows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare each CU's declared structural flows with independently inventoried flow records."""
    use_cases = {str(item["id"]): item for item in source_units if item.get("family") == "USE_CASE"}
    expected: set[str] = set()
    for use_case_id, unit in use_cases.items():
        refs = {str(value) for value in unit.get("expected_flow_refs", [])}
        if not refs:
            raise SourceInventoryError(f"Use case {use_case_id} requires expected_flow_refs")
        overlap = expected & refs
        if overlap:
            raise SourceInventoryError("Use-case flow ids must have one parent: " + ", ".join(sorted(overlap)))
        expected.update(refs)
    actual: set[str] = set()
    for flow in flows:
        flow_id = str(flow.get("id", "")).strip()
        parent = str(flow.get("use_case_ref", ""))
        if not flow_id:
            raise SourceInventoryError("Every use-case flow requires an id")
        if parent not in use_cases:
            raise SourceInventoryError(f"Flow {flow_id or '<missing>'} requires a known use_case_ref")
        if flow_id in actual:
            raise SourceInventoryError(f"Use-case flow {flow_id} is duplicated")
        actual.add(flow_id)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        raise SourceInventoryError(
            "Use-case flow inventory differs from source structure: "
            f"missing={','.join(missing) or 'none'}; unexpected={','.join(unexpected) or 'none'}"
        )
    return {
        "use_cases_accounted": len(use_cases),
        "use_case_flows_expected": len(expected),
        "use_case_flows_extracted": len(actual),
        "unaccounted_use_case_flows": 0,
        "use_case_flow_accounting_valid": True,
    }
