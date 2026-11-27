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
    REUSED         a compatible file catalog (same key, digest, role, reading policy) was reused
    CATALOGED      a validated reader result exists (a catalog, or INSPECTED with nothing to add)
    FAILED_WORKER  a reader reported failure for this file; it stays visible
    FAILED_TO_READ the runtime could not extract text (needs transcription/failed)
    UNSUPPORTED    binary/metadata-only file; nothing to read
    EMPTY          readable but zero bytes; nothing to catalog, still accounted for
    MAIN_MODEL     SEQUENTIAL strategy: the main model reads its full-text snapshot directly

Native-first reading policy (READING_POLICY): an original whose meaning can lie beyond any
runtime text (PDF, image, office document) is always offered to a reader - in SEQUENTIAL runs
the main model itself, attributed as MAIN_MODEL - and every result of a plan written under the
policy carries a reading declaration: how the original was read (method), whether completely,
what was inspected and what was not seen. A digest proves byte identity, never understanding;
a declaration is the reader's account, which the runtime checks for consistency with what it
knows (format, snapshot, page count) but cannot verify visually. Facts only an image, table or
drawn diagram carries enter as `visual_facts` with a locator; functional authority that has no
runtime text must be transcribed by its native reading before Design.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common import StageError, normalize, normalize_identifier, now, read_json, write_json
from sources import NATIVE_FORMATS, snapshot_kind, source_format

CONTRACT_VERSION = "2"
# The reading policy a plan was written under. Plans and cached catalogs without it predate
# native-first reading: they stay valid for their own runs and are never upgraded silently.
READING_POLICY = "native-first/1"
READER_ROLE = "LIGHTWEIGHT_SOURCE_READER"
MAIN_MODEL_ROLE = "MAIN_MODEL"
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
    "visual_facts",
}
# A visual fact: content only a table, figure, diagram, scan or image of a native-format file
# carries, with the locator a person can find it by. Agent-attested, never runtime-verified.
VISUAL_KINDS = ("table", "figure", "diagram", "chart", "image", "scan", "caption", "footnote", "form", "other")
# Decisions that belong to the main model only.
FORBIDDEN_FIELDS = {
    "claims", "tests", "test_cases", "oracles", "findings", "questions", "requirements",
    "coverage", "dispositions", "authority", "role_override", "completeness",
}
# Roles whose statements about an identifier can compete as definitions. Implementation
# and test code that mention an identifier describe how it is realized: references.
DEFINING_ROLES = {"FUNCTIONAL_AUTHORITY", "TECHNICAL_CONTEXT"}

RESULT_FIELDS = {"source_key", "path", "content_digest", "role", "status", "reader", "catalog", "error", "reading"}
READING_METHODS = {"native", "native_vision", "extracted_text"}
READING_FIELDS = {"method", "tool", "completeness", "inspected", "limitations", "page_count", "transcription"}
COMPLETENESS = ("COMPLETE", "PARTIAL")
# How a file's reading ended, as reconciliation reports it (a label, never a gate).
READING_STATUSES = ("COMPLETE", "PARTIAL", "LEGACY_UNASSESSED", "MAIN_MODEL_FULL_TEXT", "FAILED", "UNSUPPORTED",
                    "EMPTY")
SELECTOR_RESULT_FIELDS = {"selector_id", "selector_path", "role", "reader", "catalog", "files", "shard", "error",
                          "reading"}
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
    """A reusable file catalog must match key, digest, role and the reading policy exactly,
    and carry a valid reading declaration. A catalog cached before native-first reading is
    reused only for a full-text file (its snapshot is the whole original, so nothing visual
    could have been missed); it is then labelled LEGACY_UNASSESSED, never native-complete.
    A PDF, image or document catalog from before the policy is read again. A user-supplied
    transcription that changed (or appeared, or vanished) invalidates the catalog too."""
    path = _cache_path(artifact_root, source_key(record["path"]))
    if not path.is_file():
        return None
    try:
        entry = read_json(path)
    except Exception:
        return None
    if (entry.get("content_digest") != record["content_digest"] or entry.get("role") != record["role"]
            or entry.get("status") != "CATALOGED"):
        return None
    if entry.get("reading_policy") == READING_POLICY:
        if entry.get("transcription_digest") != record.get("transcription_digest"):
            return None
        task = _task_facts(record)
        declared = (entry.get("result") or {}).get("reading")
        if _declaration_errors(declared, task, (entry.get("result") or {}).get("status"), "cached catalog", True):
            return None
        return entry
    if entry.get("contract_version") in {CONTRACT_VERSION, "1"} and _task_facts(record)["snapshot"] == "FULL_TEXT" \
            and _task_facts(record)["format"] not in NATIVE_FORMATS:
        return {**entry, "legacy_unassessed": True}
    return None


def _task_facts(record: dict[str, Any]) -> dict[str, Any]:
    """What the runtime knows about a file's original and snapshot, for a task or a check."""
    fmt = record.get("format") or source_format(record["path"])
    # A task of a plan written before the policy has neither: its snapshot stays unknown (None).
    snapshot = record.get("snapshot") or (snapshot_kind(fmt, record["status"]) if "status" in record else None)
    facts = {"format": fmt, "snapshot": snapshot}
    if record.get("page_count"):
        facts["page_count"] = record["page_count"]
    return facts


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
                "content_digest": record["content_digest"], "selector_id": owner[record["path"]],
                **_task_facts(record), "declaration_required": True}
        for hint in ("native_reading", "extracted_layer", "transcription_digest"):
            if record.get(hint):
                task[hint] = record[hint]
        native = task["format"] in NATIVE_FORMATS
        if native and task["snapshot"] == "NONE" and record["role"] == "FUNCTIONAL_AUTHORITY":
            # No runtime text: its native reading must transcribe it before Design.
            task["transcription_required"] = True
        if record["content_digest"] == EMPTY_DIGEST:
            task["state"] = "EMPTY"
        elif not native and record["status"] in {"METADATA_ONLY", "UNSUPPORTED"}:
            task["state"] = "UNSUPPORTED"
        elif not native and record["status"] not in {"READ", "TRANSCRIBED"}:
            task["state"] = "FAILED_TO_READ"
        elif strategy == "SEQUENTIAL" and not native:
            task["state"] = "MAIN_MODEL"
        else:
            reused = cached_catalog(artifact_root, record)
            if reused:
                results_dir.mkdir(parents=True, exist_ok=True)
                write_json(results_dir / f"{key}.json", {**reused["result"], "reused_from_cache": True})
                task["state"] = "REUSED"
                if reused.get("legacy_unassessed"):
                    task["legacy_unassessed"] = True
            else:
                task["state"] = "PLANNED"
        tasks.append(task)
    document = {
        "contract_version": CONTRACT_VERSION, "reading_policy": READING_POLICY, "reader_role": READER_ROLE,
        "strategy": strategy,
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


def _check_page(item: dict[str, Any], task: dict[str, Any] | None, label: str, errors: list[str]) -> None:
    page = item.get("page")
    if page is None:
        return
    total = (task or {}).get("page_count")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1 or (total and page > total):
        errors.append(f"{label} page {page!r} is not a page of the source" + (f" ({total} pages)" if total else ""))


def _check_catalog(catalog: Any, label: str, errors: list[str], owned: dict[str, int] | None,
                   own_lines: int | None, files: dict[str, dict[str, Any]] | None = None,
                   own_path: str | None = None) -> None:
    if not isinstance(catalog, dict):
        errors.append(f"{label} catalog must be an object")
        return
    forbidden = sorted(set(catalog) & FORBIDDEN_FIELDS)
    if forbidden:
        errors.append(f"{label} catalog contains main-model decisions {forbidden}; readers only catalog facts")
    unknown = sorted(set(catalog) - CATALOG_FIELDS - FORBIDDEN_FIELDS)
    if unknown:
        errors.append(f"{label} catalog contains unknown sections {unknown}")
    files = files or {}
    for section in sorted(CATALOG_FIELDS & set(catalog)):
        for item in catalog.get(section) or []:
            if not isinstance(item, dict):
                if section == "visual_facts":
                    errors.append(f"{label} visual_facts entries must be objects with locator, kind and text")
                continue
            cited = item.get("file")
            if owned is not None and cited is not None and cited not in owned:
                errors.append(f"{label} {section} cites {cited!r}, which this selector does not own")
                continue
            task = files.get(cited or own_path or "")
            if section == "visual_facts":
                if owned is not None and not cited:
                    errors.append(f"{label} visual fact must name its file")
                    continue
                if task is not None and _task_facts(task)["format"] not in NATIVE_FORMATS:
                    errors.append(f"{label} visual fact cites {task['path']}, a text file: cite its lines as an excerpt")
                for field in ("locator", "text"):
                    if not str(item.get(field) or "").strip():
                        errors.append(f"{label} visual fact needs a non-empty {field}")
                if item.get("kind") not in VISUAL_KINDS:
                    errors.append(f"{label} visual fact kind must be one of {list(VISUAL_KINDS)}")
                _check_page(item, task, f"{label} visual fact", errors)
                continue
            if section != "excerpts":
                continue
            total = owned.get(cited) if (owned is not None and cited) else own_lines
            if owned is not None and not cited:
                errors.append(f"{label} excerpt must name its file")
                continue
            _check_page(item, task, f"{label} excerpt", errors)
            start, end = item.get("line_start"), item.get("line_end", item.get("line_start"))
            if start is not None and not (isinstance(start, int) and isinstance(end, int)
                                          and 1 <= start <= end <= (total or 0)):
                errors.append(f"{label} excerpt {start}-{end} is outside the source ({total} lines)")


def _declaration_errors(reading: Any, task: dict[str, Any], status: Any, label: str, required: bool) -> list[str]:
    """Consistency of a reading declaration with what the runtime knows about the file.
    It cannot prove the reader looked; it refuses what is missing, malformed or contradicts the
    format, the snapshot or the page count, so an omission never certifies a complete read."""
    errors: list[str] = []
    if reading is None:
        if required and status != "FAILED":
            errors.append(f"{label} needs a reading declaration: reading = {{method, completeness, inspected, "
                          "limitations} - how the original was read and what was not seen")
        return errors
    if not isinstance(reading, dict) or not reading:
        return [f"{label} reading must be a non-empty object"]
    unknown = sorted(set(reading) - READING_FIELDS)
    if unknown:
        errors.append(f"{label} reading contains unknown fields {unknown}")
    method = reading.get("method")
    if method not in READING_METHODS:
        errors.append(f"{label} reading.method must be one of {sorted(READING_METHODS)}")
    for field in ("limitations", "inspected"):
        value = reading.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            errors.append(f"{label} reading.{field} must be a list of non-empty strings")
    limitations = reading.get("limitations") if isinstance(reading.get("limitations"), list) else []
    completeness = reading.get("completeness")
    if required and completeness not in COMPLETENESS:
        errors.append(f"{label} reading.completeness must be one of {list(COMPLETENESS)}")
    elif completeness is not None and completeness not in COMPLETENESS:
        errors.append(f"{label} reading.completeness must be one of {list(COMPLETENESS)}")
    fmt, snapshot = task.get("format"), task.get("snapshot")
    if method == "extracted_text":
        if snapshot == "NONE":
            errors.append(f"{label} declares extracted_text, but the runtime has no text for this file")
        elif fmt in NATIVE_FORMATS or snapshot != "FULL_TEXT":
            if fmt == "pdf" and not limitations:
                errors.append(f"{label} read a PDF from its text layer only; declare reading.limitations "
                              "(figures, layout and drawn content were not seen)")
            if completeness == "COMPLETE":
                errors.append(f"{label} cannot be COMPLETE from extracted text alone: a text layer or "
                              "transcription is not the whole original")
    if completeness == "PARTIAL" and not limitations:
        errors.append(f"{label} PARTIAL reading must list its limitations")
    if required and status == "INSPECTED" and not reading.get("inspected"):
        errors.append(f"{label} INSPECTED needs reading.inspected: what was looked at before concluding "
                      "there is nothing to catalog")
    if "page_count" in reading:
        declared = reading["page_count"]
        if not isinstance(declared, int) or isinstance(declared, bool) or declared < 1:
            errors.append(f"{label} reading.page_count must be a positive integer")
        elif task.get("page_count") and declared != task["page_count"]:
            errors.append(f"{label} declares {declared} page(s); the original has {task['page_count']}")
    transcription = reading.get("transcription")
    if transcription is not None:
        if not isinstance(transcription, str) or not transcription.strip():
            errors.append(f"{label} reading.transcription must be non-empty text")
        elif snapshot != "NONE":
            errors.append(f"{label} has runtime text ({snapshot}); a transcription only replaces a missing one "
                          "(put visual-only content in visual_facts)")
        elif method not in {"native", "native_vision"}:
            errors.append(f"{label} a transcription comes from reading the original natively")
        if status == "FAILED":
            errors.append(f"{label} FAILED cannot carry a transcription")
    elif task.get("transcription_required") and status != "FAILED" and required:
        errors.append(f"{label} is functional authority with no runtime text: read it natively and put what it "
                      "says in reading.transcription (identifiers and titles verbatim), or report FAILED")
    return errors


def _validate_result(result: dict[str, Any], task: dict[str, Any] | None, line_counts: dict[str, int],
                     strategy: str | None = None, files: dict[str, dict[str, Any]] | None = None) -> list[str]:
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
    # Honest attribution: in a SEQUENTIAL run the main model reads; in a multi-agent run a
    # lightweight reader does, unless the main model read a file itself and says so.
    sequential = strategy == "SEQUENTIAL"
    role = reader.get("role", MAIN_MODEL_ROLE if sequential else READER_ROLE)
    allowed = {MAIN_MODEL_ROLE} if sequential else {READER_ROLE, MAIN_MODEL_ROLE}
    if role not in allowed:
        errors.append(f"{label} reader.role must be {' or '.join(sorted(allowed))}")
    status = result.get("status")
    facts = {**_task_facts(task), **task}
    errors.extend(_declaration_errors(result.get("reading"), facts, status, label,
                                      bool(task.get("declaration_required"))))
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
    _check_catalog(catalog, label, errors, None, line_counts.get(task["path"], 0), files or {task["path"]: facts},
                   task["path"])
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
            item = {"source_key": task["source_key"], "path": task["path"], "reader": reader, **entry}
            # A selector-level declaration is the default only for full-text files (code, markdown):
            # a PDF, image or document under the selector is accounted for with its own declaration.
            if "reading" not in item and result.get("reading") is not None                     and _task_facts(task)["format"] not in NATIVE_FORMATS:
                item["reading"] = result["reading"]
            files.append(item)
        if result.get("catalog"):
            _check_catalog(result["catalog"], label, errors, owned, None, by_path)
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
        errors.extend(_validate_result(result, task, line_counts, task_plan.get("strategy"), by_path))
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
        entry = {
            "contract_version": CONTRACT_VERSION, "path": task["path"], "role": task["role"],
            "content_digest": task["content_digest"], "status": "CATALOGED", "result": result,
            "selector_facts_folded": sum(len(v) for v in folded.values())}
        if task_plan.get("reading_policy"):
            entry["reading_policy"] = task_plan["reading_policy"]
            if task.get("transcription_digest"):
                entry["transcription_digest"] = task["transcription_digest"]
        write_json(_cache_path(artifact_root, task["source_key"]), entry)
        written += 1
    return written


def reading_status(task: dict[str, Any], result: dict[str, Any] | None) -> str:
    """One label per file for reports: how its reading actually ended."""
    state = task["state"]
    if state in {"CATALOGED", "REUSED"}:
        declared = (result or {}).get("reading") or {}
        if task.get("legacy_unassessed") or not declared.get("completeness"):
            return "LEGACY_UNASSESSED"
        return declared["completeness"]
    return {"MAIN_MODEL": "MAIN_MODEL_FULL_TEXT", "FAILED_WORKER": "FAILED", "FAILED_TO_READ": "FAILED",
            "UNSUPPORTED": "UNSUPPORTED", "EMPTY": "EMPTY"}.get(state, state)


def pending_transcriptions(run_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Native transcriptions to adopt as snapshots, and the authority files that still have
    no text at all. Reads only; reconciliation refuses before writing anything when the
    second list is not empty."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    results_dir = run_dir / "reading" / "results"
    adopt, missing = [], []
    for task in task_plan["tasks"]:
        result = read_json(results_dir / f"{task['source_key']}.json") if task["state"] in {"CATALOGED", "REUSED"} \
            and (results_dir / f"{task['source_key']}.json").is_file() else None
        text = ((result or {}).get("reading") or {}).get("transcription")
        if text and task.get("snapshot") == "NONE":
            adopt.append({"path": task["path"], "source_key": task["source_key"], "role": task["role"], "text": text,
                          "method": result["reading"].get("method"), "reader": result.get("reader") or {}})
        elif task.get("transcription_required"):
            missing.append(task["path"])
    return adopt, missing


def reconcile(run_dir: Path, artifact_root: Path, adopt_transcriptions: Any = None) -> dict[str, Any]:
    """Require every physical file under every selector to be accounted for, preserve
    conflicts, build one provenance-preserving catalog per selector and fill the file
    cache. Nothing is majority-voted: conflicting statements go to the main model.

    Functional authority without runtime text must have been transcribed by its native
    reading; `adopt_transcriptions(items)` (the pipeline's) turns those transcriptions into
    run snapshots and re-indexes authority before identifier conflicts are computed. Every
    refusal happens before anything is written."""
    task_plan = read_json(run_dir / "reading" / "task-plan.json")
    missing = [task["path"] for task in pending(task_plan)]
    if missing:
        raise StageError("reading", [
            f"{len(missing)} selected file(s) have no reader disposition yet: " + ", ".join(missing[:20])
            + " — each selector's reader must account for every file it owns; no file may silently disappear"
        ])
    adopt, untranscribed = pending_transcriptions(run_dir)
    if untranscribed:
        raise StageError("reading", [
            f"functional authority with no readable text: {', '.join(untranscribed[:20])} — its native reading must "
            "transcribe it (reading.transcription); a reader that cannot open it reports FAILED, and the user may "
            "supply --transcription on a new run. Design never starts on unread authority."])
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
            if result.get("reading"):
                entry["reading"] = {k: v for k, v in result["reading"].items() if k != "transcription"}
                if result["reading"].get("transcription"):
                    entry["reading"]["transcription_lines"] = len(result["reading"]["transcription"].splitlines())
            entry["reading_status"] = reading_status(task, result)
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
        if "reading_status" not in entry:
            entry["reading_status"] = reading_status(task, None)
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
    # Everything above only read; the first write is the adoption of native transcriptions,
    # which itself validates (re-indexes) in memory before writing.
    transcribed = adopt_transcriptions(adopt) if (adopt and adopt_transcriptions) else []
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
    roles = {t["path"]: t["role"] for t in task_plan["tasks"]}
    visual = []
    for selector in sorted(task_plan.get("selectors") or [], key=lambda s: s["order"]):
        for item in buckets.get(selector["selector_id"], {}).get("visual_facts", []):
            if isinstance(item, dict) and roles.get(item.get("file")) == "FUNCTIONAL_AUTHORITY":
                visual.append({"id": f"VF-{len(visual) + 1:03d}",
                               **{k: item[k] for k in ("file", "locator", "kind", "text", "page") if k in item}})
    partial = [{"path": s["path"], "method": (s.get("reading") or {}).get("method"),
                "limitations": (s.get("reading") or {}).get("limitations", [])}
               for s in sources if s["role"] == "FUNCTIONAL_AUTHORITY" and s.get("reading_status") == "PARTIAL"]
    reading_counts: dict[str, int] = {}
    for s in sources:
        reading_counts[s["reading_status"]] = reading_counts.get(s["reading_status"], 0) + 1
    reconciliation = {
        "contract_version": CONTRACT_VERSION, "reconciled_at": now(), "strategy": task_plan["strategy"],
        "worker_model": task_plan.get("worker_model"), "states": counts, "selectors": selectors_out,
        "worker_failures": [s for s in sources if s["state"] == "FAILED_WORKER"],
        "identifier_conflicts": conflicts, "identifier_references": identifier_references,
        "cross_references": references,
        "reading_policy": task_plan.get("reading_policy"),
        "reading_status": dict(sorted(reading_counts.items())),
        "authority_visual_facts": visual,
        "partial_authority_readings": partial,
        "native_transcriptions": transcribed,
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
