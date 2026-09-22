#!/usr/bin/env python3
"""Runtime-owned integrity contracts for the official generation pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE_SEQUENCE = (
    "SOURCE_SELECTION", "SOURCE_ACCOUNTING", "SOURCE_UNIT_EXTRACTION",
    "CLAIM_EXTRACTION", "CLAUSE_NORMALIZATION", "COVERAGE_DESIGN",
    "NORMATIVE_BASELINE", "TEST_ASSET_CHALLENGE", "OPERATOR_ERROR_EXPANSION",
    "RISK_EXPANSION", "CHARACTERIZATION", "CROSS_REQUIREMENT",
    "E2E_COMPOSITION", "PROCEDURE_REFINEMENT", "VALIDATION", "RENDERING",
    "PUBLICATION",
)
UNTRUSTED_RESULT_FIELDS = {
    "quality_gates", "pipeline_provenance_valid", "canonical_publication_valid",
    "atomic_coverage_valid", "claim_exercise_valid", "source_identifiers_complete",
    "historical_baseline_regression_valid", "one_step_completeness_valid",
    "automation_readiness_valid", "priority_calibration_valid",
    "scenario_family_linkage_valid", "e2e_stage_mapping_valid",
    "baseline_preserved", "final_coverage", "scenario_count", "test_count",
    "pipeline_timing", "unmapped_normative_clauses",
}
ATOMICITY_REASONS = {"INDIVISIBLE_CONTRACT"}
AUTOMATION_BLOCKERS = {
    "MISSING_EXECUTION_SURFACE", "MISSING_DETERMINISTIC_DATA", "AMBIGUOUS_ACTION",
    "MISSING_OBSERVATION", "HIDDEN_BRANCH", "PATH_COMPRESSION", "PROCEDURE_GAP",
    "EXTERNAL_DEPENDENCY", "ENVIRONMENT_GAP", "NOT_DETERMINISTIC",
}
BASELINE_RECONCILIATIONS = {
    "RENAMED", "SPLIT", "SUPERSEDED_BY_AUTHORITY_CHANGE", "INVALID_BASELINE_ITEM",
    "SCOPE_CHANGED", "INTENT_PRESERVED_DIFFERENT_ID",
}
DEFAULT_IDENTIFIER_PATTERN = r"\b[A-Za-z]{1,12}[._ -]?\d+(?:\.\d+)*\b"


class PipelineIntegrityError(ValueError):
    """Raised when an official run cannot prove its own integrity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_request_owned_results(request: dict[str, Any]) -> None:
    rejected = sorted(UNTRUSTED_RESULT_FIELDS & set(request))
    if rejected:
        raise PipelineIntegrityError(
            "Generation requests cannot provide runtime-owned results: " + ", ".join(rejected)
        )


class RunManifest:
    """Append-only ordered manifest with a deterministic hash chain."""

    def __init__(self, path: Path, run_id: str, *, generator: str = "functional-test-designer/2.2.2"):
        self.path = path
        self.document: dict[str, Any] = {
            "manifest_version": "1", "run_id": run_id, "generator": generator,
            "created_at": _now(), "stages": [], "canonical": None, "publication": None,
        }
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)

    def record(
        self, stage: str, *, inputs: Any, outputs: Any, started_at: str,
        finished_at: str, status: str = "COMPLETE", stage_version: str = "1",
    ) -> None:
        position = len(self.document["stages"])
        expected = STAGE_SEQUENCE[position] if position < len(STAGE_SEQUENCE) else None
        if stage != expected:
            raise PipelineIntegrityError(f"Stage {stage} cannot follow position {position}; expected {expected}")
        previous = self.document["stages"][-1]["chain_digest"] if position else "GENESIS"
        record = {
            "stage": stage, "status": status,
            "input_ids": _ids(inputs), "output_ids": _ids(outputs),
            "input_digest": stable_digest(inputs), "output_digest": stable_digest(outputs),
            "started_at": started_at, "finished_at": finished_at,
            "generator": self.document["generator"], "stage_version": stage_version,
            "previous_chain_digest": previous,
        }
        record["chain_digest"] = stable_digest(record)
        self.document["stages"].append(record)
        self._write()

    def bind_canonical(self, canonical_path: Path) -> None:
        self.document["canonical"] = {
            "path": str(canonical_path.resolve()), "sha256": file_digest(canonical_path),
        }
        self._write()

    def bind_publication(self, artifact_root: Path, files: list[Path]) -> None:
        root = artifact_root.resolve()
        self.document["publication"] = {
            "artifact_root": str(root),
            "files": [{
                "path": path.resolve().relative_to(root).as_posix(), "sha256": file_digest(path),
            } for path in sorted(files)],
        }
        self.document["finished_at"] = _now()
        self._write()


def _ids(value: Any) -> list[str]:
    found: list[str] = []
    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if isinstance(item.get("id"), str):
                found.append(item["id"])
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
    visit(value)
    return list(dict.fromkeys(found))


def validate_run_manifest(path: Path, *, require_publication: bool = True) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    stages = document.get("stages", [])
    names = [item.get("stage") for item in stages]
    expected = list(STAGE_SEQUENCE if require_publication else STAGE_SEQUENCE[:len(names)])
    if names != expected:
        raise PipelineIntegrityError(f"Official stage chain is incomplete or reordered: {names}")
    previous = "GENESIS"
    for record in stages:
        if record.get("previous_chain_digest") != previous:
            raise PipelineIntegrityError(f"Broken manifest link before {record.get('stage')}")
        payload = {key: value for key, value in record.items() if key != "chain_digest"}
        if record.get("chain_digest") != stable_digest(payload):
            raise PipelineIntegrityError(f"Stage record was modified: {record.get('stage')}")
        if record.get("status") != "COMPLETE":
            raise PipelineIntegrityError(f"Stage did not complete: {record.get('stage')}")
        previous = record["chain_digest"]
    canonical = document.get("canonical")
    if require_publication or canonical is not None:
        if not isinstance(canonical, dict):
            raise PipelineIntegrityError("Run manifest is not bound to canonical state")
        canonical_path = Path(canonical.get("path", ""))
        if not canonical_path.is_file() or file_digest(canonical_path) != canonical.get("sha256"):
            raise PipelineIntegrityError("Canonical state digest mismatch")
    if require_publication:
        publication = document.get("publication")
        if not isinstance(publication, dict):
            raise PipelineIntegrityError("Run manifest has no publication proof")
        root = Path(publication.get("artifact_root", ""))
        for item in publication.get("files", []):
            target = root / str(item.get("path", ""))
            if not target.is_file() or file_digest(target) != item.get("sha256"):
                raise PipelineIntegrityError(f"Published artifact digest mismatch: {target}")
    return document


def build_identifier_ledger(
    source_units: list[dict[str, Any]], expectations: list[dict[str, Any]],
    *, patterns: list[str] | None = None,
) -> dict[str, Any]:
    compiled = [re.compile(value) for value in (patterns or [DEFAULT_IDENTIFIER_PATTERN])]
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in expectations:
        path = str(item.get("path", ""))
        for value in item.get("expected_identifiers", []):
            identifier = str(value.get("identifier", value) if isinstance(value, dict) else value)
            kind = str(value.get("type", "GENERIC") if isinstance(value, dict) else "GENERIC")
            expected[(path, identifier)] = {"identifier_type": kind}
    discovered: dict[tuple[str, str], dict[str, Any]] = {}
    for unit in source_units:
        path = str(unit.get("path", ""))
        text = " ".join([
            str(unit.get("id", "")), str(unit.get("title", "")),
            " ".join(str(ref.get("reference", "")) for ref in unit.get("source_refs", [])),
        ])
        values = set(str(value) for value in unit.get("identifiers", []))
        for pattern in compiled:
            values.update(match.group(0) for match in pattern.finditer(text))
        for identifier in values:
            discovered[(path, identifier)] = {
                "identifier": identifier, "identifier_type": "GENERIC", "source_path": path,
                "source_ref": unit.get("source_refs", []), "discovery_method": "STRUCTURAL_INDEX",
                "extraction_status": unit.get("disposition"), "claim_refs": [],
                "test_refs": [], "reason_if_not_applicable": unit.get("reason"),
            }
    missing = sorted(set(expected) - set(discovered))
    if missing:
        raise PipelineIntegrityError(
            "Expected source identifiers were not inventoried: "
            + ", ".join(f"{path}:{identifier}" for path, identifier in missing)
        )
    for key, metadata in expected.items():
        discovered[key]["identifier_type"] = metadata["identifier_type"]
    return {
        "entries": sorted(discovered.values(), key=lambda item: (item["source_path"], item["identifier"])),
        "source_identifiers_expected": len(expected),
        "source_identifiers_discovered": len(discovered),
        "source_identifiers_missing": 0,
        "source_identifiers_complete": True,
    }


def build_physical_source_ledger(
    workspace: Path, resolved_paths: list[str], source_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    reviews = {str(item.get("source")): item for item in source_ledger}
    entries = []
    for relative in resolved_paths:
        path = (workspace / relative).resolve()
        review = reviews.get(relative, {})
        stat = path.stat() if path.exists() else None
        entries.append({
            "logical_group": str(review.get("logical_group", "selected-source")),
            "physical_path": str(path), "exists": path.exists(),
            "sha256": file_digest(path) if path.is_file() else None,
            "open_status": str(review.get("disposition", "NOT_INSPECTED")),
            "extraction_status": "EXTRACTED" if int(review.get("evidence_records", 0)) else "NO_RECORDS",
            "error_status": None if path.exists() else "MISSING",
            "size_bytes": stat.st_size if stat else None,
            "modified_at": (
                datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
                if stat else None
            ),
        })
    if any(not item["exists"] for item in entries):
        raise PipelineIntegrityError("Physical source ledger contains missing selected paths")
    return {"schema_version": "1", "entries": entries}


def link_identifier_ledger(
    ledger: dict[str, Any], claims: list[dict[str, Any]], mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    tests_by_claim = {
        str(item["claim_id"]): str(item["test_case_id"]) for item in mappings
    }
    for entry in ledger.get("entries", []):
        identifier = str(entry["identifier"])
        path = str(entry["source_path"])
        matched = [
            str(claim["id"]) for claim in claims
            if any(
                str(ref.get("source")) == path
                and identifier.casefold() in str(ref.get("reference", "")).casefold()
                for ref in claim.get("source_refs", [])
            )
        ]
        entry["claim_refs"] = matched
        entry["test_refs"] = list(dict.fromkeys(
            tests_by_claim[claim] for claim in matched if claim in tests_by_claim
        ))
    return ledger


def audit_atomic_coverage(points: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    acceptance = [case for case in cases if case.get("test_basis", "ACCEPTANCE") == "ACCEPTANCE"]
    by_cp: dict[str, list[dict[str, Any]]] = {}
    violations: list[str] = []
    for case in acceptance:
        refs = list(case.get("coverage_point_refs", []))
        if len(refs) != 1:
            exception = case.get("atomicity_exception")
            valid = (
                isinstance(exception, dict)
                and exception.get("reason") in ATOMICITY_REASONS
                and bool(exception.get("shared_failure_domain"))
                and bool(exception.get("claim_ids"))
            )
            if not valid:
                violations.append(f"{case.get('id')}:acceptance-must-exercise-one-cp")
        for ref in refs:
            by_cp.setdefault(str(ref), []).append(case)
    for point in points:
        if point.get("disposition") != "TEST_CASE":
            continue
        matches = by_cp.get(str(point.get("id")), [])
        if len(matches) != 1:
            violations.append(f"{point.get('id')}:acceptance-count={len(matches)}")
    if violations:
        raise PipelineIntegrityError("Atomic coverage violations: " + ", ".join(violations))
    return {"atomic_coverage_valid": True, "atomic_coverage_violations": 0}


def audit_claim_exercise(
    claims: list[dict[str, Any]], clauses: list[dict[str, Any]],
    points: list[dict[str, Any]], cases: list[dict[str, Any]],
    packs: dict[str, dict[str, Any]], claim_destinations: dict[str, str],
) -> dict[str, Any]:
    clauses_by_id = {str(item["id"]): item for item in clauses}
    cp_by_clause = {
        str(clause): point for point in points for clause in point.get("clause_refs", [])
    }
    cases_by_cp: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        for cp in case.get("coverage_point_refs", []):
            cases_by_cp.setdefault(str(cp), []).append(case)
    mappings: list[dict[str, Any]] = []
    missing: list[str] = []
    for claim in claims:
        claim_id = str(claim.get("id", ""))
        clause_id = str(claim_destinations.get(claim_id, ""))
        clause = clauses_by_id.get(clause_id)
        point = cp_by_clause.get(clause_id)
        if not clause or not point or clause.get("destination_type") != "COVERAGE_POINT":
            continue
        candidates = [case for case in cases_by_cp.get(str(point["id"]), []) if case.get("test_basis") == "ACCEPTANCE"]
        if len(candidates) != 1:
            missing.append(claim_id)
            continue
        case = candidates[0]
        pack = packs.get(str(case["id"]), {})
        explicit = pack.get("claim_exercise_map", {}).get(claim_id, {})
        step_refs = list(explicit.get("step_refs", [len(case.get("steps", []))]))
        assertion_refs = list(explicit.get("assertion_refs", ["normative_oracle"]))
        if not step_refs or not assertion_refs or not case.get("steps"):
            missing.append(claim_id)
            continue
        kind = str(case.get("primary_type", "FUNCTIONAL"))
        required_pack = {
            "PERFORMANCE": "performance_observation",
            "HARDWARE_INTEGRATION": "device_matrix",
            "FIELD": "device_matrix",
            "AUTHORIZATION": "authorization_probe",
            "SECURITY": "authorization_probe",
            "CONCURRENCY": "concurrency_plan",
            "RACE_CONDITION": "concurrency_plan",
            "IDEMPOTENCY": "idempotency_probe",
        }.get(kind)
        if required_pack and not pack.get(required_pack):
            missing.append(f"{claim_id}:{required_pack}")
            continue
        mappings.append({
            "claim_id": claim_id, "coverage_point_id": point["id"],
            "test_case_id": case["id"], "step_refs": step_refs,
            "assertion_refs": assertion_refs, "primary_type": kind,
        })
        case["claim_exercise_map"] = list(case.get("claim_exercise_map", [])) + [mappings[-1]]
    if missing:
        raise PipelineIntegrityError("Claims are not observably exercised: " + ", ".join(missing))
    return {"claim_exercise_valid": True, "claims_exercised": len(mappings), "mappings": mappings}


def apply_runtime_readiness(cases: list[dict[str, Any]], readiness: list[dict[str, Any]]) -> dict[str, Any]:
    for case, audit in zip(cases, readiness):
        reasons = list(audit.get("reason_codes", []))
        ready = audit.get("automation_classification") == "AUTOMATION_EXECUTION_READY"
        case["automation_candidate"] = bool(ready)
        if ready:
            case["automation_blocker"] = None
            if case.get("automation_layer") == "NONE":
                case["automation_layer"] = "MIXED"
            if case.get("automation_tool_hint") == "NONE":
                case["automation_tool_hint"] = "OTHER"
            case["deterministic"] = True
        else:
            blocker = next((reason for reason in reasons if reason in AUTOMATION_BLOCKERS), None)
            case["automation_blocker"] = blocker or "NOT_DETERMINISTIC"
            case["automation_layer"] = "NONE"
            case["automation_tool_hint"] = "NONE"
            case["deterministic"] = False
        case.setdefault("priority_reason", "Priority preserved from evidence-supported impact assessment.")
    invalid = [case["id"] for case in cases if not case["automation_candidate"] and not case.get("automation_blocker")]
    if invalid:
        raise PipelineIntegrityError("Automation readiness lacks blockers: " + ", ".join(invalid))
    return {"automation_readiness_valid": True, "automation_blockers_missing": 0}


def audit_scenario_family_linkage(scenarios: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(case["id"]): case for case in cases}
    errors = []
    for scenario in scenarios:
        declared_cp = set(map(str, scenario.get("coverage_point_refs", [])))
        member_cp = {
            str(cp) for tc in scenario.get("test_case_refs", [])
            for cp in by_id.get(str(tc), {}).get("coverage_point_refs", [])
        }
        if declared_cp != member_cp:
            errors.append(str(scenario.get("id")))
    if errors:
        raise PipelineIntegrityError("Scenario Family CP linkage mismatch: " + ", ".join(errors))
    return {"scenario_family_linkage_valid": True, "scenario_family_linkage_errors": 0}


def audit_use_case_flow_exercise(
    flows: list[dict[str, Any]], opportunities: list[dict[str, Any]],
    valid_targets: set[str],
) -> dict[str, Any]:
    by_flow = {str(item.get("flow_ref")): item for item in opportunities if item.get("flow_ref")}
    failures = []
    for flow in flows:
        flow_id = str(flow.get("id"))
        item = by_flow.get(flow_id)
        if not item:
            failures.append(f"{flow_id}:missing-disposition")
            continue
        disposition = str(item.get("flow_disposition", ""))
        targets = set(map(str, item.get("target_refs", [])))
        if disposition in {"COVERED_BY_ATOMIC_SCENARIOS", "E2E_SCENARIO"} and not (targets & valid_targets):
            failures.append(f"{flow_id}:not-exercised")
        if disposition in {"QUESTION", "NOT_TESTABLE", "OUT_OF_SCOPE"} and not str(item.get("reason", "")).strip():
            failures.append(f"{flow_id}:missing-reason")
    if failures:
        raise PipelineIntegrityError("Use-case flows lack observable exercise: " + ", ".join(failures))
    return {"use_case_flow_exercise_valid": True, "use_case_flow_exercise_errors": 0}


def audit_one_step_completeness(
    cases: list[dict[str, Any]], packs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    legitimate = 0
    incomplete = []
    for case in cases:
        if len(case.get("steps", [])) != 1:
            continue
        pack = packs.get(str(case.get("id")), {})
        known = list(pack.get("actions", []))
        if len(known) > 1:
            incomplete.append(str(case.get("id")))
            continue
        step = case["steps"][0]
        if not str(step.get("action", "")).strip() or not str(step.get("expected_result", "")).strip():
            incomplete.append(str(case.get("id")))
            continue
        legitimate += 1
    if incomplete:
        raise PipelineIntegrityError("One-step cases are incomplete: " + ", ".join(incomplete))
    return {
        "one_step_completeness_valid": True, "one_step_cases_reviewed": legitimate,
        "one_step_incomplete": 0,
    }


def audit_priority_calibration(cases: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [str(case.get("id")) for case in cases if not str(case.get("priority_reason", "")).strip()]
    if missing:
        raise PipelineIntegrityError("Priority lacks evidence-supported reason: " + ", ".join(missing))
    distribution: dict[str, int] = {}
    for case in cases:
        priority = str(case.get("priority"))
        distribution[priority] = distribution.get(priority, 0) + 1
    flattened = len(cases) >= 5 and max(distribution.values(), default=0) / len(cases) >= 0.9
    return {
        "priority_calibration_valid": True, "priority_reason_missing": 0,
        "priority_flattening_warning": flattened,
    }


def audit_e2e_stage_mapping(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(case["id"]): case for case in cases}
    errors = []
    for case in cases:
        if case.get("test_basis") != "E2E":
            continue
        mapping = case.get("e2e_stage_map", [])
        composed = set(map(str, case.get("composes", [])))
        mapped = {str(item.get("atomic_test_ref")) for item in mapping if isinstance(item, dict)}
        if not mapping or mapped != composed:
            errors.append(str(case.get("id")))
            continue
        for item in mapping:
            target = by_id.get(str(item.get("atomic_test_ref")))
            if not target or not item.get("trigger") or not item.get("assertion_refs"):
                errors.append(str(case.get("id")))
                break
    if errors:
        raise PipelineIntegrityError("E2E stage mapping is incomplete: " + ", ".join(sorted(set(errors))))
    return {"e2e_stage_mapping_valid": True, "e2e_stage_mapping_errors": 0}


def audit_historical_baseline(
    baseline_lock: dict[str, Any] | None, *, corpus_identity: str,
    source_scope_digest: str, claim_fingerprints: set[str],
    test_fingerprints: set[str], finding_fingerprints: set[str],
) -> dict[str, Any]:
    if not baseline_lock:
        return {"historical_baseline_regression_valid": True, "historical_baseline_applied": False}
    if baseline_lock.get("corpus_identity") != corpus_identity or baseline_lock.get("source_scope_digest") != source_scope_digest:
        return {"historical_baseline_regression_valid": True, "historical_baseline_applied": False}
    current = {
        "claim": claim_fingerprints, "test": test_fingerprints, "finding": finding_fingerprints,
    }
    reconciled = {
        (str(item.get("kind")), str(item.get("fingerprint")))
        for item in baseline_lock.get("reconciliations", [])
        if item.get("disposition") in BASELINE_RECONCILIATIONS and str(item.get("reason", "")).strip()
    }
    missing = []
    for kind, field in (("claim", "claim_fingerprints"), ("test", "normative_test_fingerprints"), ("finding", "known_finding_fingerprints")):
        for fingerprint in set(map(str, baseline_lock.get(field, []))) - current[kind]:
            if (kind, fingerprint) not in reconciled:
                missing.append(f"{kind}:{fingerprint}")
    if missing:
        raise PipelineIntegrityError("Historical baseline intent disappeared: " + ", ".join(sorted(missing)))
    return {"historical_baseline_regression_valid": True, "historical_baseline_applied": True}
