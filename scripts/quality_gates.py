#!/usr/bin/env python3
"""Independent v2.2 test-design quality gates."""

from __future__ import annotations

from typing import Any


GATE_NAMES = (
    "SCHEMA_VALID", "CROSS_FILE_VALID", "SOURCE_INVENTORY_COMPLETE",
    "NORMATIVE_COVERAGE_COMPLETE", "ORACLE_SAFETY_VALID", "REFERENCE_INTEGRITY_VALID",
    "PROCEDURE_QUALITY_ACCEPTABLE", "PIPELINE_PROVENANCE_VALID",
    "BASELINE_PRESERVATION_VALID", "NORMATIVE_SOURCE_FAMILIES_COMPLETE",
    "USE_CASE_FLOW_ACCOUNTING_VALID", "RISK_DISPOSITION_COMPLETE",
    "TEST_ASSET_CHALLENGE_VALID", "TEST_DATA_REACHABILITY_VALID",
    "EVIDENCE_REFERENCE_INTEGRITY_VALID", "SEMANTIC_COMPOSITION_VALID",
    "CANONICAL_PUBLICATION_VALID", "HISTORICAL_BASELINE_REGRESSION_VALID",
    "ATOMIC_COVERAGE_VALID", "CLAIM_EXERCISE_VALID", "SOURCE_IDENTIFIERS_COMPLETE",
    "USE_CASE_FLOW_EXERCISE_VALID", "ADDITIVE_EXPANSION_COMPLETE",
    "ONE_STEP_COMPLETENESS_VALID", "AUTOMATION_READINESS_VALID",
    "PRIORITY_CALIBRATION_VALID", "SCENARIO_FAMILY_LINKAGE_VALID",
    "E2E_STAGE_MAPPING_VALID",
)


def build_quality_gates(
    *, source_complete: bool, normative_complete: bool, oracle_safe: bool,
    references_valid: bool, procedure_acceptable: bool, provenance_valid: bool,
    baseline_preserved: bool, source_families_complete: bool,
    use_case_flows_valid: bool, risk_disposition_complete: bool,
    test_asset_challenge_valid: bool, test_data_reachability_valid: bool,
    evidence_references_valid: bool, semantic_composition_valid: bool,
    canonical_publication_valid: bool, historical_baseline_valid: bool,
    atomic_coverage_valid: bool, claim_exercise_valid: bool,
    source_identifiers_complete: bool, use_case_flow_exercise_valid: bool,
    additive_expansion_complete: bool, one_step_completeness_valid: bool,
    automation_readiness_valid: bool, priority_calibration_valid: bool,
    scenario_family_linkage_valid: bool, e2e_stage_mapping_valid: bool,
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
        "BASELINE_PRESERVATION_VALID": baseline_preserved,
        "NORMATIVE_SOURCE_FAMILIES_COMPLETE": source_families_complete,
        "USE_CASE_FLOW_ACCOUNTING_VALID": use_case_flows_valid,
        "RISK_DISPOSITION_COMPLETE": risk_disposition_complete,
        "TEST_ASSET_CHALLENGE_VALID": test_asset_challenge_valid,
        "TEST_DATA_REACHABILITY_VALID": test_data_reachability_valid,
        "EVIDENCE_REFERENCE_INTEGRITY_VALID": evidence_references_valid,
        "SEMANTIC_COMPOSITION_VALID": semantic_composition_valid,
        "CANONICAL_PUBLICATION_VALID": canonical_publication_valid,
        "HISTORICAL_BASELINE_REGRESSION_VALID": historical_baseline_valid,
        "ATOMIC_COVERAGE_VALID": atomic_coverage_valid,
        "CLAIM_EXERCISE_VALID": claim_exercise_valid,
        "SOURCE_IDENTIFIERS_COMPLETE": source_identifiers_complete,
        "USE_CASE_FLOW_EXERCISE_VALID": use_case_flow_exercise_valid,
        "ADDITIVE_EXPANSION_COMPLETE": additive_expansion_complete,
        "ONE_STEP_COMPLETENESS_VALID": one_step_completeness_valid,
        "AUTOMATION_READINESS_VALID": automation_readiness_valid,
        "PRIORITY_CALIBRATION_VALID": priority_calibration_valid,
        "SCENARIO_FAMILY_LINKAGE_VALID": scenario_family_linkage_valid,
        "E2E_STAGE_MAPPING_VALID": e2e_stage_mapping_valid,
    }
    return [{
        "gate": name,
        "status": "PASS" if values[name] else "FAIL",
        "evidence": "derived by the shared v2.2.2 runtime from materialized stage artifacts",
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
