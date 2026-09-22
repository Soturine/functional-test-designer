#!/usr/bin/env python3
"""The official Functional Test Designer pipeline.

    selected sources -> SOURCE_SELECTION -> SEMANTIC_EXTRACTION        (runtime)
                     -> TEST_DESIGN -> EXPANSION -> PROCEDURES          (model stages)
                     -> VALIDATION -> RENDER -> PUBLICATION             (runtime)

The runtime owns scope, source reading, identifier indexing, ids, validation,
canonical state and publication. The model owns the QA reasoning: it receives a work
order after every stage and submits the next stage's output. A stage output is
validated against runtime-owned facts before it is recorded; it is never a trusted
precondition.

Integrity: every recorded stage appends a hash-chained manifest entry that also binds
the digests of the stage's stored payload and result. Canonical state is built only
from those recorded results, and public files are rendered only from canonical state.
Editing any stored stage file, skipping a stage or writing final outputs directly is
detected by `verify_manifest`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (  # noqa: E402
    GENERATOR, StageError, file_digest, normalize_identifier, now, read_json, stable_digest,
    write_json,
)
import design as design_stage  # noqa: E402
import expansion as expansion_stage  # noqa: E402
import procedures as procedure_stage  # noqa: E402
import sources  # noqa: E402
import validation  # noqa: E402


SKILL_ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "SOURCE_SELECTION", "SEMANTIC_EXTRACTION", "TEST_DESIGN", "EXPANSION", "PROCEDURES",
    "VALIDATION", "RENDER", "PUBLICATION",
)
MODEL_STAGES = {"design": "TEST_DESIGN", "expansion": "EXPANSION", "procedures": "PROCEDURES"}
PUBLIC_FORMATS = {"HTML", "JSON", "MARKDOWN", "DIAGNOSTICS", "OPERATIONAL"}
DEFAULT_FORMATS = ("HTML", "JSON", "MARKDOWN")


class IntegrityError(ValueError):
    """The run cannot prove that the official pipeline produced its state."""


# --- run files ------------------------------------------------------------------------

def run_directory(artifact_root: Path, run_id: str) -> Path:
    if not run_id or any(part in run_id for part in ("/", "\\", "..")):
        raise ValueError("run_id must be a safe local identifier")
    return Path(artifact_root).resolve() / ".ftd" / "runs" / run_id


def _manifest(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / "run-manifest.json")


def _state(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / "run-state.json")


def _save_state(run_dir: Path, **changes: Any) -> dict[str, Any]:
    path = run_dir / "run-state.json"
    state = read_json(path) if path.is_file() else {}
    state.update(changes)
    state["updated_at"] = now()
    write_json(path, state)
    return state


def _record(run_dir: Path, stage: str, *, started_at: str, inputs: Any, outputs: Any,
            files: list[Path] | None = None) -> None:
    """Append one hash-chained stage record; stages can only be recorded in order."""
    path = run_dir / "run-manifest.json"
    manifest = read_json(path) if path.is_file() else {
        "manifest_version": "2", "generator": GENERATOR, "stages": [],
        "canonical": None, "publication": None,
    }
    position = len(manifest["stages"])
    expected = STAGES[position] if position < len(STAGES) else None
    if stage != expected:
        raise IntegrityError(f"stage {stage} cannot be recorded at position {position}; expected {expected}")
    previous = manifest["stages"][-1]["chain_digest"] if position else "GENESIS"
    record = {
        "stage": stage, "order": position + 1, "started_at": started_at, "finished_at": now(),
        "input_digest": stable_digest(inputs), "output_digest": stable_digest(outputs),
        "files": {item.name: file_digest(item) for item in files or []},
        "generator": GENERATOR, "previous_chain_digest": previous,
    }
    record["chain_digest"] = stable_digest(record)
    manifest["stages"].append(record)
    write_json(path, manifest)


def verify_manifest(path: Path, *, require_publication: bool = True) -> dict[str, Any]:
    """Prove stage order, chain integrity, stored stage files, canonical and publication."""
    path = Path(path)
    if path.is_dir():
        path = path / "run-manifest.json"
    manifest = read_json(path)
    run_dir = path.parent
    stages = manifest.get("stages", [])
    names = [item.get("stage") for item in stages]
    expected = list(STAGES if require_publication else STAGES[: len(names)])
    if names != expected:
        raise IntegrityError(f"official stage chain is incomplete or reordered: {names}")
    previous = "GENESIS"
    for record in stages:
        if record.get("previous_chain_digest") != previous:
            raise IntegrityError(f"broken manifest link before {record.get('stage')}")
        payload = {key: value for key, value in record.items() if key != "chain_digest"}
        if record.get("chain_digest") != stable_digest(payload):
            raise IntegrityError(f"stage record was modified: {record.get('stage')}")
        for name, digest in record.get("files", {}).items():
            stored = run_dir / "stages" / name
            if not stored.is_file() or file_digest(stored) != digest:
                raise IntegrityError(f"stored stage file {name} does not match the manifest")
        previous = record["chain_digest"]
    canonical = manifest.get("canonical")
    if require_publication or canonical is not None:
        if not isinstance(canonical, dict):
            raise IntegrityError("run manifest is not bound to canonical state")
        target = run_dir / canonical.get("file", "")
        if not target.is_file() or file_digest(target) != canonical.get("sha256"):
            raise IntegrityError("canonical state digest mismatch")
    if require_publication:
        publication = manifest.get("publication")
        if not isinstance(publication, dict) or not publication.get("files"):
            raise IntegrityError("run manifest has no publication proof")
        root = Path(publication["artifact_root"])
        for item in publication["files"]:
            target = root / item["path"]
            if not target.is_file() or file_digest(target) != item["sha256"]:
                raise IntegrityError(f"published artifact digest mismatch: {item['path']}")
    return manifest


def _check_sources_unchanged(run: dict[str, Any], records: list[dict[str, Any]]) -> None:
    workspace = Path(run["workspace"])
    for record in records:
        path = workspace / record["path"]
        if not path.is_file() or file_digest(path) != record["content_digest"]:
            raise IntegrityError(f"selected source changed after the run started: {record['path']}")


def _load(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "run.json").is_file():
        raise IntegrityError(f"{run_dir} is not a pipeline run directory")
    return read_json(run_dir / "run.json"), read_json(run_dir / "sources.json")


def _result(run_dir: Path, stage: str) -> dict[str, Any]:
    return read_json(run_dir / "stages" / f"{stage}.result.json")


# --- start: scope lock and semantic extraction ---------------------------------------

def start_run(
    *, workspace: Path, sources_selected: list[dict[str, Any]], artifact_root: Path, run_id: str,
    locale: str | None = None, request_text: str = "", transcriptions: dict[str, Any] | None = None,
    id_pattern: str | None = None, allow_source_root: bool = False,
) -> dict[str, Any]:
    """Lock scope, read sources, index authority and issue the design work order."""
    began = now()
    workspace = Path(workspace).resolve()
    root = sources.resolve_artifact_root(
        skill_root=SKILL_ROOT, source_root=workspace, artifact_root=Path(artifact_root),
        allow_source_root=allow_source_root,
    )
    run_dir = run_directory(root, run_id)
    selection = sources.assign_roles(workspace, sources_selected)
    transcripts = {str(key): Path(value) for key, value in (transcriptions or {}).items()}
    records, texts = sources.build_source_records(workspace, selection["roles"], transcripts)
    events = []
    if (run_dir / "run.json").is_file():
        previous = read_json(run_dir / "sources.json")
        same = [(r["path"], r["content_digest"]) for r in previous["records"]] == [
            (r["path"], r["content_digest"]) for r in records
        ]
        if same:
            state = _state(run_dir)
            return {"run_dir": str(run_dir), "resumed": True, "state": state,
                    "work_order": str(run_dir / "work-order.json")}
        shutil.rmtree(run_dir)
        events.append({"event": "invalidated", "reason": "SOURCE_HASH_CHANGED"})
    run_dir.mkdir(parents=True, exist_ok=True)
    authority_texts = [texts[r["path"]] for r in records if r["role"] == "FUNCTIONAL_AUTHORITY"]
    locale_info = sources.infer_locale(locale, authority_texts, request_text)
    authority_index = sources.index_authority(records, texts, id_pattern)
    test_assets = sources.discover_all_test_assets(records, texts)
    text_dir = run_dir / "authority-text"
    for record in records:
        if record["role"] == "FUNCTIONAL_AUTHORITY":
            name = re.sub(r"[^A-Za-z0-9_.-]+", "_", record["path"]) + ".txt"
            (text_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (text_dir / name).write_text(texts[record["path"]], encoding="utf-8")
    run = {
        "run_id": run_id, "generator": GENERATOR, "workspace": str(workspace),
        "artifact_root": str(root), "created_at": began, "request_text": request_text,
        "id_pattern": id_pattern, **locale_info,
    }
    write_json(run_dir / "run.json", run)
    write_json(run_dir / "sources.json", {
        "scope": {key: selection[key] for key in ("selected_scope_roots", "resolved_scope_paths")},
        "records": records, "authority_index": authority_index, "test_assets": test_assets,
    })
    _record(run_dir, "SOURCE_SELECTION", started_at=began, inputs=sources_selected,
            outputs={"scope": selection["resolved_scope_paths"], "records": records},
            files=[])
    _record(run_dir, "SEMANTIC_EXTRACTION", started_at=began, inputs=[r["content_digest"] for r in records],
            outputs={"authority_index": authority_index, "test_assets": test_assets, **locale_info})
    _save_state(run_dir, status="IN_PROGRESS", next_stage="design", events=events,
                rejections={}, stage_seconds={}, stage_started_at=now())
    order = _work_order(run_dir)
    return {"run_dir": str(run_dir), "resumed": False, "work_order": str(order), **locale_info,
            "authority_identifiers": len(authority_index), "test_assets": len(test_assets)}


# --- model stages ------------------------------------------------------------------------

def _taken_keys(design: dict[str, Any]) -> set[str]:
    keys = {item["key"] for item in design["requirements"]}
    keys |= {item["key"] for item in design["claims"]} | {item["key"] for item in design["tests"]}
    keys |= {item["key"] for item in design["questions"]} | {item["key"] for item in design["findings"]}
    return keys


def _all_tests(run_dir: Path) -> list[dict[str, Any]]:
    tests = list(_result(run_dir, "design")["tests"])
    if (run_dir / "stages" / "expansion.result.json").is_file():
        tests += _result(run_dir, "expansion")["tests"]
    return tests


def submit_stage(run_dir: Path, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one model stage against runtime-owned facts and record it."""
    run_dir = Path(run_dir).resolve()
    run, source_state = _load(run_dir)
    state = _state(run_dir)
    if stage not in MODEL_STAGES:
        raise ValueError(f"unknown model stage {stage!r}; expected one of {list(MODEL_STAGES)}")
    if state.get("status") != "IN_PROGRESS" or state.get("next_stage") != stage:
        raise IntegrityError(f"stage {stage} is not the next stage (next: {state.get('next_stage')})")
    if not isinstance(payload, dict):
        raise ValueError("stage payload must be a JSON object")
    verify_manifest(run_dir / "run-manifest.json", require_publication=False)
    _check_sources_unchanged(run, source_state["records"])
    records = source_state["records"]
    workspace = Path(run["workspace"])
    texts = {}
    for record in records:
        if record["role"] == "FUNCTIONAL_AUTHORITY":
            name = re.sub(r"[^A-Za-z0-9_.-]+", "_", record["path"]) + ".txt"
            texts[record["path"]] = (run_dir / "authority-text" / name).read_text(encoding="utf-8")
    base = {"locale": run["output_locale"], "source_records": records,
            "authority_index": source_state["authority_index"], "authority_texts": list(texts.values())}
    try:
        if stage == "design":
            result = design_stage.validate_design(payload, base)
            for number, test in enumerate(result["tests"], 1):
                test["id"] = f"TC-{number:03d}"
        elif stage == "expansion":
            design = _result(run_dir, "design")
            result = expansion_stage.validate_expansion(payload, {
                **base, "design": design, "taken_keys": _taken_keys(design),
                "test_assets": source_state["test_assets"],
            })
            offset = len(design["tests"])
            for number, test in enumerate(result["tests"], offset + 1):
                test["id"] = f"TC-{number:03d}"
        else:
            design, expanded = _result(run_dir, "design"), _result(run_dir, "expansion")
            tests = [*design["tests"], *expanded["tests"]]
            questions = [*design["questions"], *expanded["questions"]]
            result = procedure_stage.validate_procedures(payload, {
                **base, "tests": tests, "question_keys": [q["key"] for q in questions],
                "blocking_by_test": _blocking_by_test(tests, questions),
                "blocking_questions": {q["key"] for q in questions if q["blocking"]},
            })
        ref_errors, checked = sources.check_source_refs(workspace, records, texts, [payload])
        if ref_errors:
            raise StageError(stage, ref_errors)
    except StageError:
        rejections = state.get("rejections", {})
        rejections[stage] = rejections.get(stage, 0) + 1
        _save_state(run_dir, rejections=rejections)
        raise
    result["evidence_references_checked"] = checked
    stages_dir = run_dir / "stages"
    payload_path, result_path = stages_dir / f"{stage}.payload.json", stages_dir / f"{stage}.result.json"
    write_json(payload_path, payload)
    write_json(result_path, result)
    started = state.get("stage_started_at") or now()
    _record(run_dir, MODEL_STAGES[stage], started_at=started, inputs=payload, outputs=result,
            files=[payload_path, result_path])
    following = {"design": "expansion", "expansion": "procedures", "procedures": "finalize"}[stage]
    seconds = state.get("stage_seconds", {})
    seconds[stage] = round(time.time() - _epoch(started), 3)
    _save_state(run_dir, next_stage=following, stage_seconds=seconds, stage_started_at=now())
    order = _work_order(run_dir)
    return {"stage": stage, "recorded": True, "next_stage": following, "work_order": str(order),
            "warnings": result.get("warnings", [])}


def _epoch(stamp: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def _blocking_by_test(tests: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, bool]:
    blocking = {q["key"] for q in questions if q["blocking"]}
    by_key = {t["key"]: t["id"] for t in tests}
    result: dict[str, bool] = {}
    for test in tests:
        if blocking & set(test.get("question_keys", [])):
            result[test["id"]] = True
    for question in questions:
        if question["blocking"]:
            for ref in question["tests"]:
                result[by_key.get(ref, ref)] = True
    return result


# --- finalize: canonical state, validation, publication ---------------------------------

def _clean_refs(refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    for ref in refs:
        item = {"source": str(ref["source"]), "reference": str(ref["reference"])}
        if item not in unique:
            unique.append(item)
    return unique


def build_canonical(run_dir: Path, baseline_comparison: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the public suite exclusively from recorded stage results."""
    run, source_state = _load(run_dir)
    design, expanded = _result(run_dir, "design"), _result(run_dir, "expansion")
    procedures = _result(run_dir, "procedures")["procedures"]
    tests = [*design["tests"], *expanded["tests"]]
    problems = design_stage.baseline_preserved(design["baseline"], tests)
    if problems:
        raise IntegrityError("normative baseline changed: " + "; ".join(problems))
    by_key = {test["key"]: test for test in tests}
    requirements = design["requirements"]
    req_by_key = {item["key"]: item for item in requirements}
    questions_raw = [*design["questions"], *expanded["questions"]]
    findings_raw = [*design["findings"], *expanded["findings"]]
    question_id = {q["key"]: f"Q-{n:03d}" for n, q in enumerate(questions_raw, 1)}
    finding_id = {f["key"]: f"FND-{n:03d}" for n, f in enumerate(findings_raw, 1)}

    # Claims -> clauses -> coverage points; every claim keeps one explicit destination.
    clauses, points, cp_of_claim = [], [], {}
    for claim in design["claims"]:
        clause_id = claim["id"].replace("CLAIM", "CLAUSE")
        clause = {
            "id": clause_id, "requirement_ref": claim["requirement_ref"], "normalized_claim": claim["text"],
            "authority": "FUNCTIONAL_AUTHORITY", "source_refs": _clean_refs(claim["source_refs"]),
        }
        cp_id = f"CP-{len(points) + 1:03d}"
        point = {
            "id": cp_id, "requirement_ref": claim["requirement_ref"], "statement": claim["text"],
            "clause_refs": [clause_id], "source_refs": clause["source_refs"],
        }
        if claim["destination"] == "TEST":
            clause.update(destination_type="COVERAGE_POINT", destination_id=cp_id)
            point.update(disposition="TEST_CASE", target_refs=[])
            cp_of_claim[claim["id"]] = cp_id
        elif claim["destination"] == "QUESTION":
            clause.update(destination_type="QUESTION", destination_id=question_id[claim["question"]])
            point.update(disposition="QUESTION", target_refs=[question_id[claim["question"]]])
        elif claim["destination"] == "NOT_TESTABLE":
            clause.update(destination_type="NOT_TESTABLE", destination_id=None, reason=claim["reason"])
            point.update(disposition="OUT_OF_SCOPE", target_refs=[], reason=claim["reason"])
        else:
            clause.update(destination_type="FINDING", destination_id=finding_id[claim["finding"]])
            point = None
        clauses.append(clause)
        if point:
            points.append(point)
    points_by_id = {point["id"]: point for point in points}
    for test in tests:
        if test["basis"] == "E2E":
            test["composes"] = [by_key[key]["id"] for key in test.get("composes_keys", [])]
        test["cp_refs"] = list(dict.fromkeys(cp_of_claim[c] for c in test["claims"] if c in cp_of_claim))
        for cp in test["cp_refs"]:
            points_by_id[cp]["target_refs"].append(test["id"])
    families = design_stage.build_families(tests)
    family_of = {tc: family["id"] for family in families for tc in family["test_case_refs"]}
    merge = design_stage.merge_candidates(tests)

    # Questions and findings link both ways with the Test Cases they affect.
    question_links = {key: set() for key in question_id}
    finding_links = {key: set() for key in finding_id}
    for test in tests:
        for key in test.get("question_keys", []):
            question_links[key].add(test["id"])
        for key in test.get("finding_keys", []):
            finding_links[key].add(test["id"])
        for unknown in procedures[test["id"]]["unknowns"]:
            if unknown["question"]:
                question_links[unknown["question"]].add(test["id"])
    for question in questions_raw:
        for ref in question["tests"]:
            if ref in by_key:
                question_links[question["key"]].add(by_key[ref]["id"])
    for finding in findings_raw:
        for ref in finding["tests"]:
            if ref in by_key:
                finding_links[finding["key"]].add(by_key[ref]["id"])
    claim_requirements = {}
    for claim in design["claims"]:
        if claim["question"]:
            claim_requirements.setdefault(claim["question"], set()).add(claim["requirement_ref"])
    questions = []
    for question in questions_raw:
        refs = {req_by_key[key]["id"] for key in question["requirements"]} | claim_requirements.get(question["key"], set())
        default_refs = req_by_key[question["requirements"][0]]["source_refs"]
        questions.append({
            "id": question_id[question["key"]], "related_test_cases": sorted(question_links[question["key"]]),
            "requirement_refs": sorted(refs), "source_refs": _clean_refs(question["source_refs"] or default_refs),
            "question": question["question"], "reason": question["reason"], "blocking": question["blocking"],
            "impact": question["impact"],
        })
    findings = [{
        "id": finding_id[f["key"]], "type": f["type"], "statement": f["statement"],
        "requirement_refs": sorted(req_by_key[key]["id"] for key in f["requirements"]),
        "source_refs": _clean_refs(f["source_refs"]), "related_test_cases": sorted(finding_links[f["key"]]),
        "coverage_disposition": f["coverage_disposition"],
    } for f in findings_raw]
    questions_by_case: dict[str, list[str]] = {}
    for question in questions:
        for tc in question["related_test_cases"]:
            questions_by_case.setdefault(tc, []).append(question["id"])
    findings_by_case: dict[str, list[str]] = {}
    for finding in findings:
        for tc in finding["related_test_cases"]:
            findings_by_case.setdefault(tc, []).append(finding["id"])

    identifier_titles = {normalize_identifier(e["identifier"]): e["identifier"] for e in source_state["authority_index"]}
    cases = []
    for test in tests:
        procedure = procedures[test["id"]]
        case = {
            "schema_version": "2.2", "id": test["id"], "title": test["title"], "status": procedure["status"],
            "priority": test["priority"], "type": test["primary_type"], "objective": test["objective"],
            "requirement_refs": test["requirement_refs"], "scenario_refs": [family_of[test["id"]]],
            "coverage_point_refs": test["cp_refs"], "source_refs": _clean_refs(test["source_refs"]),
            "preconditions": procedure["preconditions"], "test_data": procedure["test_data"],
            "steps": procedure["steps"], "postconditions": procedure["postconditions"],
            "cleanup": procedure["cleanup"],
            "tags": [identifier_titles.get(i, i) for i in test["identifiers"]],
            "notes": procedure["notes"] + [f"{u['kind']}: {u['detail']}" for u in procedure["unknowns"]],
            "test_basis": test["basis"], "primary_type": test["primary_type"], "secondary_tags": [],
            "execution_status": procedure["status"],
            "question_refs": sorted(questions_by_case.get(test["id"], [])),
            "finding_refs": sorted(findings_by_case.get(test["id"], [])),
            "composes": test.get("composes", []),
            "automation_candidate": procedure["automation_suitability"] in {"HIGH", "MEDIUM"},
            "automation_layer": procedure["automation_layer"],
            "automation_tool_hint": procedure["automation_tool_hint"],
            "deterministic": test["basis"] != "EXPLORATORY",
            "priority_reason": test["priority_reason"],
            "automation_suitability": procedure["automation_suitability"],
            "automation_readiness": procedure["automation_readiness"],
            "readiness_blockers": procedure["readiness_blockers"],
            "failure_domain": test["failure_domain"],
            "source_identifiers": [identifier_titles.get(i, i) for i in test["identifiers"]],
        }
        if test.get("dimension"):
            case["expansion_dimension"] = test["dimension"]
        if test.get("pattern") or test.get("surface"):
            case["expansion_checklist_item"] = test.get("pattern") or test.get("surface")
        if procedure["single_step_reason"]:
            case["single_step_reason"] = procedure["single_step_reason"]
        if test["basis"] == "ACCEPTANCE":
            if len(test["claims"]) > 1:
                case["atomicity_exception"] = {
                    "reason": "INDIVISIBLE_CONTRACT", "shared_failure_domain": test["indivisible_contract"],
                    "claim_ids": test["claims"],
                }
            case["claim_exercise_map"] = [{
                "claim_id": claim_id, "coverage_point_id": cp_of_claim[claim_id], "test_case_id": test["id"],
                "step_refs": [procedure["oracle_step"]], "assertion_refs": ["expected"],
                "primary_type": test["primary_type"],
            } for claim_id in test["claims"]]
        if test["basis"] == "E2E":
            case["e2e_stage_map"] = [{
                "atomic_test_ref": by_key[stage["test"]]["id"] if stage["test"] in by_key else stage["test"],
                "trigger": stage["trigger"], "assertion_refs": [stage["observation"]],
            } for stage in test["stages"]]
        cases.append(case)

    statuses = {case["id"]: case["status"] for case in cases}
    ledger_errors: list[str] = []
    ledger = design_stage.identifier_ledger(
        source_state["authority_index"], design["claims"], tests, design["dispositions"],
        ledger_errors, statuses=statuses,
    )
    if ledger_errors:
        raise IntegrityError("identifier accounting changed after design: " + "; ".join(ledger_errors))
    claim_req = {claim["id"]: claim["requirement_ref"] for claim in design["claims"]}
    for entry in ledger:
        entry["requirement_refs"] = sorted({claim_req[c] for c in entry["claim_refs"]})
        entry["question_refs"] = [question_id[key] for key in entry["question_refs"] if key in question_id]
        entry["test_refs"] = sorted(set(entry["test_refs"]))

    cp_requirements = {point["requirement_ref"] for point in points}
    public_requirements = [{
        "id": item["id"], "statement": item["statement"],
        "status": item["status"] if item["id"] in cp_requirements else "NEEDS_CLARIFICATION",
        "source_refs": _clean_refs(item["source_refs"]), "source_identifier": item["source_identifier"],
        "source_title": item["source_title"], "source_statement": item["source_statement"], "kind": item["kind"],
    } for item in requirements]
    exercised = {claim for test in tests for claim in test["claims"]}
    gaps = validation.gap_metrics(ledger, design["claims"], exercised,
                                  expanded["test_asset_challenge"], questions, cases)
    summary = expanded["dimension_summary"]
    evidence = {
        "SCOPE_VALID": f"{len(source_state['records'])} physical source record(s); roles and digests locked at start.",
        "SOURCE_COVERAGE_VALID": f"{len(ledger)} authority identifier(s), all dispositioned: "
        + ", ".join(f"{k}={v}" for k, v in _count(e["disposition"] for e in ledger).items()),
        "NORMATIVE_BASELINE_VALID": f"{design['baseline']['count']} atomic Acceptance Test Case(s) frozen and unchanged.",
        "ADDITIVE_EXPANSION_VALID": f"{sum(item['evaluated'] for item in summary)}/{len(summary)} dimensions evaluated, "
        f"{sum(item['candidates_considered'] for item in summary)} candidate(s), "
        f"{len(expanded['test_asset_challenge'])} test asset behavior(s) challenged.",
        "PROCEDURE_QUALITY_VALID": f"{len(procedures)} procedure(s) validated in {run['output_locale']}.",
        "EVIDENCE_AND_REFERENCE_VALID": "Every evidence reference is inside the selected scope; Questions/Findings link back.",
        "PIPELINE_INTEGRITY_VALID": "Manifest hash chain verified through PROCEDURES before canonical assembly.",
        "PUBLICATION_VALID": "Canonical state validated against the public schemas before rendering.",
    }
    index = {
        "schema_version": "2.2", "generated_at": now(), "output_locale": run["output_locale"],
        "locale_source": run["locale_source"],
        "sources": [{key: record[key] for key in ("path", "role", "status", "reason", "content_digest")}
                    | {"authority": {"NORMATIVE": "NORMATIVE_PRIMARY", "IMPLEMENTATION": "IMPLEMENTATION",
                                     "SUPPORTING": "SUPPORTING", "QA_ASSET": "QA_ASSET"}[record["authority"]]}
                    for record in source_state["records"]],
        "requirements": public_requirements, "normative_clauses": clauses, "findings": findings,
        "coverage_points": points, "scenarios": families,
        "test_cases": [{
            "id": case["id"], "title": case["title"], "status": case["status"],
            "requirement_refs": case["requirement_refs"], "scenario_refs": case["scenario_refs"],
            "coverage_point_refs": case["coverage_point_refs"], "file": f"test-cases/{case['id']}.json",
            "markdown_file": f"test-cases-md/{case['id']}.md",
            **{field: case[field] for field in ("test_basis", "primary_type", "execution_status", "question_refs",
                                                "finding_refs", "composes", "automation_candidate")},
        } for case in cases],
        "merge_candidates": merge["candidates"], "quality_gates": validation.build_gates(evidence),
        "identifier_dispositions": ledger, "expansion_summary": summary, "gap_metrics": gaps,
        "baseline_comparison": baseline_comparison or {"status": "NOT_APPLIED"},
    }
    diagnostics = {
        "domain_model": design["domain_model"], "expansion_candidates": expanded["candidates"],
        "checklists": expanded["checklists"], "journeys": expanded["journeys"],
        "test_asset_challenge": expanded["test_asset_challenge"],
        "merge_detector": {k: v for k, v in merge.items() if k != "candidates"},
        "warnings": [*design["warnings"], *_result(run_dir, "procedures")["warnings"]],
    }
    return {"index": index, "questions": {"schema_version": "2.2", "questions": questions},
            "cases": cases, "diagnostics": diagnostics}


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def canonical_fingerprint(document: dict[str, Any]) -> str:
    return stable_digest({key: document[key] for key in ("index", "questions", "cases")})


def read_canonical(path: Path) -> dict[str, Any]:
    document = read_json(path)
    if document.get("public_schema_version") not in {"1.2", "2.2"}:
        raise IntegrityError("unsupported canonical suite version")
    if document.get("semantic_fingerprint") != canonical_fingerprint(document):
        raise IntegrityError("canonical suite fingerprint mismatch")
    return document


def render_outputs(canonical_path: Path, artifact_root: Path, formats: Any = None) -> dict[str, Any]:
    """Render selected public projections from canonical state only (no source reads)."""
    import render
    selected = {str(value).strip().upper() for value in (formats or DEFAULT_FORMATS)}
    unsupported = sorted(selected - PUBLIC_FORMATS)
    if unsupported or not selected:
        raise ValueError("Unsupported public output formats: " + ", ".join(unsupported or ["<none>"]))
    canonical = read_canonical(Path(canonical_path))
    work = Path(canonical_path).parent / "render-work"
    if work.exists():
        shutil.rmtree(work)
    write_json(work / "test-cases.json", canonical["index"])
    write_json(work / "questions.json", canonical["questions"])
    cases_by_id = {case["id"]: case for case in canonical["cases"]}
    for entry in canonical["index"]["test_cases"]:
        write_json(work / entry["file"], cases_by_id[entry["id"]])
    errors = validation.validate(work)
    if errors:
        raise ValueError("Canonical suite validation failed:\n- " + "\n- ".join(errors))
    markdown = render.render_markdown(work)
    report = render.render_report(work, artifact_formats=selected & {"JSON", "MARKDOWN"})
    output = Path(artifact_root).resolve() / "output"
    for stale in ("test-cases", "test-cases-md"):
        if (output / stale).is_dir():
            shutil.rmtree(output / stale)
    output.mkdir(parents=True, exist_ok=True)
    rendered, files = [], []
    if "JSON" in selected:
        for name in ("test-cases.json", "questions.json"):
            shutil.copy2(work / name, output / name)
            files.append(output / name)
        for entry in canonical["index"]["test_cases"]:
            (output / "test-cases").mkdir(exist_ok=True)
            shutil.copy2(work / entry["file"], output / entry["file"])
            files.append(output / entry["file"])
        rendered.append("JSON")
    if "MARKDOWN" in selected:
        (output / "test-cases-md").mkdir(exist_ok=True)
        for path in markdown:
            shutil.copy2(path, output / "test-cases-md" / path.name)
            files.append(output / "test-cases-md" / path.name)
        rendered.append("MARKDOWN")
    if "HTML" in selected:
        shutil.copy2(report, output / "report.html")
        files.append(output / "report.html")
        rendered.append("HTML")
    if "OPERATIONAL" in selected:
        target = output / "operational-scenarios.md"
        target.write_text(render.render_expansion_catalog(canonical["index"], canonical["cases"]), encoding="utf-8")
        files.append(target)
        rendered.append("OPERATIONAL")
    if "DIAGNOSTICS" in selected:
        diagnostics = Path(artifact_root).resolve() / "diagnostics"
        for name, value in canonical.get("diagnostics", {}).items():
            write_json(diagnostics / f"{name.replace('_', '-')}.json", value)
            files.append(diagnostics / f"{name.replace('_', '-')}.json")
        metrics = Path(canonical_path).parent / "run-metrics.json"
        if metrics.is_file():
            shutil.copy2(metrics, diagnostics / "run-metrics.json")
            files.append(diagnostics / "run-metrics.json")
        rendered.append("DIAGNOSTICS")
    return {"rendered_public_formats": sorted(rendered), "output_path": str(output),
            "files": [str(path) for path in files], "source_reads_during_render": 0,
            "semantic_fingerprint": canonical["semantic_fingerprint"]}


def _bind(run_dir: Path, key: str, value: Any) -> None:
    path = run_dir / "run-manifest.json"
    manifest = read_json(path)
    manifest[key] = value
    write_json(path, manifest)


def finalize_run(run_dir: Path, formats: Any = None, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate, persist canonical state, render the requested outputs and publish."""
    run_dir = Path(run_dir).resolve()
    run, source_state = _load(run_dir)
    state = _state(run_dir)
    if state.get("next_stage") != "finalize":
        raise IntegrityError(f"finalize requires every model stage (next: {state.get('next_stage')})")
    verify_manifest(run_dir / "run-manifest.json", require_publication=False)
    _check_sources_unchanged(run, source_state["records"])
    began = now()
    comparison = None
    if baseline is not None:
        import benchmark
        comparison = {"status": "APPLIED"}
    canonical = build_canonical(run_dir, comparison)
    if baseline is not None:
        report = benchmark.compare_with_baseline(canonical, baseline)
        canonical["index"]["baseline_comparison"] = {"status": "APPLIED", **report["counts"]}
        canonical["diagnostics"]["baseline_comparison"] = report
    document = {
        "internal_schema_version": "2", "public_schema_version": "2.2", "run_id": run["run_id"],
        "generator": GENERATOR, **canonical,
    }
    document["semantic_fingerprint"] = canonical_fingerprint(document)
    canonical_path = run_dir / "canonical-suite.json"
    write_json(canonical_path, document)
    _record(run_dir, "VALIDATION", started_at=began, inputs=[r["chain_digest"] for r in _manifest(run_dir)["stages"]],
            outputs={"fingerprint": document["semantic_fingerprint"]})
    _bind(run_dir, "canonical", {"file": canonical_path.name, "sha256": file_digest(canonical_path)})
    metrics = validation.suite_metrics(document["index"], document["cases"], document["questions"]["questions"])
    metrics.update({"stage_seconds": state.get("stage_seconds", {}), "stage_rejections": state.get("rejections", {}),
                    "authority_identifiers": len(source_state["authority_index"]),
                    "test_assets_discovered": len(source_state["test_assets"]),
                    "warnings": document["diagnostics"]["warnings"]})
    write_json(run_dir / "run-metrics.json", metrics)
    render_began = now()
    rendered = render_outputs(canonical_path, Path(run["artifact_root"]), formats)
    _record(run_dir, "RENDER", started_at=render_began, inputs=document["semantic_fingerprint"],
            outputs=rendered["rendered_public_formats"])
    _publish(run_dir, Path(run["artifact_root"]), rendered["files"])
    _record(run_dir, "PUBLICATION", started_at=render_began, inputs=rendered["rendered_public_formats"],
            outputs=_manifest(run_dir)["publication"])
    verify_manifest(run_dir / "run-manifest.json")
    _save_state(run_dir, status="VALIDATED", next_stage=None)
    superseded = _supersede_others(run_dir)
    return {"run_dir": str(run_dir), "canonical_path": str(canonical_path), "render": rendered,
            "metrics": metrics, "superseded_runs": superseded}


def _publish(run_dir: Path, artifact_root: Path, files: list[str]) -> None:
    root = Path(artifact_root).resolve()
    _bind(run_dir, "publication", {
        "artifact_root": str(root), "published_at": now(),
        "files": [{"path": Path(path).resolve().relative_to(root).as_posix(), "sha256": file_digest(Path(path))}
                  for path in sorted(files)],
    })


def _supersede_others(run_dir: Path) -> list[str]:
    changed = []
    for state_path in run_dir.parent.glob("*/run-state.json"):
        if state_path.parent == run_dir:
            continue
        document = read_json(state_path)
        if document.get("status") == "VALIDATED":
            document.update(status="SUPERSEDED", superseded_by=run_dir.name)
            write_json(state_path, document)
            changed.append(state_path.parent.name)
    return sorted(changed)


def render_run(run_dir: Path, formats: Any = None) -> dict[str, Any]:
    """Re-render a validated run from canonical state and refresh the publication proof."""
    run_dir = Path(run_dir).resolve()
    run, _ = _load(run_dir)
    if _state(run_dir).get("status") not in {"VALIDATED", "SUPERSEDED"}:
        raise IntegrityError("only a validated run can be rendered")
    manifest = verify_manifest(run_dir / "run-manifest.json", require_publication=False)
    if manifest.get("canonical") is None or len(manifest["stages"]) != len(STAGES):
        raise IntegrityError("render requires a complete official run")
    rendered = render_outputs(run_dir / "canonical-suite.json", Path(run["artifact_root"]), formats)
    _publish(run_dir, Path(run["artifact_root"]), rendered["files"])
    verify_manifest(run_dir / "run-manifest.json")
    return rendered


def status(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    return {"state": _state(run_dir), "stages": [item["stage"] for item in _manifest(run_dir)["stages"]]}


# --- work orders -------------------------------------------------------------------------

STAGE_GUIDE = {
    "design": [
        "Read every selected source yourself (authority text is also in authority-text/). You own the QA reasoning; the runtime only validates.",
        "Build a lightweight domain_model from the sources: actors, entities, states, operations, invariants, permissions, integrations, events, dependencies, observables, failure_surfaces. Use the project's own vocabulary.",
        "Create one requirement per authority identifier or unidentified requirement. Keep source_identifier/source_title exactly as the authority states them (see authority_identifiers).",
        "Decompose each requirement AND each business rule into atomic claims: one independently diagnosable obligation each. Transversal rules (uniqueness, audit, roles, state machines, deduplication, idempotency, history/KPIs, isolation, lifecycle) need their own claims.",
        "Design one atomic Acceptance test per failure domain: title, objective, family, actor, state, trigger, expected (the oracle), failure_domain, primary_type, priority, priority_reason. Independent obligations triggered by one action stay separate tests; explain indivisible_contract only for one indivisible observation.",
        "Every authority identifier must end exercised by tests or carry an explicit disposition (QUESTION_REQUIRED, NOT_TESTABLE_WITH_REASON, SUPERSEDED_BY_AUTHORITY). Missing implementation is never a reason to drop normative behavior.",
        "Write all human-readable text in output_locale. Keep code symbols, endpoints, constants, enums, fields, ids and filenames as they are.",
    ],
    "expansion": [
        "The normative baseline is frozen: add, never edit. Evaluate every dimension in `dimensions` across all families and record what you considered.",
        "Walk operator_error_patterns and failure_surfaces as reasoning prompts: decide how, or whether, each applies to THIS project using its domain_model. Mark irrelevant ones NOT_APPLICABLE with the project-specific reason; never materialize a scenario just because the checklist names it.",
        "Materialized candidates carry a test with basis DERIVED (oracle_source in authority), CHARACTERIZATION (oracle_source in implementation/test assets) or EXPLORATORY (undefined policy: safe invariants plus a Question). Anchor each to the normative claims it derives from.",
        "ALREADY_COVERED needs covered_by plus the candidate intent (actor, state, trigger, failure_domain, expected); coverage is checked semantically against the target test.",
        "Challenge every discovered test asset: normalize its intent, compare, and disposition it. Existing tests never become authority.",
        "Give every use case an E2E candidate (use_case): a MATERIALIZED journey composes at least two atomic tests stage by stage; otherwise ALREADY_COVERED by atomics, QUESTION_REQUIRED or NOT_APPLICABLE with a reason.",
    ],
    "procedures": [
        "Write an executable procedure for every Test Case: preconditions (real starting context), test_data, steps (action + observable expected_result), postconditions/cleanup when relevant.",
        "Use semantic fixtures (ROLE_A, ENTITY_ACTIVE_A, ACCOUNT_B) with clear properties when exact values are unnecessary; use real values only when evidence provides them. Never invent routes, labels or ids.",
        "One step only when one action completes the failure domain (explain single_step_reason); never compress a multi-action flow.",
        "The oracle_step (default: last) must observe the designed expected result.",
        "Record only material unknowns (MISSING_ORACLE, AMBIGUOUS_POLICY, UNRESOLVED_PERMISSION, MISSING_EXECUTION_SURFACE, UNKNOWN_SETUP_PATH, EXTERNAL_DEPENDENCY_UNAVAILABLE) or automation-only unknowns (MISSING_FIXTURE, MISSING_SELECTOR, MISSING_ENVIRONMENT). Status and automation readiness are derived from them.",
        "Classify automation.suitability (HIGH, MEDIUM, LOW, MANUAL_ONLY) and automation.layer independently of readiness.",
    ],
}


def _work_order(run_dir: Path) -> Path:
    run, source_state = _load(run_dir)
    state = _state(run_dir)
    stage = state.get("next_stage")
    order: dict[str, Any] = {
        "run_dir": str(run_dir), "next_stage": stage, "output_locale": run["output_locale"],
        "locale_source": run["locale_source"], "instructions": STAGE_GUIDE.get(stage, []),
        "submit": f"python scripts/pipeline.py submit --run \"{run_dir}\" --stage {stage} --file <payload.json>"
        if stage in MODEL_STAGES else f"python scripts/pipeline.py finalize --run \"{run_dir}\"",
        "contract": "references/stage-contracts.md",
    }
    if stage == "design":
        order["sources"] = [{k: r[k] for k in ("path", "role", "status", "reason")} for r in source_state["records"]]
        order["authority_identifiers"] = source_state["authority_index"]
        order["domain_dimensions"] = list(design_stage.DOMAIN_DIMENSIONS)
    elif stage == "expansion":
        design = _result(run_dir, "design")
        order["domain_model"] = design["domain_model"]
        order["frozen_tests"] = [{k: t[k] for k in ("id", "key", "title", "family", "actor", "state", "trigger",
                                                    "expected", "failure_domain", "claim_keys")} for t in design["tests"]]
        order["claims"] = [{k: c[k] for k in ("key", "requirement_key", "text", "destination", "identifiers")}
                           for c in design["claims"]]
        order["dimensions"] = list(expansion_stage.DIMENSIONS)
        order["operator_error_patterns"] = expansion_stage.OPERATOR_PATTERNS
        order["failure_surfaces"] = expansion_stage.FAILURE_SURFACES
        order["use_cases"] = [e for e in source_state["authority_index"] if e["kind"] == "USE_CASE"]
        order["test_assets"] = source_state["test_assets"]
    elif stage == "procedures":
        order["tests"] = [{k: t.get(k) for k in ("id", "key", "basis", "title", "objective", "actor", "state",
                                                 "trigger", "expected", "failure_domain", "dimension")}
                          for t in _all_tests(run_dir)]
    path = run_dir / "work-order.json"
    write_json(path, order)
    return path


# --- CLI -----------------------------------------------------------------------------

def _parse_mapping(values: list[str], label: str) -> list[tuple[str, str]]:
    pairs = []
    for value in values or []:
        key, separator, item = value.rpartition("=")
        if not separator or not key or not item:
            raise SystemExit(f"{label} must look like PATH=VALUE: {value}")
        pairs.append((key, item))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="lock scope, read sources and issue the design work order")
    start.add_argument("--workspace", required=True, type=Path)
    start.add_argument("--source", action="append", required=True, help="SELECTOR=ROLE (repeatable)")
    start.add_argument("--artifact-root", required=True, type=Path)
    start.add_argument("--run-id", required=True)
    start.add_argument("--locale")
    start.add_argument("--request", default="")
    start.add_argument("--transcription", action="append", default=[], help="SOURCE=TEXT_FILE for unreadable sources")
    start.add_argument("--id-pattern")
    submit = commands.add_parser("submit", help="submit one model stage payload")
    submit.add_argument("--run", required=True, type=Path)
    submit.add_argument("--stage", required=True, choices=sorted(MODEL_STAGES))
    submit.add_argument("--file", required=True, type=Path)
    final = commands.add_parser("finalize", help="validate, persist canonical state and publish")
    final.add_argument("--run", required=True, type=Path)
    final.add_argument("--formats", default=",".join(DEFAULT_FORMATS))
    final.add_argument("--baseline", type=Path, help="benchmark-only historical baseline")
    again = commands.add_parser("render", help="re-render a validated run from canonical state")
    again.add_argument("--run", required=True, type=Path)
    again.add_argument("--formats", default=",".join(DEFAULT_FORMATS))
    for name in ("status", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("--run", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start_run(
                workspace=args.workspace,
                sources_selected=[{"path": path, "role": role} for path, role in _parse_mapping(args.source, "--source")],
                artifact_root=args.artifact_root, run_id=args.run_id, locale=args.locale,
                request_text=args.request, transcriptions=dict(_parse_mapping(args.transcription, "--transcription")),
                id_pattern=args.id_pattern,
            )
        elif args.command == "submit":
            result = submit_stage(args.run, args.stage, read_json(args.file))
        elif args.command == "finalize":
            result = finalize_run(args.run, args.formats.split(","), read_json(args.baseline) if args.baseline else None)
            result.pop("metrics", None)
        elif args.command == "render":
            result = render_run(args.run, args.formats.split(","))
            result.pop("files", None)
        elif args.command == "status":
            result = status(args.run)
        else:
            verify_manifest(args.run)
            result = {"verified": True}
    except (StageError, IntegrityError, ValueError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
