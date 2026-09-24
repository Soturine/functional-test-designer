#!/usr/bin/env python3
"""Default multi-agent source reading: plan, reader results, reconciliation, reuse.

Many lightweight readers read faster; one main model decides. Terms:

    USER SOURCE SELECTOR   what the user selected (a file or a directory)
    PHYSICAL SOURCE FILE   a resolved file owned by exactly one selector
    READER RESPONSIBILITY  one logical reading assignment per selector
    FILE CATALOG           factual evidence for one file (the cache/reuse unit)
    SELECTOR CATALOG       the reconciled factual view of one selector, with file provenance
    GLOBAL RECONCILIATION  cross-selector accounting, conflicts and references

This module owns only the deterministic half: the per-file ledger under every selector,
reader assignments (one per selector, in waves bounded by the concurrency limit), the
validation of reader results, reconciliation before Design, and digest-bound reuse of
file catalogs across runs. It never reads for meaning and never lets a reader decide
claims, oracles, Test Cases, Findings or Questions.

File task states:
    PLANNED        waiting for its selector's reader to account for it
    REUSED         a compatible file catalog (same key, digest, role, contract) was reused
    CATALOGED      a validated reader result exists (a catalog, or INSPECTED with nothing to add)
    FAILED_WORKER  a reader reported failure for this file; it stays visible
    FAILED_TO_READ the runtime could not extract text (needs transcription/failed)
    UNSUPPORTED    binary/metadata-only file; nothing to read
    EMPTY          readable but zero bytes; nothing to catalog, still accounted for
    MAIN_MODEL     SEQUENTIAL strategy: the main model reads it directly, no reader
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common import StageError, normalize, normalize_identifier, now, read_json, write_json

CONTRACT_VERSION = "2"
READER_ROLE = "LIGHTWEIGHT_SOURCE_READER"
STRATEGIES = ("MULTI_AGENT_PER_SOURCE", "MULTI_AGENT_BATCHED", "SEQUENTIAL")
DEFAULT_CONCURRENCY = 8  # host execution default, never business data
TASK_STATES = ("PLANNED", "REUSED", "CATALOGED", "FAILED_WORKER", "FAILED_TO_READ", "UNSUPPORTED", "EMPTY",
               "MAIN_MODEL")
ACCOUNTED = set(TASK_STATES) - {"PLANNED"}
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
# Roles whose statements about an identifier can compete as definitions. Implementation
# and test code that mention an identifier describe how it is realized: references.
DEFINING_ROLES = {"FUNCTIONAL_AUTHORITY", "TECHNICAL_CONTEXT"}

RESULT_FIELDS = {"source_key", "path", "content_digest", "role", "status", "reader", "catalog", "error"}
SELECTOR_RESULT_FIELDS = {"selector_id", "selector_path", "role", "reader", "catalog", "files", "shard", "error"}
FILE_STATUSES = ("CATALOGED", "INSPECTED", "FAILED")


def source_key(path: str) -> str:
    """Deterministic, collision-safe key: a digest of the normalized selected path plus a
    readable suffix. `foo/bar.py` and `foo_bar.py` never share a key."""
    normalized = str(path).replace("\\", "/").strip("/")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "-", normalized.rsplit("/", 1)[-1])[:48] or "source"
    return f"{digest}-{readable}"


def selector_id(path: str) -> str:
    return "S" + source_key(path)


def _cache_path(artifact_root: Path, key: str) -> Path:
    return Path(artifact_root) / ".ftd" / "catalog-cache" / f"{key}.json"


def cached_catalog(artifact_root: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """A reusable file catalog must match key, digest, role and contract version exactly.
    Contract 1 file results are the same per-file shape and stay reusable."""
    path = _cache_path(artifact_root, source_key(record["path"]))
    if not path.is_file():
        return None
    try:
        entry = read_json(path)
    except Exception:
        return None
    if (entry.get("content_digest") == record["content_digest"] and entry.get("role") == record["role"]
            and entry.get("contract_version") in {CONTRACT_VERSION, "1"} and entry.get("status") == "CATALOGED"):
        return entry
    return None


def _selector_entries(records: list[dict[str, Any]], selectors: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Selectors with ids and their owned files; without selectors each file is its own."""
    if not selectors:
        selectors = [{"path": r["path"], "role": r["role"], "files": [r["path"]]} for r in records]
    known = {r["path"] for r in records}
    entries, owned = [], set()
    for order, selector in enumerate(selectors):
        files = [path for path in selector["files"] if path in known and path not in owned]
        owned.update(files)
        entries.append({"selector_id": selector_id(selector["path"]), "path": selector["path"],
                        "role": selector["role"], "order": order, "files": files})
    orphans = sorted(known - owned)
    if orphans:
        raise ValueError("physical files without an owning selector: " + ", ".join(orphans[:20]))
    return entries


def _selector_view(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: e[k] for k in ("selector_id", "path", "role", "order")}
            | {"files": [source_key(p) for p in e["files"]]} for e in entries]


def selector_view(records: list[dict[str, Any]], selectors: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The deterministic selector structure (path, role, order, owned file keys) a plan
    records; comparing it tells whether a resumed request still reads the same way."""
    return _selector_view(_selector_entries(records, selectors))


def plan(
    records: list[dict[str, Any]], artifact_root: Path, run_dir: Path, *,
    selectors: list[dict[str, Any]] | None = None,
    strategy: str | None = None, worker_model: str | None = None, concurrency: int | None = None,
) -> dict[str, Any]:
    """Per-file ledger under each user-declared selector. One reader responsibility per
    selector; a compatible cached file catalog is reused instead of being read again."""
    strategy = strategy or "MULTI_AGENT_PER_SOURCE"
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown reading strategy {strategy!r}; expected one of {STRATEGIES}")
    if concurrency is not None and int(concurrency) < 1:
        raise ValueError("reading concurrency must be a positive integer")
    entries = _selector_entries(records, selectors)
    owner = {path: e["selector_id"] for e in entries for path in e["files"]}
    results_dir = run_dir / "reading" / "results"
    tasks = []
    for record in records:
        key = source_key(record["path"])
        task = {"source_key": key, "path": record["path"], "role": record["role"],
                "content_digest": record["content_digest"], "selector_id": owner[record["path"]]}
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
        "concurrency": None if strategy == "SEQUENTIAL" else int(concurrency or DEFAULT_CONCURRENCY),
        "selectors": _selector_view(entries), "tasks": tasks, "history": [], "created_at": now(),
    }
    write_json(run_dir / "reading" / "task-plan.json", document)
    return document


def attach_selectors(run_dir: Path, records: list[dict[str, Any]], selectors: list[dict[str, Any]], *,
                     strategy: str | None = None) -> dict[str, Any]:
    """Upgrade a plan written before selector ownership existed, preserving every task
    state and recorded result. The initial strategy stays in the history; nothing is re-read."""
    path = run_dir / "reading" / "task-plan.json"
    task_plan = read_json(path)
    if task_plan.get("selectors"):
        return task_plan
    entries = _selector_entries(records, selectors)
    owner = {p: e["selector_id"] for e in entries for p in e["files"]}
    for task in task_plan["tasks"]:
        task["selector_id"] = owner[task["path"]]
    task_plan["selectors"] = _selector_view(entries)
    # The plan now carries selector ownership, so it is a current-contract plan. The
    # contract it was written under stays in the history; its per-file results keep the
    # same shape and stay valid.
    task_plan.setdefault("history", []).append({
        "event": "SELECTOR_OWNERSHIP_ATTACHED", "at": now(), "initial_strategy": task_plan["strategy"],
        "initial_contract_version": task_plan.get("contract_version"), "contract_version": CONTRACT_VERSION,
        "states_at_migration": summary(task_plan),
    })
    task_plan["contract_version"] = CONTRACT_VERSION
    if strategy:
        task_plan["strategy"] = strategy
    if task_plan.get("strategy") != "SEQUENTIAL" and not task_plan.get("concurrency"):
        task_plan["concurrency"] = DEFAULT_CONCURRENCY
    write_json(path, task_plan)
    return task_plan


def apply_preferences(run_dir: Path, reading: dict[str, Any] | None,
                      provenance: dict[str, str] | None = None) -> dict[str, Any]:
    """Apply the current request's reading preferences (strategy, worker_model,
    concurrency) to a resumed plan that still has reading to do. A stated current value
    wins over the stored plan; unstated values keep the plan's. Every change is recorded
    in the history with its provenance. Switching to or from SEQUENTIAL mid-reading is
    refused: it changes who reads, which needs a new run."""
    path = run_dir / "reading" / "task-plan.json"
    task_plan = read_json(path)
    wanted = {key: value for key, value in (reading or {}).items()
              if key in {"strategy", "worker_model", "concurrency"} and value not in (None, "")}
    if "strategy" in wanted and wanted["strategy"] not in STRATEGIES:
        raise ValueError(f"unknown reading strategy {wanted['strategy']!r}; expected one of {STRATEGIES}")
    if "concurrency" in wanted:
        if int(wanted["concurrency"]) < 1:
            raise ValueError("reading concurrency must be a positive integer")
        wanted["concurrency"] = int(wanted["concurrency"])
    current = task_plan.get("strategy")
    if "strategy" in wanted and wanted["strategy"] != current and "SEQUENTIAL" in {wanted["strategy"], current}:
        raise StageError("reading", [
            f"this run reads with {current}; switching to {wanted['strategy']} while reading changes who reads — "
            "start a new run id (compatible file catalogs are reused)"])
    changes = {key: {"from": task_plan.get(key), "to": value, "provenance": (provenance or {}).get(f"reading.{key}", "EXPLICIT")}
               for key, value in wanted.items() if task_plan.get(key) != value}
    if changes:
        for key, change in changes.items():
            task_plan[key] = change["to"]
        task_plan.setdefault("history", []).append({"event": "READING_PREFERENCES_APPLIED", "at": now(),
                                                    "changes": changes})
        write_json(path, task_plan)
    return task_plan


def summary(task_plan: dict[str, Any]) -> dict[str, int]:
    counts = {state: 0 for state in TASK_STATES}
    for task in task_plan["tasks"]:
        counts[task["state"]] += 1
    return counts


def pending(task_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for task in task_plan["tasks"] if task["state"] == "PLANNED"]


def assignments(task_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """One reader responsibility per selector that still has unaccounted files, queued in
    waves of at most `concurrency` concurrently active readers, in declared order."""
    limit = int(task_plan.get("concurrency") or 1)
    out = []
    for selector in sorted(task_plan.get("selectors") or [], key=lambda s: s["order"]):
        files = [t for t in task_plan["tasks"] if t.get("selector_id") == selector["selector_id"]]
        todo = [t for t in files if t["state"] == "PLANNED"]
        if not todo:
            continue
        out.append({"selector_id": selector["selector_id"], "selector_path": selector["path"],
                    "role": selector["role"], "wave": len(out) // limit + 1, "files_total": len(files),
                    "files_pending": todo, "files_already_accounted": len(files) - len(todo)})
    return out


def _check_catalog(catalog: Any, label: str, errors: list[str], owned: dict[str, int] | None,
                   own_lines: int | None) -> None:
    if not isinstance(catalog, dict):
        errors.append(f"{label} catalog must be an object")
        return
    forbidden = sorted(set(catalog) & FORBIDDEN_FIELDS)
    if forbidden:
        errors.append(f"{label} catalog contains main-model decisions {forbidden}; readers only catalog facts")
    unknown = sorted(set(catalog) - CATALOG_FIELDS - FORBIDDEN_FIELDS)
    if unknown:
        errors.append(f"{label} catalog contains unknown sections {unknown}")
    for section in sorted(CATALOG_FIELDS & set(catalog)):
        for item in catalog.get(section) or []:
            if not isinstance(item, dict):
                continue
            cited = item.get("file")
            if owned is not None and cited is not None and cited not in owned:
                errors.append(f"{label} {section} cites {cited!r}, which this selector does not own")
                continue
            if section != "excerpts":
                continue
            total = owned.get(cited) if (owned is not None and cited) else own_lines
            if owned is not None and not cited:
                errors.append(f"{label} excerpt must name its file")
                continue
            start, end = item.get("line_start"), item.get("line_end", item.get("line_start"))
            if start is not None and not (isinstance(start, int) and isinstance(end, int)
                                          and 1 <= start <= end <= (total or 0)):
                errors.append(f"{label} excerpt {start}-{end} is outside the source ({total} lines)")


def _validate_result(result: dict[str, Any], task: dict[str, Any] | None, line_counts: dict[str, int]) -> list[str]:
    label = f"reader result for {result.get('path') or result.get('source_key') or '<unknown>'}"
    errors: list[str] = []
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
    if status not in FILE_STATUSES:
        errors.append(f"{label} status must be one of {list(FILE_STATUSES)}")
    if status == "FAILED":
        if not str(result.get("error", "")).strip():
            errors.append(f"{label} FAILED requires an error explanation")
        return errors
    if status == "INSPECTED":
        if result.get("catalog"):
            errors.append(f"{label} INSPECTED means read with nothing to add; facts belong under CATALOGED")
        return errors
    catalog = result.get("catalog")
    if not isinstance(catalog, dict) or not any(catalog.get(field) for field in CATALOG_FIELDS):
        errors.append(f"{label} CATALOGED requires a non-empty factual catalog")
        return errors
    _check_catalog(catalog, label, errors, None, line_counts.get(task["path"], 0))
    return errors


def _expand(results: list[dict[str, Any]], task_plan: dict[str, Any], line_counts: dict[str, int],
            errors: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split selector results into per-file results (the accounting and cache unit) and
    selector-level catalogs. Plain per-file results pass through unchanged."""
    by_key = {t["source_key"]: t for t in task_plan["tasks"]}
    by_path = {t["path"]: t for t in task_plan["tasks"]}
    selectors = {s["selector_id"]: s for s in task_plan.get("selectors") or []}
    files, selector_catalogs = [], []
    for result in results:
        if "selector_id" not in result:
            files.append(result)
            continue
        sid = result.get("selector_id")
        selector = selectors.get(sid)
        label = f"selector result {sid}"
        if selector is None:
            errors.append(f"{label} names no selector of this run")
            continue
        extra = sorted(set(result) - SELECTOR_RESULT_FIELDS)
        if extra:
            errors.append(f"{label} contains unknown fields {extra}")
        if result.get("role", selector["role"]) != selector["role"]:
            errors.append(f"{label} tries to change the selector role; readers never change authority")
        owned = {by_key[k]["path"]: line_counts.get(by_key[k]["path"], 0) for k in selector["files"]}
        reader = result.get("reader") if isinstance(result.get("reader"), dict) else {}
        for entry in result.get("files") or []:
            task = by_key.get(entry.get("source_key")) or by_path.get(entry.get("path"))
            if task is None or task.get("selector_id") != sid:
                errors.append(f"{label} accounts for {entry.get('path') or entry.get('source_key')!r}, "
                              "which this selector does not own")
                continue
            files.append({"source_key": task["source_key"], "path": task["path"], "reader": reader, **entry})
        if result.get("catalog"):
            _check_catalog(result["catalog"], label, errors, owned, None)
            selector_catalogs.append({"selector_id": sid, "shard": result.get("shard"), "reader": reader,
                                      "catalog": result["catalog"]})
    return files, selector_catalogs


def submit(run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Record reader results — per selector (with its file accounting) or per file. May be
    called several times (e.g. once per internal shard); each call is validated as a whole
    and records nothing when any part is invalid."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    by_key = {task["source_key"]: task for task in task_plan["tasks"]}
    by_path = {task["path"]: task for task in task_plan["tasks"]}
    catalog = read_json(run_dir / "evidence" / "source-catalog.json")["sources"]
    line_counts = {entry["path"]: entry["line_count"] or 0 for entry in catalog}
    errors: list[str] = []
    files, selector_catalogs = _expand(results, task_plan, line_counts, errors)
    seen = set()
    for result in files:
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
    for result in files:
        task = by_key.get(result.get("source_key")) or by_path[result["path"]]
        stored = {**result, "source_key": task["source_key"], "path": task["path"], "role": task["role"]}
        write_json(results_dir / f"{task['source_key']}.json", stored)
        task["state"] = "FAILED_WORKER" if result["status"] == "FAILED" else "CATALOGED"
        if result["status"] == "FAILED":
            task["error"] = str(result["error"])
    for item in selector_catalogs:
        folder = run_dir / "reading" / "selector-results" / item["selector_id"]
        folder.mkdir(parents=True, exist_ok=True)
        write_json(folder / f"{len(list(folder.glob('*.json'))) + 1:03d}.json", item)
    write_json(run_dir / "reading" / "task-plan.json", task_plan)
    return {"recorded": len(files), "selector_catalogs": len(selector_catalogs), "states": summary(task_plan),
            "pending": [t["path"] for t in pending(task_plan)]}


def _item_key(item: Any) -> str:
    """Deterministic identity of one catalog item: its full content with whitespace
    collapsed. Only exact restatements collapse; similar but distinct facts survive."""
    def canonical(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return " ".join(value.split()) if isinstance(value, str) else value
    return json.dumps(canonical(item), sort_keys=True, ensure_ascii=False)


def _dedupe(bucket: dict[str, list[Any]]) -> tuple[dict[str, list[Any]], int]:
    """A selector catalog is an index over its files: a fact that both a file result and
    the selector-level result restate appears once, with its file provenance."""
    removed, out = 0, {}
    for section, items in bucket.items():
        seen, kept = set(), []
        for item in items:
            key = _item_key(item)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(item)
        out[section] = kept
    return out, removed


def identifier_conflicts(statements: dict[str, list[dict[str, str]]], official: dict[str, dict[str, str]]
                         ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split identifier statements into genuine definition conflicts and references.

    A conflict needs an official identifier (from the Functional Authority index, when
    one exists) stated by two different sources of defining roles (authority or
    technical context) in ways that do not agree; one statement containing the other
    agrees. The authority index's own title takes part for its source. Implementation
    and test mentions are references to how the identifier is realized, and identifiers
    outside the authority universe never enter the conflict list."""
    def agree(left: str, right: str) -> bool:
        return left in right or right in left

    conflicts, references = [], []
    for ident, items in sorted(statements.items()):
        key = normalize_identifier(ident)
        if official and key not in official:
            continue
        defining = [s for s in items if s.get("role") in DEFINING_ROLES and normalize(s.get("statement"))]
        references.extend({"identifier": ident, **s} for s in items if s.get("role") not in DEFINING_ROLES)
        if key in official and official[key].get("title"):
            defining = [{"source": official[key]["source"], "statement": official[key]["title"],
                         "role": "FUNCTIONAL_AUTHORITY", "authority_index": True}, *defining]
        clash = any(a["source"] != b["source"] and not agree(normalize(a["statement"]), normalize(b["statement"]))
                    for i, a in enumerate(defining) for b in defining[i + 1:])
        if clash:
            conflicts.append({"identifier": ident, "statements": defining})
    return conflicts, references


def _official_identifiers(run_dir: Path) -> dict[str, dict[str, str]]:
    path = run_dir / "sources.json"
    if not path.is_file():
        return {}
    return {normalize_identifier(item["identifier"]): {"title": item.get("title") or "", "source": item.get("source", "")}
            for item in read_json(path).get("authority_index", [])}


def _with_file(items: list[Any], path: str) -> list[Any]:
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append(item if "file" in item else {"file": path, **item})
        else:
            out.append({"file": path, "fact": item})
    return out


def _selector_facts_by_file(run_dir: Path) -> dict[str, dict[str, list[Any]]]:
    """Selector-level catalog items grouped by the file they cite."""
    by_file: dict[str, dict[str, list[Any]]] = {}
    for item_path in sorted((run_dir / "reading" / "selector-results").glob("*/*.json")):
        for section, values in (read_json(item_path).get("catalog") or {}).items():
            for value in values or []:
                if isinstance(value, dict) and value.get("file"):
                    by_file.setdefault(value["file"], {}).setdefault(section, []).append(value)
    return by_file


def refresh_file_cache(run_dir: Path, artifact_root: Path) -> int:
    """Write the reusable file catalog of every file this run's readers recorded. Facts a
    reader put in its selector-level result are folded into the catalog of the file they
    cite, so reusing file catalogs later loses nothing a reader reported. Reads the run,
    writes only the artifact root's catalog cache; the run itself is not modified."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    selector_facts = _selector_facts_by_file(run_dir)
    written = 0
    for task in task_plan["tasks"]:
        if task["state"] != "CATALOGED":
            continue
        result = dict(read_json(run_dir / "reading" / "results" / f"{task['source_key']}.json"))
        folded = selector_facts.get(task["path"], {})
        if folded:
            catalog: dict[str, list[Any]] = {}
            for section, items in (result.get("catalog") or {}).items():
                catalog[section] = _with_file(items, task["path"])
            for section, items in folded.items():
                catalog.setdefault(section, []).extend(items)
            result["catalog"], _ = _dedupe(catalog)
            if result.get("status") == "INSPECTED" and any(result["catalog"].values()):
                result["status"] = "CATALOGED"
        write_json(_cache_path(artifact_root, task["source_key"]), {
            "contract_version": CONTRACT_VERSION, "path": task["path"], "role": task["role"],
            "content_digest": task["content_digest"], "status": "CATALOGED", "result": result,
            "selector_facts_folded": sum(len(v) for v in folded.values())})
        written += 1
    return written


def reconcile(run_dir: Path, artifact_root: Path) -> dict[str, Any]:
    """Require every physical file under every selector to be accounted for, preserve
    conflicts, build one provenance-preserving catalog per selector and fill the file
    cache. Nothing is majority-voted: conflicting statements go to the main model."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    missing = [task["path"] for task in pending(task_plan)]
    if missing:
        raise StageError("reading", [
            f"{len(missing)} selected file(s) have no reader disposition yet: " + ", ".join(missing[:20])
            + " — each selector's reader must account for every file it owns; no file may silently disappear"
        ])
    results_dir = run_dir / "reading" / "results"
    identifier_statements: dict[str, list[dict[str, str]]] = {}
    references: list[dict[str, Any]] = []
    selected_paths = {task["path"] for task in task_plan["tasks"]}
    sources, models = [], set()
    buckets: dict[str, dict[str, list[Any]]] = {}
    for task in task_plan["tasks"]:
        entry = {k: task[k] for k in ("source_key", "path", "role", "content_digest", "state")}
        entry["selector_id"] = task.get("selector_id")
        path = results_dir / f"{task['source_key']}.json"
        if task["state"] in {"CATALOGED", "REUSED"}:
            if not path.is_file():
                raise StageError("reading", [f"{task['path']} is {task['state']} but its reader result is missing"])
            result = read_json(path)
            if result.get("content_digest") != task["content_digest"]:
                raise StageError("reading", [f"{task['path']} reader result is stale (digest mismatch)"])
            cat = result.get("catalog") or {}
            entry.update({"result_ref": f"results/{task['source_key']}.json", "reader": result.get("reader", {}),
                          "disposition": result.get("status")})
            if (result.get("reader") or {}).get("model"):
                models.add(str(result["reader"]["model"]))
            bucket = buckets.setdefault(task.get("selector_id") or task["source_key"], {})
            for section in sorted(CATALOG_FIELDS):
                if cat.get(section):
                    bucket.setdefault(section, []).extend(_with_file(cat[section], task["path"]))
            for item in cat.get("identifiers", []) or []:
                ident = item.get("identifier") if isinstance(item, dict) else str(item)
                statement = (item.get("title") or item.get("statement") or "") if isinstance(item, dict) else ""
                if ident:
                    identifier_statements.setdefault(ident, []).append(
                        {"source": task["path"], "statement": statement, "role": task["role"]})
            for ref in cat.get("references", []) or []:
                target = ref.get("target") if isinstance(ref, dict) else str(ref)
                references.append({"source": task["path"], "target": target, "selected": target in selected_paths})
        elif task["state"] == "FAILED_WORKER":
            entry["error"] = task.get("error")
        sources.append(entry)
    shards: dict[str, int] = {}
    for folder in sorted((run_dir / "reading" / "selector-results").glob("*")):
        for item_path in sorted(folder.glob("*.json")):
            item = read_json(item_path)
            shards[folder.name] = shards.get(folder.name, 0) + 1
            if (item.get("reader") or {}).get("model"):
                models.add(str(item["reader"]["model"]))
            bucket = buckets.setdefault(folder.name, {})
            for section, values in sorted((item.get("catalog") or {}).items()):
                bucket.setdefault(section, []).extend(values or [])
    duplicates_removed = 0
    for sid in list(buckets):
        buckets[sid], removed = _dedupe(buckets[sid])
        duplicates_removed += removed
    selectors_out = []
    for selector in task_plan.get("selectors") or []:
        files = [t for t in task_plan["tasks"] if t.get("selector_id") == selector["selector_id"]]
        states: dict[str, int] = {}
        for t in files:
            states[t["state"]] = states.get(t["state"], 0) + 1
        catalog_ref = f"selector-catalogs/{selector['selector_id']}.json"
        write_json(run_dir / "reading" / catalog_ref, {
            "selector_id": selector["selector_id"], "path": selector["path"], "role": selector["role"],
            "files": [t["path"] for t in files], "catalog": buckets.get(selector["selector_id"], {})})
        selectors_out.append({"selector_id": selector["selector_id"], "path": selector["path"],
                              "role": selector["role"], "files_total": len(files), "file_states": states,
                              "complete": all(t["state"] in ACCOUNTED for t in files),
                              "selector_level_results": shards.get(selector["selector_id"], 0),
                              "catalog_ref": catalog_ref})
    conflicts, identifier_references = identifier_conflicts(identifier_statements, _official_identifiers(run_dir))
    counts = summary(task_plan)
    reconciliation = {
        "contract_version": CONTRACT_VERSION, "reconciled_at": now(), "strategy": task_plan["strategy"],
        "worker_model": task_plan.get("worker_model"), "states": counts, "selectors": selectors_out,
        "worker_failures": [s for s in sources if s["state"] == "FAILED_WORKER"],
        "identifier_conflicts": conflicts, "identifier_references": identifier_references,
        "cross_references": references,
        "telemetry": {
            "user_source_selectors": len(task_plan.get("selectors") or []),
            "physical_files_selected": len(task_plan["tasks"]),
            "reader_concurrency_limit": task_plan.get("concurrency"),
            "reader_model_requested": task_plan.get("worker_model"),
            "reader_models_reported": sorted(models),
            "reader_model_host_verified": None,  # a reader's own claim is not host verification
            "file_catalogs_reused": counts["REUSED"], "file_results_recorded": counts["CATALOGED"],
            "failed_reader_files": counts["FAILED_WORKER"], "empty_files": counts["EMPTY"],
            "unsupported_files": counts["UNSUPPORTED"] + counts["FAILED_TO_READ"],
            "unaccounted_files": counts["PLANNED"],
            "internal_shards_used": {sid: n for sid, n in shards.items() if n > 1},
            "duplicate_catalog_items_removed": duplicates_removed,
            "history": task_plan.get("history", []),
        },
        "note": "Conflicts are preserved for the main model; nothing was majority-voted.",
    }
    reconciliation["telemetry"]["file_catalogs_cached"] = refresh_file_cache(run_dir, artifact_root)
    write_json(run_dir / "reading" / "source-catalog.json", {"sources": sources})
    write_json(run_dir / "reading" / "reconciliation.json", reconciliation)
    return reconciliation
