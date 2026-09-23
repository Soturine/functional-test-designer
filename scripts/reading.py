#!/usr/bin/env python3
"""Default multi-agent source reading: plan, reader results, reconciliation, reuse.

Many lightweight readers read faster; one main model decides. This module owns only
the deterministic half: one logical reading task per eligible selected source, the
validation of each reader's factual catalog, the reconciliation of all catalogs
before Design, and digest-bound reuse of catalogs across runs. It never reads for
meaning and never lets a reader decide claims, oracles, Test Cases, Findings or
Questions.

Task states:
    PLANNED        eligible source waiting for a reader result
    REUSED         a compatible catalog (same key, digest, role, contract) was reused
    CATALOGED      a validated reader result exists for this run
    FAILED_WORKER  a reader ran and reported failure; the source stays visible
    FAILED_TO_READ the runtime could not extract text (needs transcription/failed)
    UNSUPPORTED    binary/metadata-only source; nothing to read
    EMPTY          readable but zero bytes; nothing to catalog, still accounted for
    MAIN_MODEL     SEQUENTIAL strategy: the main model reads it directly, no reader
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from common import StageError, now, read_json, write_json

CONTRACT_VERSION = "1"
READER_ROLE = "LIGHTWEIGHT_SOURCE_READER"
STRATEGIES = ("MULTI_AGENT_PER_SOURCE", "MULTI_AGENT_BATCHED", "SEQUENTIAL")
TASK_STATES = ("PLANNED", "REUSED", "CATALOGED", "FAILED_WORKER", "FAILED_TO_READ", "UNSUPPORTED", "EMPTY",
               "MAIN_MODEL")
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()
# Factual catalog sections a reader may fill; all optional, all lists.
CATALOG_FIELDS = {
    "headings", "identifiers", "actors", "entities", "states", "operations", "integrations",
    "config_facts", "candidate_rules", "flows", "test_assets", "excerpts", "references", "ambiguities",
}
# Decisions that belong to the main model only.
FORBIDDEN_FIELDS = {
    "claims", "tests", "test_cases", "oracles", "findings", "questions", "requirements",
    "coverage", "dispositions", "authority", "role_override", "completeness",
}
RESULT_FIELDS = {"source_key", "path", "content_digest", "role", "status", "reader", "catalog", "error"}


def source_key(path: str) -> str:
    """Deterministic, collision-safe key: a digest of the normalized selected path plus a
    readable suffix. `foo/bar.py` and `foo_bar.py` never share a key."""
    normalized = str(path).replace("\\", "/").strip("/")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "-", normalized.rsplit("/", 1)[-1])[:48] or "source"
    return f"{digest}-{readable}"


def _cache_dir(artifact_root: Path) -> Path:
    return Path(artifact_root) / ".ftd" / "catalog-cache"


def _cache_path(artifact_root: Path, key: str) -> Path:
    return _cache_dir(artifact_root) / f"{key}.json"


def cached_catalog(artifact_root: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """A reusable catalog must match key, digest, role and contract version exactly."""
    path = _cache_path(artifact_root, source_key(record["path"]))
    if not path.is_file():
        return None
    try:
        entry = read_json(path)
    except Exception:
        return None
    if (entry.get("content_digest") == record["content_digest"] and entry.get("role") == record["role"]
            and entry.get("contract_version") == CONTRACT_VERSION and entry.get("status") == "CATALOGED"):
        return entry
    return None


def plan(
    records: list[dict[str, Any]], artifact_root: Path, run_dir: Path, *,
    strategy: str | None = None, worker_model: str | None = None, concurrency: int | None = None,
) -> dict[str, Any]:
    """One logical task per eligible source; reuse a compatible cached catalog instead of
    planning a reader for it. Concurrency is a bound, never a per-task promise."""
    strategy = strategy or "MULTI_AGENT_PER_SOURCE"
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown reading strategy {strategy!r}; expected one of {STRATEGIES}")
    if concurrency is not None and int(concurrency) < 1:
        raise ValueError("reading concurrency must be a positive integer")
    results_dir = run_dir / "reading" / "results"
    tasks = []
    for record in records:
        key = source_key(record["path"])
        task = {"source_key": key, "path": record["path"], "role": record["role"],
                "content_digest": record["content_digest"]}
        if record["status"] in {"METADATA_ONLY", "UNSUPPORTED"}:
            task["state"] = "UNSUPPORTED"
        elif record["status"] not in {"READ", "TRANSCRIBED"}:
            task["state"] = "FAILED_TO_READ"
        elif record["content_digest"] == EMPTY_DIGEST:
            task["state"] = "EMPTY"
        elif strategy == "SEQUENTIAL":
            task["state"] = "MAIN_MODEL"
        else:
            reused = cached_catalog(artifact_root, record)
            if reused:
                results_dir.mkdir(parents=True, exist_ok=True)
                write_json(results_dir / f"{key}.json", {**reused["result"], "reused_from_cache": True})
                task["state"] = "REUSED"
            else:
                task["state"] = "PLANNED"
        tasks.append(task)
    document = {
        "contract_version": CONTRACT_VERSION, "reader_role": READER_ROLE, "strategy": strategy,
        "worker_model": worker_model if strategy != "SEQUENTIAL" else None,
        "concurrency": int(concurrency) if concurrency else None,
        "tasks": tasks, "created_at": now(),
    }
    write_json(run_dir / "reading" / "task-plan.json", document)
    return document


def summary(task_plan: dict[str, Any]) -> dict[str, int]:
    counts = {state: 0 for state in TASK_STATES}
    for task in task_plan["tasks"]:
        counts[task["state"]] += 1
    return counts


def pending(task_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for task in task_plan["tasks"] if task["state"] == "PLANNED"]


def _validate_result(result: dict[str, Any], task: dict[str, Any] | None, line_counts: dict[str, int]) -> list[str]:
    label = f"reader result for {result.get('path') or result.get('source_key') or '<unknown>'}"
    errors = []
    if task is None:
        return [f"{label} names no selected source of this run"]
    extra = sorted(set(result) - RESULT_FIELDS)
    if extra:
        errors.append(f"{label} contains unknown fields {extra}")
    if result.get("content_digest") != task["content_digest"]:
        errors.append(f"{label} was produced for a different revision (digest mismatch)")
    if result.get("role", task["role"]) != task["role"]:
        errors.append(f"{label} tries to change the source role; readers never change authority")
    reader = result.get("reader") if isinstance(result.get("reader"), dict) else {}
    if reader.get("role", READER_ROLE) != READER_ROLE:
        errors.append(f"{label} reader.role must be {READER_ROLE}")
    status = result.get("status")
    if status not in {"CATALOGED", "FAILED"}:
        errors.append(f"{label} status must be CATALOGED or FAILED")
    if status == "FAILED":
        if not str(result.get("error", "")).strip():
            errors.append(f"{label} FAILED requires an error explanation")
        return errors
    catalog = result.get("catalog")
    if not isinstance(catalog, dict) or not any(catalog.get(field) for field in CATALOG_FIELDS):
        errors.append(f"{label} CATALOGED requires a non-empty factual catalog")
        return errors
    forbidden = sorted(set(catalog) & FORBIDDEN_FIELDS)
    if forbidden:
        errors.append(f"{label} catalog contains main-model decisions {forbidden}; readers only catalog facts")
    unknown = sorted(set(catalog) - CATALOG_FIELDS - FORBIDDEN_FIELDS)
    if unknown:
        errors.append(f"{label} catalog contains unknown sections {unknown}")
    total = line_counts.get(task["path"], 0)
    for excerpt in catalog.get("excerpts", []) or []:
        start, end = excerpt.get("line_start"), excerpt.get("line_end", excerpt.get("line_start"))
        if start is not None and not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= total):
            errors.append(f"{label} excerpt {start}-{end} is outside the source ({total} lines)")
    return errors


def submit(run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Record reader results. May be called several times as readers finish; each call is
    validated as a whole and records nothing when any result is invalid."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    by_key = {task["source_key"]: task for task in task_plan["tasks"]}
    by_path = {task["path"]: task for task in task_plan["tasks"]}
    catalog = read_json(run_dir / "evidence" / "source-catalog.json")["sources"]
    line_counts = {entry["path"]: entry["line_count"] or 0 for entry in catalog}
    errors = []
    seen = set()
    for result in results:
        task = by_key.get(result.get("source_key")) or by_path.get(result.get("path"))
        if task is not None:
            if task["source_key"] in seen:
                errors.append(f"reader result for {task['path']} is supplied twice")
            seen.add(task["source_key"])
            if task["state"] not in {"PLANNED", "FAILED_WORKER"}:
                errors.append(f"reader result for {task['path']} not expected in state {task['state']}")
        errors.extend(_validate_result(result, task, line_counts))
    if errors:
        raise StageError("reading", errors)
    results_dir = run_dir / "reading" / "results"
    for result in results:
        task = by_key.get(result.get("source_key")) or by_path[result["path"]]
        stored = {**result, "source_key": task["source_key"], "path": task["path"], "role": task["role"]}
        write_json(results_dir / f"{task['source_key']}.json", stored)
        task["state"] = "CATALOGED" if result["status"] == "CATALOGED" else "FAILED_WORKER"
        if result["status"] == "FAILED":
            task["error"] = str(result["error"])
    write_json(run_dir / "reading" / "task-plan.json", task_plan)
    return {"recorded": len(results), "states": summary(task_plan), "pending": [t["path"] for t in pending(task_plan)]}


def reconcile(run_dir: Path, artifact_root: Path) -> dict[str, Any]:
    """Validate completeness, preserve conflicts, consolidate the catalog and fill the
    reuse cache. Nothing is majority-voted: conflicting statements go to the main model."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    missing = [task["path"] for task in pending(task_plan)]
    if missing:
        raise StageError("reading", [
            f"{len(missing)} selected source(s) have no reader result yet: " + ", ".join(missing[:20])
            + " — submit a CATALOGED or FAILED result for each; no source may silently disappear"
        ])
    results_dir = run_dir / "reading" / "results"
    identifier_statements: dict[str, list[dict[str, str]]] = {}
    references: list[dict[str, str]] = []
    selected_paths = {task["path"] for task in task_plan["tasks"]}
    sources = []
    for task in task_plan["tasks"]:
        entry = {k: task[k] for k in ("source_key", "path", "role", "content_digest", "state")}
        path = results_dir / f"{task['source_key']}.json"
        if task["state"] in {"CATALOGED", "REUSED"}:
            if not path.is_file():
                raise StageError("reading", [f"{task['path']} is {task['state']} but its reader result is missing"])
            result = read_json(path)
            if result.get("content_digest") != task["content_digest"]:
                raise StageError("reading", [f"{task['path']} reader result is stale (digest mismatch)"])
            cat = result.get("catalog", {})
            entry["result_ref"] = f"results/{task['source_key']}.json"
            entry["reader"] = result.get("reader", {})
            for item in cat.get("identifiers", []) or []:
                ident = item.get("identifier") if isinstance(item, dict) else str(item)
                statement = (item.get("title") or item.get("statement") or "") if isinstance(item, dict) else ""
                if ident:
                    identifier_statements.setdefault(ident, []).append({"source": task["path"], "statement": statement})
            for ref in cat.get("references", []) or []:
                target = ref.get("target") if isinstance(ref, dict) else str(ref)
                references.append({"source": task["path"], "target": target,
                                   "selected": target in selected_paths})
            if task["state"] == "CATALOGED":
                cache = _cache_path(artifact_root, task["source_key"])
                write_json(cache, {"contract_version": CONTRACT_VERSION, "path": task["path"],
                                   "role": task["role"], "content_digest": task["content_digest"],
                                   "status": "CATALOGED", "result": result})
        elif task["state"] == "FAILED_WORKER":
            entry["error"] = task.get("error")
        sources.append(entry)
    conflicts = []
    for ident, statements in sorted(identifier_statements.items()):
        distinct = {s["statement"].strip().casefold() for s in statements if s["statement"].strip()}
        if len(distinct) > 1:
            conflicts.append({"identifier": ident, "statements": statements})
    reconciliation = {
        "contract_version": CONTRACT_VERSION, "reconciled_at": now(), "strategy": task_plan["strategy"],
        "worker_model": task_plan.get("worker_model"), "states": summary(task_plan),
        "worker_failures": [s for s in sources if s["state"] == "FAILED_WORKER"],
        "identifier_conflicts": conflicts, "cross_references": references,
        "note": "Conflicts are preserved for the main model; nothing was majority-voted.",
    }
    write_json(run_dir / "reading" / "source-catalog.json", {"sources": sources})
    write_json(run_dir / "reading" / "reconciliation.json", reconciliation)
    return reconciliation

