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
from collections import Counter
import hashlib
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
    GENERATOR, StageError, content_tokens, file_digest, normalize_identifier, now, read_json, stable_digest,
    write_json,
)
import design as design_stage  # noqa: E402
import expansion as expansion_stage  # noqa: E402
import instructions as instructions_stage  # noqa: E402
import procedures as procedure_stage  # noqa: E402
import reading as reading_stage  # noqa: E402
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
    """Digest check once per stage (never per Test Case); contents are not reread."""
    workspace = Path(run["workspace"])
    for record in records:
        path = workspace / record["path"]
        if not path.is_file() or file_digest(path) != record["content_digest"]:
            raise IntegrityError(f"selected source changed after the run started: {record['path']}")


_FINGERPRINT_REASONS = {
    "corpus": "SOURCE_HASH_CHANGED", "roles": "SOURCE_ROLE_CHANGED",
    "selectors": "SELECTOR_STRUCTURE_CHANGED", "request": "REQUEST_CHANGED", "locale": "LOCALE_CHANGED",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def selection_fingerprint(
    records: list[dict[str, Any]], selectors: list[dict[str, Any]] | None,
    normalized_request: dict[str, Any] | None, locale: str | None,
) -> dict[str, Any]:
    """What a run means, beyond which bytes it read: the corpus (path + digest), each
    file's role, the selector structure (path, role, order, owned files), the semantic
    part of the normalized request (guidance, seeds, source order) and the requested
    locale. Presentation choices (formats, output directory, diagnostics) and reading
    preferences are deliberately excluded: they never change what a run means. A
    component that could not be known (None) is not compared."""
    components = {
        "corpus": _digest([(r["path"], r["content_digest"]) for r in records]),
        "roles": _digest([(r["path"], r["role"]) for r in records]),
        "selectors": _digest([(s["path"], s["role"], s["order"], s["files"]) for s in selectors]) if selectors else None,
        "request": _digest({k: normalized_request.get(k) for k in ("guidance", "seeds", "source_order")})
        if normalized_request is not None else None,
        "locale": locale or "INFERRED",
    }
    return {"digest": _digest(components), "components": components}


def _stored_fingerprint(run_dir: Path) -> dict[str, Any]:
    """The fingerprint of an existing run; runs written before it was stored are
    fingerprinted from their own persisted records, plan and normalized request."""
    run = read_json(run_dir / "run.json")
    if run.get("selection_fingerprint"):
        return run["selection_fingerprint"]
    records = read_json(run_dir / "sources.json")["records"]
    plan_path = run_dir / "reading" / "task-plan.json"
    selectors = read_json(plan_path).get("selectors") if plan_path.is_file() else None
    request_path = run_dir / "normalized-request.json"
    request = read_json(request_path) if request_path.is_file() else None
    fingerprint = selection_fingerprint(records, selectors, request, None)
    fingerprint["components"]["locale"] = None  # not recorded by older runs
    return fingerprint


def selection_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    before, after = previous.get("components", {}), current.get("components", {})
    return [reason for key, reason in _FINGERPRINT_REASONS.items()
            if before.get(key) is not None and after.get(key) is not None and before[key] != after[key]]


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
    id_pattern: str | None = None, allow_source_root: bool = False, formats: Any = None,
    diagnostics: bool = False, source_order: list[list[str]] | None = None,
    clarifications: list[dict[str, Any]] | None = None, reading: dict[str, Any] | None = None,
    normalized_request: dict[str, Any] | None = None, supersedes: str | None = None,
) -> dict[str, Any]:
    """Lock scope, read sources, index authority and issue the design work order.

    Requested formats, the diagnostics option, an explicit source order and prior
    clarifications are run properties: the work orders carry them to the model and
    finalize applies the formats unless it is given others.

    `reading` states how the corpus should be read: {"strategy": "MULTI_AGENT_PER_SOURCE"
    (default) | "SEQUENTIAL" | "MULTI_AGENT_BATCHED", "worker_model": "haiku" | ...,
    "concurrency": int}. This runtime never spawns agents itself; it only plans the
    work deterministically (one task per eligible source by default) and records what
    was requested so the invoking agent can follow it. See reading.py.

    `normalized_request` is the host's semantic reading of the instructions file merged with
    explicit overrides (see instructions.py). It is persisted as normalized-request.json
    and its guidance/seeds reach every model work order — as guidance, never authority.

    `supersedes` names an earlier run in the same artifact root that this run explicitly
    revises. The relation is recorded on this run only; the earlier run is never modified.
    """
    began = now()
    requested = _normalize_formats(formats, diagnostics)
    workspace = Path(workspace).resolve()
    root = sources.resolve_artifact_root(
        skill_root=SKILL_ROOT, source_root=workspace, artifact_root=Path(artifact_root),
        allow_source_root=allow_source_root,
    )
    run_dir = run_directory(root, run_id)
    if supersedes is not None:
        if supersedes == run_id or not (run_dir.parent / supersedes / "run.json").is_file():
            raise IntegrityError(f"supersedes must name another existing run in {run_dir.parent}: {supersedes!r}")
    selection = sources.assign_roles(workspace, sources_selected)
    selectors = {str(item.get("path", "")).strip() for item in sources_selected}
    for group in source_order or []:
        outside = [str(value) for value in group
                   if str(value) not in selectors and str(value) not in selection["roles"]]
        if outside:
            raise sources.ScopeError("source order names sources outside the selection: " + ", ".join(outside))
    transcripts = {str(key): Path(value) for key, value in (transcriptions or {}).items()}
    records, texts = sources.build_source_records(
        workspace, selection["roles"], transcripts, text_cache=root / ".ftd" / "text-cache",
    )
    ownership = sources.selector_ownership(workspace, sources_selected)
    fingerprint = selection_fingerprint(records, reading_stage.selector_view(records, ownership),
                                        normalized_request, locale)
    events = []
    if (run_dir / "run.json").is_file():
        # A run resumes only when it still means the same thing: same bytes, same roles,
        # same selector structure, same semantic request. Same (path, digest) alone is
        # not enough — the same file promoted to authority is a different run.
        changes = selection_changes(_stored_fingerprint(run_dir), fingerprint)
        state = _state(run_dir)
        if not changes:
            if (run_dir / "reading" / "task-plan.json").is_file():
                # Plans written before selector ownership existed are upgraded in place:
                # every recorded state and reader result is kept, nothing is re-read.
                reading_stage.attach_selectors(run_dir, records, ownership, strategy=(reading or {}).get("strategy"))
                if state.get("next_stage") == "reading":
                    # The current request's reading preferences win over the stored plan.
                    provenance = ((normalized_request or {}).get("effective") or {}).get("provenance")
                    task_plan = reading_stage.apply_preferences(run_dir, reading, provenance)
                    run = read_json(run_dir / "run.json")
                    run["reading"] = {k: task_plan.get(k) for k in ("strategy", "worker_model", "concurrency")}
                    write_json(run_dir / "run.json", run)
                    _work_order(run_dir)
            return {"run_dir": str(run_dir), "resumed": True, "state": state,
                    "work_order": str(run_dir / "work-order.json")}
        if state.get("status") in {"VALIDATED", "SUPERSEDED"}:
            raise IntegrityError(
                f"run {run_id} is frozen ({state['status']}) and its selection changed ({', '.join(changes)}); "
                "start a new run id — compatible file catalogs are reused, the frozen run stays evidence")
        shutil.rmtree(run_dir)
        events.append({"event": "invalidated", "reason": changes[0], "reasons": changes})
    run_dir.mkdir(parents=True, exist_ok=True)
    authority_texts = [texts[r["path"]] for r in records if r["role"] == "FUNCTIONAL_AUTHORITY"]
    locale_info = sources.infer_locale(locale, authority_texts, request_text)
    authority_index = sources.index_authority(records, texts, id_pattern)
    asset_warnings: list[str] = []
    test_assets = sources.discover_all_test_assets(records, texts, asset_warnings)
    text_dir = run_dir / "authority-text"
    for record in records:
        if record["role"] == "FUNCTIONAL_AUTHORITY":
            name = reading_stage.source_key(record["path"]) + ".txt"
            (text_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (text_dir / name).write_text(texts[record["path"]], encoding="utf-8")
    # Every eligible source's text is snapshotted once, run-scoped, so later stages and
    # a post-suite Challenge can look up bounded evidence without rereading the corpus.
    evidence_dir = run_dir / "evidence" / "text"
    catalog = []
    for record in records:
        text = texts.get(record["path"])
        entry = {"path": record["path"], "role": record["role"], "status": record["status"],
                 "content_digest": record["content_digest"], "text_ref": None, "line_count": None}
        if text is not None:
            name = reading_stage.source_key(record["path"]) + ".txt"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / name).write_text(text, encoding="utf-8")
            entry.update({"text_ref": f"text/{name}", "line_count": len(text.splitlines())})
        catalog.append(entry)
    write_json(run_dir / "evidence" / "source-catalog.json", {"sources": catalog})
    reading_request = dict(reading or {})
    reading_plan = reading_stage.plan(
        records, root, run_dir, selectors=ownership,
        strategy=reading_request.get("strategy"),
        worker_model=reading_request.get("worker_model"), concurrency=reading_request.get("concurrency"),
    )
    reading_states = reading_stage.summary(reading_plan)
    run = {
        "run_id": run_id, "generator": GENERATOR, "workspace": str(workspace),
        "artifact_root": str(root), "created_at": began, "request_text": request_text,
        "id_pattern": id_pattern, "formats": requested,
        "source_order": [list(map(str, group)) for group in source_order or []],
        "clarifications": [dict(item) for item in clarifications or []],
        "reading": {"strategy": reading_plan["strategy"], "worker_model": reading_plan["worker_model"],
                    "concurrency": reading_plan["concurrency"]},
        "selection_fingerprint": fingerprint,
        **({"supersedes": supersedes} if supersedes else {}),
        **locale_info,
    }
    write_json(run_dir / "run.json", run)
    if normalized_request is not None:
        write_json(run_dir / "normalized-request.json", normalized_request)
    elif (run_dir / "normalized-request.json").is_file():
        (run_dir / "normalized-request.json").unlink()
    write_json(run_dir / "sources.json", {
        "scope": {key: selection[key] for key in ("selected_scope_roots", "resolved_scope_paths")},
        "records": records, "authority_index": authority_index, "test_assets": test_assets,
        "test_asset_warnings": asset_warnings,
    })
    _record(run_dir, "SOURCE_SELECTION", started_at=began, inputs=sources_selected,
            outputs={"scope": selection["resolved_scope_paths"], "records": records},
            files=[])
    _record(run_dir, "SEMANTIC_EXTRACTION", started_at=began, inputs=[r["content_digest"] for r in records],
            outputs={"authority_index": authority_index, "test_assets": test_assets, **locale_info})
    if reading_states["PLANNED"] == 0:
        # Nothing left for readers (sequential, or every catalog reused): reconcile now.
        if reading_plan["strategy"] != "SEQUENTIAL":
            _reconcile_and_bind(run_dir, root)
        first = "design"
    else:
        first = "reading"
    _save_state(run_dir, status="IN_PROGRESS", next_stage=first, events=events,
                rejections={}, stage_seconds={}, stage_started_at=now())
    order = _work_order(run_dir)
    return {"run_dir": str(run_dir), "resumed": False, "work_order": str(order), **locale_info,
            "authority_identifiers": len(authority_index), "test_assets": len(test_assets),
            "test_asset_warnings": asset_warnings,
            "reading_task_plan": str(run_dir / "reading" / "task-plan.json"), "reading": run["reading"],
            "reading_states": reading_states, "next_stage": first}


# --- reading: reader results and reconciliation ------------------------------------------

def _reconcile_and_bind(run_dir: Path, artifact_root: Path) -> dict[str, Any]:
    result = reading_stage.reconcile(run_dir, artifact_root)
    # Bound into the TEST_DESIGN manifest record, so Design provably ran on this catalog.
    write_json(run_dir / "stages" / "reading.reconciliation.json", result)
    return result


def submit_reading(run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    state = _state(run_dir)
    if state.get("next_stage") != "reading":
        raise IntegrityError(f"reader results are not expected now (next: {state.get('next_stage')})")
    outcome = reading_stage.submit(run_dir, results)
    return {**outcome, "next_stage": "reading",
            "reconcile": f"python scripts/pipeline.py reading-reconcile --run \"{run_dir}\""}


def reconcile_reading(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run, _ = _load(run_dir)
    state = _state(run_dir)
    if state.get("next_stage") != "reading":
        raise IntegrityError(f"reading is not the next stage (next: {state.get('next_stage')})")
    result = _reconcile_and_bind(run_dir, Path(run["artifact_root"]))
    _save_state(run_dir, next_stage="design", stage_started_at=now())
    order = _work_order(run_dir)
    return {"reconciled": True, "next_stage": "design", "work_order": str(order),
            "states": result["states"], "identifier_conflicts": len(result["identifier_conflicts"]),
            "worker_failures": len(result["worker_failures"])}


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
    _check_official_stage_files(run_dir)
    _check_sources_unchanged(run, source_state["records"])
    _save_state(run_dir, integrity_checks=state.get("integrity_checks", 0) + 1)
    records = source_state["records"]
    workspace = Path(run["workspace"])
    texts = {}
    for record in records:
        if record["role"] == "FUNCTIONAL_AUTHORITY":
            name = reading_stage.source_key(record["path"]) + ".txt"
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
            asset_sources = {asset["source"] for asset in source_state["test_assets"]}
            catalog = {e["path"]: e for e in read_json(run_dir / "evidence" / "source-catalog.json")["sources"]}
            asset_texts = {
                source: (run_dir / "evidence" / catalog[source]["text_ref"]).read_text(encoding="utf-8")
                for source in asset_sources if catalog.get(source, {}).get("text_ref")}
            normalized_path = run_dir / "normalized-request.json"
            guidance = (instructions_stage.guidance_items(read_json(normalized_path))
                        if normalized_path.is_file() else [])
            result = expansion_stage.validate_expansion(payload, {
                **base, "design": design, "taken_keys": _taken_keys(design),
                "test_assets": source_state["test_assets"], "asset_texts": asset_texts,
                "guidance_items": guidance,
            })
            offset = len(design["tests"])
            for number, test in enumerate(result["tests"], offset + 1):
                test["id"] = f"TC-{number:03d}"
        else:
            design, expanded = _result(run_dir, "design"), _result(run_dir, "expansion")
            tests = [*design["tests"], *expanded["tests"]]
            questions = [*design["questions"], *expanded["questions"]]
            snapshots = sorted((run_dir / "evidence" / "text").glob("*.txt"))
            result = procedure_stage.validate_procedures(payload, {
                **base, "tests": tests, "question_keys": [q["key"] for q in questions],
                "source_tokens": procedure_stage.source_vocabulary(
                    path.read_text(encoding="utf-8") for path in snapshots),
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
    bound = [payload_path, result_path]
    reconciliation = stages_dir / "reading.reconciliation.json"
    if stage == "design" and reconciliation.is_file():
        bound.append(reconciliation)
    _record(run_dir, MODEL_STAGES[stage], started_at=started, inputs=payload, outputs=result,
            files=bound)
    following = {"design": "expansion", "expansion": "procedures", "procedures": "finalize"}[stage]
    seconds = state.get("stage_seconds", {})
    seconds[stage] = round(time.time() - _epoch(started), 3)
    _save_state(run_dir, next_stage=following, stage_seconds=seconds, stage_started_at=now())
    order = _work_order(run_dir)
    return {"stage": stage, "recorded": True, "next_stage": following, "work_order": str(order),
            "warnings": result.get("warnings", [])}


def merge_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine batch files of one stage: list fields concatenate in the given order."""
    merged: dict[str, Any] = {}
    for payload in payloads:
        for key, value in payload.items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
            elif key in merged and merged[key] != value:
                raise ValueError(f"batch files disagree on {key!r}")
            else:
                merged[key] = value
    return merged


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
        "question_refs": sorted(question_id[key] for key in f.get("question_keys", [])),
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
            "coverage_point_refs": test["cp_refs"],
            "source_refs": _clean_refs(test["source_refs"] + procedure.get("evidence_refs", [])),
            "preconditions": procedure["preconditions"], "test_data": procedure["test_data"],
            "steps": procedure["steps"], "postconditions": procedure["postconditions"],
            "cleanup": procedure["cleanup"], "state_contract": procedure_stage.state_contract(procedure["cleanup"]),
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
        if procedure.get("execution_variants"):
            case["execution_variants"] = procedure["execution_variants"]
        if procedure.get("request_contract"):
            case["request_contract"] = procedure["request_contract"]
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
    key_to_id = {test["key"]: test["id"] for test in tests}
    if expanded.get("guidance_dispositions"):
        index["guidance_dispositions"] = [{
            "item": entry["item"], "text": entry["text"], "disposition": entry["disposition"],
            "test_refs": [key_to_id[key] for key in entry["test_keys"] if key in key_to_id],
            "question_ref": question_id.get(entry["question"]) if entry["question"] else None,
            "reason": entry["reason"]} for entry in expanded["guidance_dispositions"]]
    diagnostics = {
        "domain_model": design["domain_model"], "expansion_candidates": expanded["candidates"],
        "checklists": expanded["checklists"], "journeys": expanded["journeys"],
        "test_asset_challenge": expanded["test_asset_challenge"],
        "merge_detector": {k: v for k, v in merge.items() if k != "candidates"},
        "warnings": [*design["warnings"], *_result(run_dir, "procedures")["warnings"]],
    }
    return {"index": index, "questions": {"schema_version": "2.2", "questions": questions},
            "cases": cases, "diagnostics": diagnostics}


# --- publication organization: placements and execution views, never clones -------------
#
# A Test Case keeps one identity; *where* it is shown is derived publication metadata.
# Every projection (HTML, machine-readable JSON, Azure suites) reads this one model.

ORGANIZATION_LABELS = {
    "pt": {"TRANSVERSAL": "Regras de negócio transversais", "E2E": "Casos de uso ponta a ponta (E2E)",
           "LOAD_CONCURRENCY": "Carga e concorrência", "PHYSICAL_DEVICE": "Físicos / dispositivos",
           "CHAOS_RESILIENCE": "Chaos / resiliência", "MANUAL_FIELD": "Manual / campo"},
    "es": {"TRANSVERSAL": "Reglas de negocio transversales", "E2E": "Casos de uso de extremo a extremo (E2E)",
           "LOAD_CONCURRENCY": "Carga y concurrencia", "PHYSICAL_DEVICE": "Físicos / dispositivos",
           "CHAOS_RESILIENCE": "Caos / resiliencia", "MANUAL_FIELD": "Manual / campo"},
    "en": {"TRANSVERSAL": "Cross-cutting business rules", "E2E": "End-to-end use cases (E2E)",
           "LOAD_CONCURRENCY": "Load and concurrency", "PHYSICAL_DEVICE": "Physical / devices",
           "CHAOS_RESILIENCE": "Chaos / resilience", "MANUAL_FIELD": "Manual / field"},
}
EXECUTION_VIEWS = ("E2E", "LOAD_CONCURRENCY", "PHYSICAL_DEVICE", "CHAOS_RESILIENCE", "MANUAL_FIELD")
# Canonical signals per execution view (primary types and automation layers the suite already records).
_VIEW_TYPES = {"LOAD_CONCURRENCY": {"PERFORMANCE", "CONCURRENCY", "RACE_CONDITION"},
               "PHYSICAL_DEVICE": {"HARDWARE_INTEGRATION", "FIELD"},
               "CHAOS_RESILIENCE": {"CHAOS", "RECOVERY", "RESILIENCE"}}
# Post-suite execution tags per view; a case may carry any well-formed tag, these are the recognized ones.
_VIEW_TAGS = {"LOAD_CONCURRENCY": {"LOAD", "PERFORMANCE", "CONCURRENCY"},
              "PHYSICAL_DEVICE": {"PHYSICAL_DEVICE", "HARDWARE", "DEVICE"},
              "CHAOS_RESILIENCE": {"CHAOS_RECOVERY", "CHAOS", "RESILIENCE"},
              "MANUAL_FIELD": {"MANUAL", "FIELD", "MANUAL_FIELD"}}
_STEP_LINE = re.compile(r"^\s*(\d{1,2})[.)]\s+(\S.*)$")


def _use_case_flows(authority_index: list[dict[str, Any]], authority_texts: dict[str, str]) -> dict[str, Any]:
    """Main-flow steps of every documented use case and the use case each alternative or
    exception flow belongs to, read from the authority's own structure: a use case's
    section runs to the next use case (or higher-level identifier); numbered lines before
    its first alternative flow are the main flow; flows defined inside the section are its
    alternatives."""
    ordered = sorted(authority_index, key=lambda item: (item.get("source", ""), item.get("line") or 0))
    flows: dict[str, Any] = {}
    for position, item in enumerate(ordered):
        if sources.identifier_kind(item["identifier"]) != "USE_CASE" or not item.get("line"):
            continue
        end, alternatives = None, []
        for later in ordered[position + 1:]:
            if later.get("source") != item.get("source"):
                break
            kind = sources.identifier_kind(later["identifier"])
            if kind in {"ALTERNATIVE_FLOW", "EXCEPTION_FLOW"}:
                alternatives.append(later)
                continue
            end = later.get("line")
            break
        lines = (authority_texts.get(item.get("source", "")) or "").splitlines()
        stop = (alternatives[0]["line"] if alternatives else end or len(lines) + 1) - 1
        steps = [match.group(2) for line in lines[item["line"]:stop] if (match := _STEP_LINE.match(line))]
        flows[normalize_identifier(item["identifier"])] = {
            "identifier": item["identifier"], "steps": steps,
            "alternatives": {normalize_identifier(alt["identifier"]): alt.get("excerpt") or alt.get("title") or ""
                             for alt in alternatives},
        }
    return flows


def _best_step(text: str, steps: list[str], minimum: float = 0.25) -> int | None:
    """The main-flow step a text is about: TF-IDF cosine over the flow's own steps, so
    words every step uses decide nothing. None when no step is a confident match."""
    import math

    def stems(value: str) -> set[str]:
        # A light prefix stem lets inflections meet ("bloquear"/"bloqueia", "confirm"/"confirmed").
        return {token[:5] if len(token) > 5 else token for token in content_tokens(value)}

    step_tokens = [stems(step) for step in steps]
    frequency = Counter(token for tokens in step_tokens for token in tokens)
    weight = {token: math.log((len(steps) + 1) / (count + 1)) + 1 for token, count in frequency.items()}
    words = stems(text)
    best, best_score = None, 0.0
    for index, tokens in enumerate(step_tokens):
        norm = math.sqrt(sum(weight[t] ** 2 for t in tokens)) or 1.0
        score = sum(weight[t] ** 2 for t in tokens & words) / norm / (math.sqrt(sum(weight[t] ** 2 for t in words & set(weight))) or 1.0)
        if score > best_score:
            best, best_score = index, score
    return best if best_score >= minimum else None


def _case_text(case: dict[str, Any]) -> str:
    return " ".join([case.get("title", ""), case.get("objective", "")])


def build_organization(
    canonical: dict[str, Any], *, authority_index: list[dict[str, Any]], authority_texts: dict[str, str],
    chaos_runs: list[dict[str, Any]] | None = None, locale: str | None = None,
) -> dict[str, Any]:
    """Placements of canonical and post-suite cases in functional groups and execution
    views. Functional groups are the authority's functional requirements (or, when it has
    none, its use cases, else the scenario families). Membership is traceability: a case
    joins a requirement group only when it traces to that requirement. A use-case flow only
    ORDERS a group's members (main flow, an alternative flow's cases right after the step it
    challenges); it never adds members. A case that traces to a use case or flow but to no
    requirement joins that use case's own group; one tracing to neither is transversal.
    Without a derivable flow the canonical order is kept. A case appears in several groups
    by reference only."""
    language = (locale or canonical["index"].get("output_locale") or "en").split("-")[0].lower()
    labels = ORGANIZATION_LABELS.get(language, ORGANIZATION_LABELS["en"])
    cases = canonical["cases"]
    order_of = {case["id"]: number for number, case in enumerate(cases)}
    requirements = canonical["index"]["requirements"]
    kind_of = {normalize_identifier(r["source_identifier"]): (r.get("kind") or sources.identifier_kind(r["source_identifier"]))
               for r in requirements if r.get("source_identifier")}
    title_of = {normalize_identifier(r["source_identifier"]): (r["source_identifier"], r.get("source_title"))
                for r in requirements if r.get("source_identifier")}
    flows = _use_case_flows(authority_index, authority_texts)
    owner_use_case = {alt: uc for uc, flow in flows.items() for alt in flow["alternatives"]}

    functional_kind = next((k for k in ("FUNCTIONAL_REQUIREMENT", "USE_CASE") if k in kind_of.values()), None)
    # Which functional group a use case belongs to: the one its Test Cases co-occur with most.
    co: dict[str, Counter] = {}
    for case in cases:
        ids = {normalize_identifier(v) for v in case.get("source_identifiers", [])}
        for uc in (i for i in ids if kind_of.get(i) == "USE_CASE"):
            co.setdefault(uc, Counter()).update(i for i in ids if kind_of.get(i) == functional_kind)
    # Several requirements may share one documented flow: each is ORDERED by the use case its
    # own Test Cases co-occur with most. This never decides who belongs to the requirement.
    group_flow: dict[str, str] = {}
    if functional_kind == "FUNCTIONAL_REQUIREMENT":
        for group in {g for counter in co.values() for g in counter}:
            group_flow[group] = sorted(co, key=lambda u: (-co[u][group], u))[0]
    # A use case's own group follows its own flow.
    for uc in {*flows, *(i for i in kind_of if kind_of[i] == "USE_CASE")}:
        group_flow.setdefault(uc, uc)

    def functional_groups(case: dict[str, Any]) -> tuple[list[str], str]:
        if case.get("test_basis") == "E2E":
            return [], "E2E"
        ids = [normalize_identifier(v) for v in case.get("source_identifiers", [])]
        if functional_kind is None:
            return [f"FAMILY:{(case.get('scenario_refs') or ['-'])[0]}"], "FAMILY"
        direct = [i for i in ids if kind_of.get(i) == functional_kind]
        if direct:
            return list(dict.fromkeys(direct)), "IDENTIFIER"
        # No requirement it traces to: its use case (directly, or as the owner of the flow it
        # exercises) is its home — never a requirement merely sharing that use case.
        via = [i if kind_of.get(i) == "USE_CASE" else owner_use_case.get(i) for i in ids]
        via = [uc for uc in via if uc]
        if via:
            return list(dict.fromkeys(via)), "USE_CASE"
        return ["TRANSVERSAL"], "TRANSVERSAL"

    clauses = {c["id"]: c.get("normalized_claim", "") for c in canonical["index"].get("normative_clauses", [])}
    points = {p["id"]: p for p in canonical["index"].get("coverage_points", [])}
    claim_text = {case["id"]: " ".join(clauses.get(ref, "") for point in case.get("coverage_point_refs", [])
                                      for ref in points.get(point, {}).get("clause_refs", []))
                  for case in cases}
    # A requirement's title names what it is about; its statement only when it has no title.
    requirement_text = {normalize_identifier(r["source_identifier"]): r.get("source_title") or (r.get("source_statement") or "")[:300]
                        for r in requirements if r.get("source_identifier")}
    members: dict[str, list[dict[str, Any]]] = {}
    positions: dict[tuple[str, str], float | None] = {}
    for case in cases:
        groups, via = functional_groups(case)
        if via == "E2E":
            members.setdefault("E2E", []).append({"case": case["id"], "origin": "CANONICAL", "via": "BASIS"})
            continue
        ids = {normalize_identifier(v) for v in case.get("source_identifiers", [])}
        for group in groups:
            flow = flows.get(group_flow.get(group, ""), {})
            steps = flow.get("steps", [])
            position = None
            alternative = next((normalize_identifier(a) for a in case.get("source_identifiers", [])
                                if normalize_identifier(a) in flow.get("alternatives", {})), None)
            if alternative:
                # An alternative flow's cases follow the main-flow step it branches from.
                step = _best_step(flow["alternatives"][alternative], steps)
                position = (step if step is not None else len(steps)) + 0.5
            elif steps and case.get("test_basis") in {None, "ACCEPTANCE", "REGRESSION"}:
                step = None
                if group_flow.get(group) in ids:
                    # A case exercising the use case itself: its claims are the step sentences.
                    step = _best_step(f"{_case_text(case)} {claim_text.get(case['id'], '')}", steps)
                if step is None and group in requirement_text:
                    # A requirement's own acceptance cases stay together, in authority order,
                    # at the step the requirement describes.
                    step = _best_step(requirement_text[group], steps, minimum=0.0)
                position = float(step) if step is not None else None
            positions[(group, case["id"])] = position
            members.setdefault(group, []).append({"case": case["id"], "origin": "CANONICAL", "via": via})
    # Derived, characterization and exploratory cases follow the acceptance case whose
    # coverage point they share.
    point_owner: dict[tuple[str, str], str] = {}
    for case in cases:
        if case.get("test_basis") in {None, "ACCEPTANCE", "REGRESSION"}:
            for point in case.get("coverage_point_refs", []):
                point_owner.setdefault(point, case["id"])
    for case in cases:
        if case.get("test_basis") in {None, "ACCEPTANCE", "REGRESSION", "E2E"}:
            continue
        owners = [point_owner[p] for p in case.get("coverage_point_refs", []) if p in point_owner]
        for group, entries in members.items():
            if any(e["case"] == case["id"] for e in entries) and positions.get((group, case["id"])) is None:
                anchor = next((o for o in owners if (group, o) in positions), None)
                if anchor is not None and positions.get((group, anchor)) is not None:
                    positions[(group, case["id"])] = positions[(group, anchor)]
                    order_of[case["id"]] = order_of[anchor] + order_of[case["id"]] / (10 * len(cases) + 1)

    def sort_members(group: str) -> list[dict[str, Any]]:
        # Cases without a matched flow step keep their canonical neighbours' place.
        carried, last = {}, 0.0
        for entry in sorted(members.get(group, []), key=lambda e: order_of[e["case"]]):
            position = positions.get((group, entry["case"]))
            carried[entry["case"]] = last = position if position is not None else last
        return sorted(members.get(group, []), key=lambda e: (carried[e["case"]], order_of[e["case"]]))

    ordered_groups = {group: sort_members(group) for group in members if group != "E2E"}
    # Post-suite cases sit right after the related canonical case they challenge, in every
    # group that case belongs to; unrelated ones join the transversal group.
    chaos_records = []
    for run in chaos_runs or []:
        for case in run.get("cases", []):
            chaos_records.append({"case": case["id"], "chaos_run_id": run["chaos_run_id"], "raw": case})
    for record in chaos_records:
        related = [r for r in record["raw"].get("related_test_cases", []) if r in order_of]
        entry = {"case": record["case"], "origin": "POST_SUITE", "chaos_run_id": record["chaos_run_id"]}
        placed = False
        for group, entries in ordered_groups.items():
            anchors = [i for i, e in enumerate(entries) if e["origin"] == "CANONICAL" and e["case"] in related]
            if anchors:
                entries.insert(max(anchors) + 1, {**entry, "via": "RELATED_TEST_CASE"})
                placed = True
        if not placed:
            ordered_groups.setdefault("TRANSVERSAL", []).append({**entry, "via": "UNRELATED"})

    def group_label(group: str) -> str:
        if group in labels:
            return labels[group]
        if group.startswith("FAMILY:"):
            return group.split(":", 1)[1]
        display, title = title_of.get(group, (group, None))
        return f"{display} — {title.strip()}" if title and title.strip() and title.strip() != display else display

    def group_kind(group: str) -> str:
        if group == "TRANSVERSAL":
            return "TRANSVERSAL"
        return "USE_CASE" if functional_kind == "FUNCTIONAL_REQUIREMENT" and kind_of.get(group) == "USE_CASE" \
            or (functional_kind == "FUNCTIONAL_REQUIREMENT" and group in flows) else "FUNCTIONAL"

    functional_order = sorted((g for g in members if g not in labels),
                              key=lambda g: (g.startswith("FAMILY:"), group_kind(g) == "USE_CASE", g))
    groups_out = []
    for group in [*functional_order, "TRANSVERSAL"]:
        if group not in ordered_groups:
            continue
        flow_uc = group_flow.get(group)
        ordered = [{**e, "order": i} for i, e in enumerate(ordered_groups[group], 1)]
        matched = any(positions.get((group, e["case"])) is not None for e in ordered)
        groups_out.append({
            "id": group, "kind": group_kind(group), "label": group_label(group),
            "identifier": title_of.get(group, (None,))[0], "flow_reference": flows[flow_uc]["identifier"] if flow_uc in flows else None,
            "order_source": "USE_CASE_MAIN_FLOW" if matched else "CANONICAL_ORDER", "members": ordered,
        })
    execution_order = {}
    for rank, group in enumerate(groups_out):
        for entry in group["members"]:
            key = (entry["origin"], entry.get("chaos_run_id"), entry["case"])
            execution_order.setdefault(key, (rank, entry["order"]))

    by_view: dict[str, list[dict[str, Any]]] = {view: [] for view in EXECUTION_VIEWS}
    by_view["E2E"] = [dict(e) for e in members.get("E2E", [])]
    for case in cases:
        variants = {v.get("kind") for v in case.get("execution_variants", []) or []}
        for view in ("LOAD_CONCURRENCY", "PHYSICAL_DEVICE", "CHAOS_RESILIENCE"):
            if case.get("primary_type") in _VIEW_TYPES[view] or (view == "PHYSICAL_DEVICE" and case.get("automation_layer") == "HARDWARE"):
                by_view[view].append({"case": case["id"], "origin": "CANONICAL", "via": "CATEGORY"})
            elif view in variants:
                by_view[view].append({"case": case["id"], "origin": "CANONICAL", "via": "EXECUTION_VARIANT"})
        if case.get("automation_suitability") == "MANUAL_ONLY" or "MANUAL_FIELD" in variants:
            by_view["MANUAL_FIELD"].append({"case": case["id"], "origin": "CANONICAL", "via": "CATEGORY"})
    load_ids = {e["case"] for e in by_view["LOAD_CONCURRENCY"]}
    for record in chaos_records:
        tags = set(record["raw"].get("execution_tags", []))
        tags |= {v.get("kind") for v in record["raw"].get("execution_variants", []) or []}
        related = set(record["raw"].get("related_test_cases", []))
        for view, recognized in _VIEW_TAGS.items():
            inherited = view == "LOAD_CONCURRENCY" and related and related <= load_ids
            if tags & recognized or inherited:
                by_view[view].append({"case": record["case"], "origin": "POST_SUITE", "chaos_run_id": record["chaos_run_id"],
                                      "via": "EXECUTION_TAG" if tags & recognized else "RELATED_TEST_CASE"})
    physical = {(e["origin"], e["case"]) for e in by_view["PHYSICAL_DEVICE"]}
    if {(e["origin"], e["case"]) for e in by_view["MANUAL_FIELD"]} <= physical:
        by_view["MANUAL_FIELD"] = []  # a manual view identical to the physical one adds nothing
    for view in EXECUTION_VIEWS:
        entries = sorted(by_view[view], key=lambda e: execution_order.get(
            (e["origin"], e.get("chaos_run_id"), e["case"]), (len(groups_out), order_of.get(e["case"], len(cases)))))
        if entries:
            groups_out.append({"id": view, "kind": "EXECUTION_VIEW", "label": labels[view], "identifier": None,
                               "flow_reference": None, "order_source": "EXECUTION_ORDER",
                               "members": [{**e, "order": i} for i, e in enumerate(entries, 1)]})

    memberships: dict[str, list[dict[str, Any]]] = {}
    for group in groups_out:
        for entry in group["members"]:
            key = entry["case"] if entry["origin"] == "CANONICAL" else f"{entry['chaos_run_id']}:{entry['case']}"
            memberships.setdefault(key, []).append({"group": group["id"], "order": entry["order"]})
    return {
        "schema_version": "1", "functional_grouping": functional_kind or "SCENARIO_FAMILY",
        "groups": groups_out, "memberships": memberships,
        "diagnostics": {
            "canonical_cases": len(cases), "post_suite_cases": len(chaos_records),
            "groups": sum(g["kind"] != "EXECUTION_VIEW" for g in groups_out),
            "execution_views": sum(g["kind"] == "EXECUTION_VIEW" for g in groups_out),
            "placements": sum(len(g["members"]) for g in groups_out),
            "multi_membership_cases": sum(len(v) > 1 for v in memberships.values()),
            "cloned_cases": 0,
        },
    }


def _chaos_runs_for(run_dir: Path) -> list[dict[str, Any]]:
    """Finalized post-suite runs of this run and of the revision it explicitly supersedes
    (a successor carries its predecessor's discoveries; they keep their own parent)."""
    run_dir = Path(run_dir)
    run = read_json(run_dir / "run.json")
    parents = [run_dir]
    if run.get("supersedes"):
        parents.append(run_dir.parent / run["supersedes"])
    runs = []
    for parent in parents:
        base = parent / "challenges"
        for folder in sorted(base.iterdir()) if base.is_dir() else []:
            lineage, cases = folder / "challenge-run.json", folder / "challenge-cases.json"
            if lineage.is_file() and cases.is_file() and read_json(lineage).get("status") == "FINALIZED":
                runs.append({"chaos_run_id": folder.name, "parent_run_id": parent.name,
                             "cases": read_json(cases)["cases"]})
    return runs


def organization_for_run(run_dir: Path, canonical: dict[str, Any] | None = None,
                         chaos_runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The publication organization of a run, from persisted state only (no source reads).
    `chaos_runs` narrows the post-suite runs placed (default: every finalized one)."""
    run_dir = Path(run_dir)
    canonical = canonical or read_canonical(run_dir / "canonical-suite.json")
    source_state = read_json(run_dir / "sources.json")
    texts = {}
    for record in source_state["records"]:
        if record["role"] == "FUNCTIONAL_AUTHORITY":
            path = run_dir / "authority-text" / (reading_stage.source_key(record["path"]) + ".txt")
            if path.is_file():
                texts[record["path"]] = path.read_text(encoding="utf-8")
    chaos_runs = _chaos_runs_for(run_dir) if chaos_runs is None else chaos_runs
    organization = build_organization(canonical, authority_index=source_state["authority_index"],
                                      authority_texts=texts, chaos_runs=chaos_runs)
    organization["post_suite_runs"] = [{k: r[k] for k in ("chaos_run_id", "parent_run_id")} | {"cases": len(r["cases"])}
                                       for r in chaos_runs]
    return organization


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
    if isinstance(formats, str):
        formats = formats.split(",")
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
    # One organization (functional placements, execution views, post-suite cases) feeds the
    # report, the machine-readable views and the Azure suites alike.
    run_dir = Path(canonical_path).parent
    organization = None
    if (run_dir / "sources.json").is_file() and (run_dir / "run.json").is_file():
        organization = organization_for_run(run_dir, canonical)
        organization["post_suite_cases"] = [
            {**case, "key": f"{run['chaos_run_id']}:{case['id']}", "chaos_run_id": run["chaos_run_id"],
             "parent_run_id": run["parent_run_id"]}
            for run in _chaos_runs_for(run_dir) for case in run["cases"]]
        write_json(work / "organization.json", organization)
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
        if organization:
            # Placements reference cases; post-suite case content stays in its own run's files.
            refs = [{k: case.get(k) for k in ("key", "id", "chaos_run_id", "parent_run_id", "title")}
                    for case in organization["post_suite_cases"]]
            write_json(output / "organization.json", {**organization, "post_suite_cases": refs})
            files.append(output / "organization.json")
        for entry in canonical["index"]["test_cases"]:
            (output / "test-cases").mkdir(exist_ok=True)
            shutil.copy2(work / entry["file"], output / entry["file"])
            files.append(output / entry["file"])
        rendered.append("JSON")
    if "MARKDOWN" in selected:
        if organization:
            plan = output / "execution-plan.md"
            plan.write_text(render.render_execution_plan(organization, canonical["index"]), encoding="utf-8")
            files.append(plan)
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


def _normalize_formats(formats: Any, diagnostics: bool = False) -> list[str]:
    if isinstance(formats, str):
        formats = formats.split(",")
    selected = [str(value).strip().upper() for value in (formats or DEFAULT_FORMATS) if str(value).strip()]
    if diagnostics and "DIAGNOSTICS" not in selected:
        selected.append("DIAGNOSTICS")
    unsupported = sorted(set(selected) - PUBLIC_FORMATS)
    if unsupported:
        raise ValueError("Unsupported public output formats: " + ", ".join(unsupported))
    return selected


def _bind(run_dir: Path, key: str, value: Any) -> None:
    path = run_dir / "run-manifest.json"
    manifest = read_json(path)
    manifest[key] = value
    write_json(path, manifest)


# The only files official stage state consists of. Anything else in `stages/` (a helper script,
# a generated mapping, a scratch payload) is not official state and must live elsewhere.
OFFICIAL_STAGE_FILES = {"reading.reconciliation.json",
                        *(f"{stage}.{kind}.json" for stage in ("design", "expansion", "procedures")
                          for kind in ("payload", "result"))}


def _check_official_stage_files(run_dir: Path) -> None:
    folder = Path(run_dir) / "stages"
    foreign = sorted(p.name for p in folder.iterdir() if p.name not in OFFICIAL_STAGE_FILES) if folder.is_dir() else []
    if foreign:
        raise IntegrityError(
            f"unofficial files in {folder}: {foreign}. Official stage state is written only by the pipeline; keep "
            "helper scripts and drafts outside the run directory — they never become stage state")


def finalize_run(run_dir: Path, formats: Any = None, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate, persist canonical state, render the requested outputs and publish."""
    run_dir = Path(run_dir).resolve()
    _check_official_stage_files(run_dir)
    run, source_state = _load(run_dir)
    formats = formats or run.get("formats")
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
    # Recomputed from the recorded procedures so metric additions never require resubmission.
    procedure_metrics = procedure_stage.procedure_metrics(_result(run_dir, "procedures").get("procedures", {}))
    procedure_seconds = state.get("stage_seconds", {}).get("procedures")
    metrics.update({
        **procedure_metrics,
        "procedure_generation_seconds": procedure_seconds,
        "average_procedure_generation_seconds": round(procedure_seconds / procedure_metrics["procedures_generated"], 3)
        if procedure_seconds and procedure_metrics.get("procedures_generated") else None,
        **reading_metrics(run_dir, source_state["records"]),
        "runtime_source_rereads": 0,
        "source_integrity_checks": state.get("integrity_checks", 0),
    })
    metrics.update({"stage_seconds": state.get("stage_seconds", {}), "stage_rejections": state.get("rejections", {}),
                    "authority_identifiers": len(source_state["authority_index"]),
                    "test_assets_discovered": len(source_state["test_assets"]),
                    "test_assets_by_source_role": _count(a.get("source_role", "TEST_ASSET")
                                                         for a in source_state["test_assets"]),
                    "warnings": document["diagnostics"]["warnings"] + source_state.get("test_asset_warnings", [])})
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
    # A validated run is frozen: a newer publication never edits it. Supersession is an
    # explicit relation recorded by the newer run (run.json "supersedes"), nothing more.
    return {"run_dir": str(run_dir), "canonical_path": str(canonical_path), "render": rendered,
            "metrics": metrics, "supersedes": run.get("supersedes")}


def _publish(run_dir: Path, artifact_root: Path, files: list[str]) -> None:
    root = Path(artifact_root).resolve()
    _bind(run_dir, "publication", {
        "artifact_root": str(root), "published_at": now(),
        "files": [{"path": Path(path).resolve().relative_to(root).as_posix(), "sha256": file_digest(Path(path))}
                  for path in sorted(files)],
    })


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


def reading_metrics(run_dir: Path, records: list[dict[str, Any]]) -> dict[str, int]:
    """What reading really did, from the reading plan's per-file states: every selected file is
    accounted for, but only files a reader (or the main model, reading sequentially) catalogued
    in this run count as read. A reused catalog is not a read; hashing a file to check that it
    is unchanged is not a read either."""
    plan_path = Path(run_dir) / "reading" / "task-plan.json"
    if not plan_path.is_file():  # runs planned before reading ledgers: every readable file was read once
        readable = sum(record["status"] in {"READ", "TRANSCRIBED"} for record in records)
        return {"source_files_accounted": len(records), "runtime_source_reads": readable,
                "reused_file_catalogs": 0, "source_digest_checks": len(records)}
    states = Counter(task["state"] for task in read_json(plan_path)["tasks"])
    return {
        "source_files_accounted": sum(n for state, n in states.items() if state != "PLANNED"),
        "runtime_source_reads": states["CATALOGED"] + states["MAIN_MODEL"],
        "reused_file_catalogs": states["REUSED"],
        "source_digest_checks": len(records),
    }


def refresh_publication_after_post_suite(parent_run_dir: Path) -> list[str]:
    """After a post-suite run finalizes, re-render the publication that shows it: the parent
    run, or a successor that explicitly supersedes it, whichever currently owns the published
    output. Canonical state is never touched and nothing is read or regenerated; a run whose
    publication was already replaced by another run is left as it is."""
    parent = Path(parent_run_dir).resolve()
    candidates = [parent] + sorted(
        path.parent for path in parent.parent.glob("*/run.json")
        if path.parent != parent and read_json(path).get("supersedes") == parent.name)
    refreshed = []
    for run_dir in candidates:
        if _state(run_dir).get("status") != "VALIDATED":
            continue
        try:
            verify_manifest(run_dir / "run-manifest.json", require_publication=True)
        except IntegrityError:
            continue  # its published files are no longer the current output
        render_run(run_dir)
        refreshed.append(run_dir.name)
    return refreshed


def status(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    return {"state": _state(run_dir), "stages": [item["stage"] for item in _manifest(run_dir)["stages"]]}


# --- work orders -------------------------------------------------------------------------

STAGE_GUIDE = {
    "reading": [
        "One lightweight reader per entry in `reader_assignments`: each entry is one source selector the user declared (a file or a whole directory), never one reader per physical file. Prefer the lightweight model this host offers (e.g. Haiku on Claude). Run at most `concurrency` readers at once; later `wave`s wait for a free slot. Honor any explicit user preference recorded in `reading`.",
        "Each reader reads its selector's files with ordinary file/navigation tools (list, open, read ranges, search) — it must not write or run helper scripts, parsers or crawlers to automate cataloging. It returns one selector result: facts (headings, identifiers with their stated titles, actors, entities, states, operations, integrations, config_facts, candidate_rules, flows, test_assets, excerpts with file and line spans, references, ambiguities), each citing its `file`, plus a `files` entry for EVERY pending file: CATALOGED with that file's own catalog, INSPECTED (read, nothing to add), or FAILED with an error. Readers never decide claims, oracles, Test Cases, Findings, Questions, coverage or authority.",
        "Split a selector into internal shards only when it cannot fit the reader's real context limit; submit each shard's result separately (same `selector_id`, a `shard` label) — they reconcile back into one selector catalog.",
        "Submit results with `pipeline.py reading-submit`, then run `pipeline.py reading-reconcile`, which refuses while any physical file is unaccounted. You may prepare an authority-only skeleton while readers run, but Design is decided and submitted only after reconciliation. If sub-agents are unavailable, restart with --reading-strategy SEQUENTIAL and read the sources yourself; say which mode actually ran.",
    ],
    "design": [
        "This is a semantic reasoning stage (so are expansion and procedures): write each item from its own claims, evidence and oracle. Do not generate the payload with a mapping or template script; templated items are rejected, and helper files never go into the run's stages/ directory.",
        "Use the reconciled reader catalog (reading/source-catalog.json and reconciliation.json) as your index of the corpus, then read what you need from the evidence snapshots or authority-text/. Conflicts listed in reconciliation are for you to judge — nothing was majority-voted. You own the QA reasoning; the runtime only validates.",
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
        "When `user_guidance` lists items (anchors `instructions.md#guidance-NNN` / `#seed-NNN`), give each exactly one `guidance_dispositions` entry: MATERIALIZED or ALREADY_COVERED with the `tests` that exercise it, USED_FOR_ORDERING or NOT_APPLICABLE_WITH_REASON with a `reason`, or QUESTION_REQUIRED with the `question`. Guidance is not authority and never forces a Test Case; it must not disappear unanswered.",
        "Materialized candidates carry a test with basis DERIVED (oracle_source in authority), CHARACTERIZATION (oracle_source in implementation/test assets) or EXPLORATORY (undefined policy: safe invariants plus a Question). Anchor each to the normative claims it derives from.",
        "ALREADY_COVERED needs covered_by plus the candidate intent (actor, state, trigger, failure_domain, expected); coverage is checked semantically against the target test.",
        "Challenge every discovered test asset: normalize its intent, compare, and disposition it. Existing tests never become authority.",
        "Give every use case an E2E candidate (use_case): a MATERIALIZED journey composes at least two atomic tests stage by stage; otherwise ALREADY_COVERED by atomics, QUESTION_REQUIRED or NOT_APPLICABLE with a reason.",
    ],
    "procedures": [
        "Write an executable procedure for every Test Case: preconditions (real starting context), test_data, steps (action + observable expected_result), postconditions/cleanup when relevant.",
        "Write each step once, for two readers: a tester who has never seen the product and an agent that will later translate it into UI/API/load automation. Make clear, when evidence supports it, WHO acts (actor/session), WHERE (execution surface), WHAT (one atomic action), on which TARGET, with which DATA (semantic fixture), and the EXPECTED observable result. Never invent selectors, test ids, labels, screens, routes, endpoints, credentials, columns, device commands, messages or timeouts — declare an unknown instead. Keep canonical steps tool-agnostic (no Playwright/TestSprite/k6 syntax).",
        "Use semantic fixtures (ROLE_A, ENTITY_ACTIVE_A, ACCOUNT_B) with clear properties when exact values are unnecessary; use real values only when evidence provides them. Never invent routes, labels or ids.",
        "One step only when one action completes the failure domain (explain single_step_reason); never compress a multi-action flow.",
        "The oracle_step (default: last) must observe the designed expected result.",
        "A procedure must stand alone at execution time: a tester or an automation agent reading only the Test Case must not need the requirements, source code or FTD internals to understand what it means and how to run it. State the resources and their relationships (who ACTOR_A is, which properties ENTITY_A has, which device or environment is involved), the starting state, what evidence to collect, the resulting state (postconditions) and, when evidence supports it, how to return the environment to a reusable state (cleanup).",
        "A step that changes the environment or suppresses a signal to create the test condition (restart or stop a service, cut a connection, power off or shield a device, keep a tag or label from being read) needs evidence that says how: list the step number in an evidence_ref's `supports`. Without it, keep the scenario (its intent, e.g. 'a traversal in which the identifier is not captured') and declare UNKNOWN_SETUP_PATH or MISSING_EXECUTION_SURFACE — never invent the technique, and such a case is not READY.",
        "Every expected result states what becomes observable (a status, counter, state, message or record) — never only that the request was sent, received or processed — and names one outcome: when the policy could go either way, declare the unknown instead of writing 'X or Y'. Every semantic fixture used (ACTOR_A, ENTITY_A, DEVICE_B) is described in test_data with its role, properties and relationships, consistently across preconditions and steps.",
        "Load, latency and capacity: an expected result may assert a numeric threshold only when the designed Test Case states it. When the sources define no SLA, write a characterization: apply a declared, progressively increasing load (experiment configuration, in the action or test_data), record rate, throughput, latency, errors/timeouts, lost or duplicated operations and integrity failures, stop by the declared method, and report the observed saturation or degradation point — linking the Question that asks for the threshold.",
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
        if stage in MODEL_STAGES else (
            f"python scripts/pipeline.py reading-submit --run \"{run_dir}\" --file <reader-result.json> (repeatable), "
            f"then python scripts/pipeline.py reading-reconcile --run \"{run_dir}\""
            if stage == "reading" else f"python scripts/pipeline.py finalize --run \"{run_dir}\""),
        "contract": "references/stage-contracts.md",
        "requested_formats": run.get("formats"),
    }
    if run.get("source_order"):
        order["source_order"] = run["source_order"]
    if run.get("clarifications"):
        order["user_clarifications"] = run["clarifications"]
    if stage in MODEL_STAGES and (run_dir / "normalized-request.json").is_file():
        normalized = read_json(run_dir / "normalized-request.json")
        order["user_guidance"] = {
            "guidance": normalized.get("guidance", []), "seeds": normalized.get("seeds", []),
            "items": instructions_stage.guidance_items(normalized),
            "note": "From the instructions file: seeds and guidance provoke reasoning and never limit it. "
                    "They are not authority — a seed the selected authority/evidence does not support "
                    "is never promoted to a normative Test Case, Finding or oracle.",
        }
    if stage == "reading":
        task_plan = read_json(run_dir / "reading" / "task-plan.json")
        catalog = {e["path"]: e for e in read_json(run_dir / "evidence" / "source-catalog.json")["sources"]}
        order["reading"] = {k: task_plan[k] for k in ("strategy", "worker_model", "concurrency", "reader_role")}
        order["reader_assignments"] = [{
            **{k: a[k] for k in ("selector_id", "selector_path", "role", "wave", "files_total", "files_already_accounted")},
            "files_pending": [{
                **{k: t[k] for k in ("source_key", "path", "content_digest")},
                "snapshot": str(run_dir / "evidence" / catalog[t["path"]]["text_ref"]) if catalog[t["path"]]["text_ref"] else None,
                "line_count": catalog[t["path"]]["line_count"],
            } for t in a["files_pending"]],
        } for a in reading_stage.assignments(task_plan)]
        order["reader_result_contract"] = {
            "selector_result_fields": sorted(reading_stage.SELECTOR_RESULT_FIELDS),
            "file_entry": {"fields": ["source_key", "path", "content_digest", "status", "catalog", "error"],
                           "status": list(reading_stage.FILE_STATUSES)},
            "catalog_sections": sorted(reading_stage.CATALOG_FIELDS),
            "forbidden_catalog_sections": sorted(reading_stage.FORBIDDEN_FIELDS),
            "provenance": "every selector-level fact may cite `file` (an owned path); excerpts must",
            "reader": {"role": reading_stage.READER_ROLE, "model": "the model that actually ran"},
        }
    if stage == "design":
        order["sources"] = [{k: r[k] for k in ("path", "role", "status", "reason")} for r in source_state["records"]]
        if (run_dir / "reading" / "reconciliation.json").is_file():
            order["reader_catalog"] = str(run_dir / "reading" / "source-catalog.json")
            order["reading_reconciliation"] = str(run_dir / "reading" / "reconciliation.json")
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
        # Lightweight, already-indexed context: the model writes procedures from these
        # slices and targeted lookups instead of rereading the corpus per Test Case.
        design = _result(run_dir, "design")
        claims = {c["id"]: c["text"] for c in design["claims"]}
        excerpts = {normalize_identifier(e["identifier"]): (e["identifier"], e["excerpt"][:400])
                    for e in source_state["authority_index"]}
        tests = _all_tests(run_dir)
        order["evidence_index"] = [{k: r[k] for k in ("path", "role")} for r in source_state["records"]
                                   if r["role"] != "FUNCTIONAL_AUTHORITY" and r["status"] in {"READ", "TRANSCRIBED"}]
        order["tests"] = [{
            **{k: t.get(k) for k in ("id", "key", "basis", "title", "objective", "actor", "state", "trigger",
                                     "expected", "failure_domain", "dimension", "family")},
            "claims": [claims[c] for c in t["claims"] if c in claims],
            "authority_excerpts": dict(excerpts[i] for i in t["identifiers"] if i in excerpts),
        } for t in tests]
        batches: dict[str, list[str]] = {}
        for t in tests:
            batches.setdefault(t["family"], []).append(t["id"])
        order["batches"] = [{"family": family, "tests": ids} for family, ids in batches.items()]
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
    start = commands.add_parser("start", help="lock scope, plan source readers and issue the first work order")
    start.add_argument("--workspace", required=True, type=Path)
    start.add_argument("--source", action="append", required=True, help="SELECTOR=ROLE (repeatable)")
    start.add_argument("--artifact-root", required=True, type=Path)
    start.add_argument("--run-id", required=True)
    start.add_argument("--locale")
    start.add_argument("--request", default="")
    start.add_argument("--transcription", action="append", default=[], help="SOURCE=TEXT_FILE for unreadable sources")
    start.add_argument("--id-pattern")
    start.add_argument("--formats", help="HTML,JSON,MARKDOWN,DIAGNOSTICS,OPERATIONAL (default HTML,JSON,MARKDOWN)")
    start.add_argument("--diagnostics", action="store_true")
    start.add_argument("--order", action="append", default=[], help="comma-separated selectors read as one ordered group (repeatable)")
    start.add_argument("--reading-strategy", choices=("MULTI_AGENT_PER_SOURCE", "MULTI_AGENT_BATCHED", "SEQUENTIAL"),
                       help="default MULTI_AGENT_PER_SOURCE; SEQUENTIAL disables the default multi-agent reading plan")
    start.add_argument("--reading-model", help="preferred lightweight worker model, e.g. haiku")
    start.add_argument("--reading-concurrency", type=int, help="bounded concurrent reading tasks")
    start.add_argument("--supersedes", help="an earlier run id this run explicitly revises (never modified)")
    submit = commands.add_parser("submit", help="submit one model stage payload")
    submit.add_argument("--run", required=True, type=Path)
    submit.add_argument("--stage", required=True, choices=sorted(MODEL_STAGES))
    submit.add_argument("--file", required=True, type=Path, action="append",
                        help="stage payload; repeat to merge batch files (e.g. one per Scenario Family)")
    final = commands.add_parser("finalize", help="validate, persist canonical state and publish")
    final.add_argument("--run", required=True, type=Path)
    final.add_argument("--formats", help="defaults to the formats requested at start")
    final.add_argument("--baseline", type=Path, help="benchmark-only historical baseline")
    again = commands.add_parser("render", help="re-render a validated run from canonical state")
    again.add_argument("--run", required=True, type=Path)
    again.add_argument("--formats", default=",".join(DEFAULT_FORMATS))
    for name in ("status", "verify", "reading-reconcile"):
        sub = commands.add_parser(name)
        sub.add_argument("--run", required=True, type=Path)
    reader = commands.add_parser("reading-submit", help="record source-reader results (repeatable --file)")
    reader.add_argument("--run", required=True, type=Path)
    reader.add_argument("--file", required=True, type=Path, action="append")
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start_run(
                workspace=args.workspace,
                sources_selected=[{"path": path, "role": role} for path, role in _parse_mapping(args.source, "--source")],
                artifact_root=args.artifact_root, run_id=args.run_id, locale=args.locale,
                request_text=args.request, transcriptions=dict(_parse_mapping(args.transcription, "--transcription")),
                id_pattern=args.id_pattern, formats=args.formats, diagnostics=args.diagnostics,
                source_order=[group.split(",") for group in args.order],
                reading={"strategy": args.reading_strategy, "worker_model": args.reading_model,
                        "concurrency": args.reading_concurrency}, supersedes=args.supersedes,
            )
        elif args.command == "submit":
            result = submit_stage(args.run, args.stage, merge_payloads([read_json(path) for path in args.file]))
        elif args.command == "finalize":
            result = finalize_run(args.run, args.formats, read_json(args.baseline) if args.baseline else None)
            result.pop("metrics", None)
        elif args.command == "render":
            result = render_run(args.run, args.formats.split(","))
            result.pop("files", None)
        elif args.command == "status":
            result = status(args.run)
        elif args.command == "reading-submit":
            loaded = [read_json(path) for path in args.file]
            result = submit_reading(args.run, [r for item in loaded for r in (item.get("results") if "results" in item else [item])])
        elif args.command == "reading-reconcile":
            result = reconcile_reading(args.run)
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
