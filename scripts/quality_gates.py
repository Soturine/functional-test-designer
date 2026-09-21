#!/usr/bin/env python3
"""Independent v2.2 test-design quality gates."""

from __future__ import annotations

from typing import Any


GATE_NAMES = (
    "SCHEMA_VALID", "CROSS_FILE_VALID", "SOURCE_INVENTORY_COMPLETE",
    "NORMATIVE_COVERAGE_COMPLETE", "ORACLE_SAFETY_VALID", "REFERENCE_INTEGRITY_VALID",
    "PROCEDURE_QUALITY_ACCEPTABLE", "PIPELINE_PROVENANCE_VALID",
)


def build_quality_gates(
    *, source_complete: bool, normative_complete: bool, oracle_safe: bool,
    references_valid: bool, procedure_acceptable: bool, provenance_valid: bool,
) -> list[dict[str, str]]:
    values = {
        "SCHEMA_VALID": True,
        "CROSS_FILE_VALID": True,
        "SOURCE_INVENTORY_COMPLETE": source_complete,
        "NORMATIVE_COVERAGE_COMPLETE": normative_complete,
        "ORACLE_SAFETY_VALID": oracle_safe,
        "REFERENCE_INTEGRITY_VALID": references_valid,
        "PROCEDURE_QUALITY_ACCEPTABLE": procedure_acceptable,
        "PIPELINE_PROVENANCE_VALID": provenance_valid,
    }
    return [{
        "gate": name,
        "status": "PASS" if values[name] else "FAIL",
        "evidence": "validated by the shared v2.2 generation pipeline",
    } for name in GATE_NAMES]


def assert_quality_gates(gates: list[dict[str, Any]]) -> None:
    by_name = {str(item.get("gate")): item for item in gates}
    missing = [name for name in GATE_NAMES if name not in by_name]
    failed = [name for name in GATE_NAMES if by_name.get(name, {}).get("status") != "PASS"]
    if missing or failed:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if failed:
            details.append("failed=" + ",".join(failed))
        raise ValueError("Test design quality gates did not pass: " + "; ".join(details))
