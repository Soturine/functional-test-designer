#!/usr/bin/env python3
"""FTD ADR: maintain a validated Test Case suite incrementally as ADRs and other approved
project decisions arrive — without regenerating the suite or rereading the original sources.

    current validated canonical run (+ the latest finalized ADR round of that run)
        + the selected ADR file or folder (only new or changed files are read)
        -> analysis (you)    source classification, decision ledger, relationship to the existing
                             authority, affected Test Cases, targeted expansion, Questions, Findings
        -> procedures (you)  complete executable procedures for every UPDATE / CREATE
        -> finalize (runtime) ADR validation, effective suite, ADR report, local Azure ADR delta

The runtime owns scope, inventory, digests, ids, lineage, validation and publication; the model
owns the reasoning. Nothing here edits the parent canonical run: every ADR round lives in its own
`<run>/adr/<adr-id>/` folder, and `.ftd/current-adr.json` names, per canonical run, the latest
FINALIZED round (written atomically, only by finalize). `.ftd/current-run.json` keeps meaning the
current validated canonical run. A round is STARTED -> ANALYZED -> PROCEDURES_READY -> FINALIZED;
a rejected submission records nothing, and a finalized round is immutable — a mistake is fixed by
a new round, never by editing history. Nothing here authenticates or talks to Azure.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import file_digest, now, read_json, stable_digest, write_json  # noqa: E402
import pipeline  # noqa: E402
import sources  # noqa: E402

ADR_FOLDER = "adr"
POINTER_FILE = "current-adr.json"
ROUND_FILE = "adr-run.json"
ROUND_ID = re.compile(r"^adr-(\d{3,})$")
STATES = ("STARTED", "ANALYZED", "PROCEDURES_READY", "FINALIZED")
SOURCE_DISPOSITIONS = ("NEW_READ", "CHANGED_READ", "UNCHANGED_REUSED", "UNSUPPORTED", "FAILED",
                       "SOURCE_REMOVED_FROM_SELECTION")
READABLE = {"NEW_READ", "CHANGED_READ"}


class AdrError(ValueError):
    """An ADR action whose preconditions do not hold. ADR state is never trusted on failure."""


# --- the parent canonical run ----------------------------------------------------------

def resolve_canonical(run: Any = None, artifact_root: Any = None) -> Path:
    """explicit --run > the current validated canonical run (`.ftd/current-run.json`) > an error.
    Either way the run must be VALIDATED, with an intact manifest and canonical fingerprint —
    the same checks the current-run pointer gets, applied to an explicit run too."""
    run_dir = pipeline.resolve_run(run, artifact_root)
    verify_canonical(run_dir)
    return run_dir


def verify_canonical(run_dir: Path) -> dict[str, Any]:
    try:
        if pipeline._state(run_dir).get("status") != "VALIDATED":
            raise AdrError(f"{run_dir.name} is not a VALIDATED canonical run; finalize it before an ADR round")
        pipeline.verify_manifest(run_dir / "run-manifest.json", require_publication=False)
        return pipeline.read_canonical(run_dir / "canonical-suite.json")
    except AdrError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise AdrError(f"the canonical run {run_dir.name} cannot be trusted: {exc}") from exc


def parent_snapshot(run_dir: Path) -> dict[str, str]:
    """Digest of every file of the parent run that ADR must never touch. Its own `adr/` folder,
    post-suite chaos runs and the publisher's integration state are separate, owned state."""
    owned = {ADR_FOLDER, "challenges", "integration-state"}
    return {p.relative_to(run_dir).as_posix(): file_digest(p) for p in sorted(run_dir.rglob("*"))
            if p.is_file() and p.relative_to(run_dir).parts[0] not in owned}


# --- effective state -------------------------------------------------------------------

def effective_digest(document: dict[str, Any]) -> str:
    return stable_digest({k: v for k, v in document.items() if k not in {"effective_digest", "finalized_at"}})


def case_digest(case: dict[str, Any]) -> str:
    return stable_digest(case)


def canonical_effective(run_dir: Path, canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    """The effective state before any ADR round: the canonical suite itself, read-only."""
    canonical = canonical or verify_canonical(run_dir)
    document = {
        "schema_version": "1", "kind": "FTD_ADR_EFFECTIVE_SUITE",
        "parent": {"run_id": run_dir.name, "canonical_digest": canonical["semantic_fingerprint"]},
        "adr_run_id": None, "previous_adr_id": None, "previous_effective_digest": None, "lineage": [],
        "output_locale": canonical["index"].get("output_locale") or "en",
        "requirements": copy.deepcopy(canonical["index"]["requirements"]),
        "cases": copy.deepcopy(canonical["cases"]),
        "case_states": {case["id"]: {"state": "ACTIVE", "origin": "CANONICAL", "export_key": f"canonical:{case['id']}",
                                     "created_by": None, "last_changed_by": None}
                        for case in canonical["cases"]},
        "coverage_points": copy.deepcopy(canonical["index"].get("coverage_points", [])),
        "scenarios": copy.deepcopy(canonical["index"].get("scenarios", [])),
        "questions": copy.deepcopy(canonical["questions"]["questions"]),
        "findings": copy.deepcopy(canonical["index"]["findings"]),
        "question_dispositions": {}, "finding_dispositions": {},
        "decisions": [], "sources": {}, "case_history": {}, "adr_requirements": [],
    }
    document["effective_digest"] = effective_digest(document)
    return document


def _round_dir(run_dir: Path, adr_id: str) -> Path:
    if not ROUND_ID.match(str(adr_id or "")):
        raise AdrError(f"{adr_id!r} is not an ADR round id (adr-NNN)")
    return Path(run_dir) / ADR_FOLDER / adr_id


def _round(round_dir: Path) -> dict[str, Any]:
    path = round_dir / ROUND_FILE
    if not path.is_file():
        raise AdrError(f"ADR round {round_dir.name} does not exist")
    return read_json(path)


def load_effective(run_dir: Path, adr_id: str, canonical: dict[str, Any] | None = None, _seen: set | None = None
                   ) -> dict[str, Any]:
    """A FINALIZED round's effective state, after checking its manifest, its digest, its parent
    canonical digest and, recursively, every earlier round it builds on. Fails closed."""
    canonical = canonical or verify_canonical(run_dir)
    seen = _seen or set()
    if adr_id in seen:
        raise AdrError(f"ADR lineage loops at {adr_id}")
    seen.add(adr_id)
    round_dir = _round_dir(run_dir, adr_id)
    lineage = _round(round_dir)
    if lineage.get("status") != "FINALIZED":
        raise AdrError(f"ADR round {adr_id} is {lineage.get('status')}, not FINALIZED; it is not effective state")
    verify_round_manifest(round_dir)
    document = read_json(round_dir / "effective-suite.json")
    if document.get("effective_digest") != effective_digest(document) or \
            document["effective_digest"] != lineage.get("effective_digest"):
        raise AdrError(f"ADR round {adr_id} effective state does not match its recorded digest")
    if document["parent"]["canonical_digest"] != canonical["semantic_fingerprint"] or \
            lineage.get("parent_canonical_digest") != canonical["semantic_fingerprint"]:
        raise AdrError(f"ADR round {adr_id} was built on another canonical suite than {run_dir.name}'s current one")
    previous = lineage.get("previous_adr_id")
    if previous:
        before = load_effective(run_dir, previous, canonical, seen)
        if before["effective_digest"] != lineage.get("previous_effective_digest"):
            raise AdrError(f"ADR round {adr_id} no longer matches the state of {previous} it was built on")
    elif lineage.get("previous_effective_digest") != canonical_effective(run_dir, canonical)["effective_digest"]:
        raise AdrError(f"ADR round {adr_id} no longer matches the canonical state it was built on")
    return document


def verify_round_manifest(round_dir: Path) -> dict[str, Any]:
    path = round_dir / "adr-manifest.json"
    if not path.is_file():
        raise AdrError(f"ADR round {round_dir.name} has no manifest")
    manifest = read_json(path)
    for name, digest in manifest["files"].items():
        target = round_dir / name
        if not target.is_file() or file_digest(target) != digest:
            raise AdrError(f"ADR round {round_dir.name}: {name} changed after it was finalized")
    return manifest


def _pointer_path(run_dir: Path) -> Path:
    artifact_root = Path(read_json(Path(run_dir) / "run.json")["artifact_root"])
    return artifact_root / ".ftd" / POINTER_FILE


def current_adr(run_dir: Path) -> str | None:
    """The latest finalized round recorded for this canonical run, or None. A recorded entry
    that does not verify is an error, never a silent fallback to the canonical state."""
    path = _pointer_path(run_dir)
    if not path.is_file():
        return None
    try:
        entry = read_json(path)["lineages"].get(Path(run_dir).name)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        raise AdrError(f"{path} is corrupt ({exc}); repair or remove it, or pass --base-adr explicitly") from exc
    if not entry:
        return None
    return entry["adr_run_id"]


def resolve_base(run_dir: Path, base_adr: str | None = None) -> dict[str, Any]:
    """The effective state a new round builds on: --base-adr (an id, or `none` for the canonical
    suite) > the current finalized round of this canonical run > the canonical suite."""
    canonical = verify_canonical(run_dir)
    if base_adr in ("none", "canonical"):
        return canonical_effective(run_dir, canonical)
    adr_id = base_adr or current_adr(run_dir)
    if not adr_id:
        return canonical_effective(run_dir, canonical)
    document = load_effective(run_dir, adr_id, canonical)
    if not base_adr:
        entry = read_json(_pointer_path(run_dir))["lineages"][run_dir.name]
        if entry.get("effective_digest") != document["effective_digest"] or \
                entry.get("canonical_digest") != canonical["semantic_fingerprint"]:
            raise AdrError(f"{_pointer_path(run_dir)} does not match ADR round {adr_id}; pass --base-adr explicitly")
    return document


def mark_current_adr(run_dir: Path, adr_id: str, document: dict[str, Any]) -> Path:
    """Atomic: a reader sees the previous pointer or the new one, never a half-written file."""
    path = _pointer_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_json(path) if path.is_file() else {"schema_version": "1", "lineages": {}}
    data["lineages"][Path(run_dir).name] = {
        "run_dir": str(run_dir), "canonical_digest": document["parent"]["canonical_digest"],
        "adr_run_id": adr_id, "effective_digest": document["effective_digest"], "finalized_at": now()}
    temporary = path.with_name(f".{POINTER_FILE}.{adr_id}.tmp")
    write_json(temporary, data)
    temporary.replace(path)
    return path


# --- ADR source inventory --------------------------------------------------------------

def _scope_files(scope: Path) -> tuple[Path, list[tuple[str, Path]]]:
    """Every physical file of the selection (a file, or a folder recursively below itself),
    keyed by its path relative to the selection — stable across working directories."""
    scope = Path(scope)
    if not scope.exists():
        raise AdrError(f"the ADR selection {scope} does not exist")
    if scope.is_file():
        return scope.parent.resolve(), [(scope.name, scope)]
    root = scope.resolve()
    files = [(p.relative_to(scope).as_posix(), p) for p in sorted(scope.rglob("*")) if p.is_file() or p.is_symlink()]
    if not files:
        raise AdrError(f"the ADR selection {scope} contains no files")
    return root, files


def inventory(scope: Path, ledger: dict[str, Any], text_dir: Path | None = None) -> list[dict[str, Any]]:
    """One disposition per physical file: NEW_READ / CHANGED_READ (text extracted), UNCHANGED_REUSED
    (same digest as an already analyzed file: its catalog is reused, its text is not reread),
    UNSUPPORTED or FAILED. A previously analyzed file missing from the selection is
    SOURCE_REMOVED_FROM_SELECTION: a removed file is not a revoked decision."""
    root, files = _scope_files(scope)
    entries = []
    for key, path in files:
        entry: dict[str, Any] = {"path": key}
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            entries.append({**entry, "disposition": "FAILED", "reason": "resolves outside the selected ADR scope",
                            "digest": None})
            continue
        digest = file_digest(resolved)
        entry["digest"] = digest
        previous = ledger.get(key)
        if previous and previous.get("digest") == digest and previous.get("readable"):
            entries.append({**entry, "disposition": "UNCHANGED_REUSED", "reason": "same digest as the analyzed file",
                            "read_in": previous.get("read_in")})
            continue
        text, status, reason = sources.read_text(resolved)
        if status == "READ" and text is not None:
            entry.update(disposition="CHANGED_READ" if previous else "NEW_READ", reason=reason,
                         line_count=len(text.splitlines()))
            if text_dir is not None:
                text_dir.mkdir(parents=True, exist_ok=True)
                name = f"{len([e for e in entries if e['disposition'] in READABLE]) + 1:03d}.txt"
                (text_dir / name).write_text(text, encoding="utf-8")
                entry["text_ref"] = f"text/{name}"
        elif status in {"METADATA_ONLY", "UNSUPPORTED"}:
            entry.update(disposition="UNSUPPORTED", reason=reason)
        else:
            entry.update(disposition="FAILED", reason=reason)
        entries.append(entry)
    present = {entry["path"] for entry in entries}
    for key in sorted(set(ledger) - present):
        entries.append({"path": key, "disposition": "SOURCE_REMOVED_FROM_SELECTION", "digest": ledger[key].get("digest"),
                        "reason": "no longer in the selection; its earlier decisions stay in effect until a decision "
                                  "explicitly revokes or supersedes them"})
    return entries


# --- start -----------------------------------------------------------------------------

def next_round_id(run_dir: Path) -> str:
    """adr-001, adr-002, ...: the next number after every round ever started (finalized or not)
    under this canonical run, so an id is never reused."""
    numbers = [int(m.group(1)) for p in (Path(run_dir) / ADR_FOLDER).glob("adr-*") if (m := ROUND_ID.match(p.name))]
    return f"adr-{max(numbers, default=0) + 1:03d}"


def _domain_model(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "stages" / "design.result.json"
    return read_json(path).get("domain_model", {}) if path.is_file() else {}


def _claims(run_dir: Path) -> list[dict[str, Any]]:
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    return [{"id": c["id"], "requirement_ref": c["requirement_ref"], "claim": c["normalized_claim"]}
            for c in canonical["index"].get("normative_clauses", [])]


def start_adr(run_dir: Path, scope: Path, *, base_adr: str | None = None) -> dict[str, Any]:
    """Resolve the base effective state, inventory the selection, extract only new or changed
    files, and write the work order. The parent run is read, never written."""
    run_dir = Path(run_dir).resolve()
    base = resolve_base(run_dir, base_adr)
    adr_id = next_round_id(run_dir)
    round_dir = _round_dir(run_dir, adr_id)
    before = parent_snapshot(run_dir)
    staging = round_dir.with_name(f".{adr_id}.staging")
    if staging.exists():
        raise AdrError(f"a previous start of {adr_id} was interrupted; remove {staging} and start again")
    try:
        entries = inventory(scope, base["sources"], staging / "text")
        texts = {e["path"]: (staging / e["text_ref"]).read_text(encoding="utf-8")
                 for e in entries if e["disposition"] in READABLE}
        lineage = {
            "adr_run_id": adr_id, "status": "STARTED", "created_at": now(),
            "parent_run_id": run_dir.name, "parent_canonical_digest": base["parent"]["canonical_digest"],
            "previous_adr_id": base["adr_run_id"], "previous_effective_digest": base["effective_digest"],
            "scope": {"files": len(entries)},
            "sources": [{k: e.get(k) for k in ("path", "digest", "disposition")} for e in entries],
            "parent_snapshot_digest": stable_digest(before),
        }
        write_json(staging / "inventory.json", {"sources": entries})
        write_json(staging / "work-order.json", work_order(run_dir, base, adr_id, entries, texts))
        write_json(staging / ROUND_FILE, lineage)
        staging.replace(round_dir)  # the round becomes visible only once complete
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if parent_snapshot(run_dir) != before:
        raise AdrError("the parent canonical run changed while the ADR round started")
    counts = {d: sum(e["disposition"] == d for e in entries) for d in SOURCE_DISPOSITIONS}
    return {"adr_run_id": adr_id, "adr_dir": str(round_dir), "work_order": str(round_dir / "work-order.json"),
            "base": base["adr_run_id"] or "canonical", "sources": counts, "next": "analysis",
            "live_azure_calls": 0}


def work_order(run_dir: Path, base: dict[str, Any], adr_id: str, entries: list[dict[str, Any]],
               texts: dict[str, str]) -> dict[str, Any]:
    """Everything the analysis needs, from persisted state only: no original source is reread."""
    active = [c for c in base["cases"] if base["case_states"][c["id"]]["state"] == "ACTIVE"]
    reused = {e["path"] for e in entries if e["disposition"] == "UNCHANGED_REUSED"}
    return {
        "adr_run_id": adr_id, "parent_run_id": run_dir.name, "base_adr_id": base["adr_run_id"],
        "output_locale": base["output_locale"],
        "adr_sources": [{"path": e["path"], "disposition": e["disposition"], "text": texts.get(e["path"]),
                         "reason": e.get("reason")} for e in entries],
        "reused_decisions": [d for d in base["decisions"] if d["source"] in reused],
        "decision_ledger": [{k: d[k] for k in ("id", "official_id", "source", "status", "statement", "relationship")}
                            for d in base["decisions"]],
        "domain_model": _domain_model(run_dir),
        "requirements": [{"id": r["id"], "source_identifier": r.get("source_identifier"), "title": r.get("source_title"),
                          "statement": r.get("statement")} for r in base["requirements"]] + base["adr_requirements"],
        "claims": _claims(run_dir),
        "test_cases": [{"id": c["id"], "title": c["title"], "status": c["status"], "type": c.get("primary_type"),
                        "basis": c.get("test_basis"), "objective": c.get("objective"),
                        "failure_domain": c.get("failure_domain"), "requirement_refs": c.get("requirement_refs", []),
                        "source_identifiers": c.get("source_identifiers", []),
                        "expected": [s.get("expected_result") for s in c.get("steps", [])],
                        "question_refs": c.get("question_refs", [])} for c in active],
        "superseded_test_cases": [{"id": cid, **state} for cid, state in base["case_states"].items()
                                  if state["state"] != "ACTIVE"],
        "questions": [{**q, "disposition": base["question_dispositions"].get(q["id"])} for q in base["questions"]],
        "findings": [{**f, "disposition": base["finding_dispositions"].get(f["id"])} for f in base["findings"]],
        "parent_evidence": [{"path": e["path"], "lines": e.get("line_count")}
                            for e in read_json(run_dir / "evidence" / "source-catalog.json")["sources"] if e.get("text_ref")],
        "vocabulary": vocabulary(),
        "instructions": (
            "The selected ADR material is a change corpus: formal ADRs, approved decisions, meeting notes, drafts, "
            "observations, standards, proposals, rejected or future ideas, all mixed. Review every NEW_READ / "
            "CHANGED_READ file as a whole corpus against the persisted project state; never reread the original "
            "project sources, and never rely on the files naming a requirement, rule or Test Case. Catalog each "
            "material statement verbatim with its own kind, status (only APPROVED when the file itself shows the "
            "approval) and disposition; a file's status is not each statement's authority. Build decisions from "
            "statements, reconciling them across files and never voting between disagreeing ones. Map each "
            "decision to the project model by meaning (requirements, rules, actors, states, integrations, devices, "
            "E2E journeys), find its hidden consequences, map DIRECT and INDIRECT Test Case impact, and list its "
            "testable claims and how each is covered — including behavior no Test Case covers yet. Review the "
            "expansion dimensions for each behavior-changing decision (targeted, never global). Drafts and notes "
            "become Questions, Findings, REVIEW_ONLY or context, never a silent change; NO_TEST_IMPACT is a valid, "
            "explained result. When an excerpt of an original project source is needed, request a bounded "
            f"lookup: `python scripts/adr.py lookup --run <run> --adr-id {adr_id} --source <path> --query \"...\"`. "
            "Submit with `python scripts/adr.py submit-analysis --run <run> --adr-id "
            f"{adr_id} --file <analysis.json>`; then write a complete procedure for every UPDATE / CREATE and "
            "submit it with `submit-procedures`; then `finalize`."),
    }


def vocabulary() -> dict[str, Any]:
    import adr_contract as c
    from expansion import DIMENSIONS
    return {"document_statuses": list(c.DOCUMENT_STATUSES), "statement_kinds": list(c.STATEMENT_KINDS),
            "statement_statuses": list(c.STATEMENT_STATUSES), "statement_dispositions": list(c.STATEMENT_DISPOSITIONS),
            "confidence": list(c.CONFIDENCE), "relationships": list(c.RELATIONSHIPS),
            "claim_dispositions": list(c.CLAIM_DISPOSITIONS), "actions": list(c.ACTIONS), "impacts": list(c.IMPACTS),
            "bases": list(c.BASES), "dimensions": list(DIMENSIONS),
            "dimension_dispositions": list(c.DIMENSION_DISPOSITIONS),
            "question_dispositions": list(c.QUESTION_DISPOSITIONS), "finding_dispositions": list(c.FINDING_DISPOSITIONS)}


# --- bounded lookup into the parent's persisted evidence -------------------------------

def lookup(run_dir: Path, adr_id: str, source: str, *, query: str | None = None,
           line_start: int | None = None, line_end: int | None = None) -> dict[str, Any]:
    """A bounded, recorded excerpt of an original project source, from the parent run's own
    evidence snapshot — never the original corpus, never a full reread."""
    run_dir = Path(run_dir).resolve()
    round_dir = _round_dir(run_dir, adr_id)
    lineage = _round(round_dir)
    if lineage["status"] == "FINALIZED":
        raise AdrError(f"ADR round {adr_id} is finalized")
    if verify_canonical(run_dir)["semantic_fingerprint"] != lineage["parent_canonical_digest"]:
        raise AdrError("the parent canonical suite changed since this ADR round started")
    catalog = read_json(run_dir / "evidence" / "source-catalog.json")["sources"]
    entry = next((item for item in catalog if item["path"] == source), None)
    if entry is None or not entry.get("text_ref"):
        raise AdrError(f"{source!r} is not a readable source of the parent run")
    lines = (run_dir / "evidence" / entry["text_ref"]).read_text(encoding="utf-8").splitlines()
    if line_start is not None:
        line_end = line_end or line_start
        if not (1 <= line_start <= line_end <= len(lines)) or line_end - line_start > 80:
            raise AdrError(f"{source}:{line_start}-{line_end} is not a bounded valid range ({len(lines)} lines, at most 80)")
        excerpt, locator = "\n".join(lines[line_start - 1:line_end]), f"lines {line_start}-{line_end}"
    elif query:
        match = next((i for i, line in enumerate(lines) if query.casefold() in line.casefold()), None)
        if match is None:
            raise AdrError(f"{query!r} was not found in {source}")
        excerpt, locator = "\n".join(lines[max(0, match - 2):match + 3]), f"near {query!r} (line {match + 1})"
    else:
        raise AdrError("lookup requires a query or a line range")
    path = round_dir / "lookups.json"
    records = read_json(path)["lookups"] if path.is_file() else []
    records.append({"source": source, "locator": locator, "at": now()})
    write_json(path, {"lookups": records})
    return {"source": source, "locator": locator, "excerpt": excerpt}


def status(run_dir: Path, adr_id: str | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    adr_id = adr_id or current_adr(run_dir)
    if not adr_id:
        return {"parent_run_id": run_dir.name, "current_adr": None}
    lineage = _round(_round_dir(run_dir, adr_id))
    return {"parent_run_id": run_dir.name, "adr_run_id": adr_id, "status": lineage["status"],
            "previous_adr_id": lineage.get("previous_adr_id"), "current_adr": current_adr(run_dir)}


# --- stage plumbing --------------------------------------------------------------------

def _set_status(round_dir: Path, lineage: dict[str, Any], status_value: str, **changes: Any) -> None:
    """One atomic replacement of the round's lineage record; nothing else advances the state."""
    lineage.update(status=status_value, **changes)
    temporary = round_dir / f".{ROUND_FILE}.tmp"
    write_json(temporary, lineage)
    temporary.replace(round_dir / ROUND_FILE)


def _open_round(run_dir: Path, adr_id: str, expected: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """The round, its lineage and its base effective state — all re-verified before any step."""
    run_dir = Path(run_dir).resolve()
    round_dir = _round_dir(run_dir, adr_id)
    lineage = _round(round_dir)
    if lineage["status"] != expected:
        raise AdrError(f"ADR round {adr_id} is {lineage['status']}; this step needs {expected}"
                       + (" (a finalized round is immutable: start a new round)" if lineage["status"] == "FINALIZED" else ""))
    canonical = verify_canonical(run_dir)
    if canonical["semantic_fingerprint"] != lineage["parent_canonical_digest"]:
        raise AdrError("the parent canonical suite changed since this ADR round started; start a new round")
    previous = lineage.get("previous_adr_id")
    base = load_effective(run_dir, previous, canonical) if previous else canonical_effective(run_dir, canonical)
    if base["effective_digest"] != lineage["previous_effective_digest"]:
        raise AdrError(f"the state this round was built on ({previous or 'canonical'}) changed; start a new round")
    return round_dir, lineage, base


def _round_texts(round_dir: Path) -> dict[str, str]:
    entries = read_json(round_dir / "inventory.json")["sources"]
    return {e["path"]: (round_dir / e["text_ref"]).read_text(encoding="utf-8")
            for e in entries if e["disposition"] in READABLE}


def _ledger_texts(run_dir: Path, base: dict[str, Any]) -> dict[str, str]:
    """Texts of ADR files analyzed in earlier rounds, from those rounds' own snapshots."""
    return {path: (Path(run_dir) / ADR_FOLDER / entry["text_ref"]).read_text(encoding="utf-8")
            for path, entry in base["sources"].items() if entry.get("text_ref")}


def _parent_texts(run_dir: Path) -> dict[str, str]:
    catalog = read_json(Path(run_dir) / "evidence" / "source-catalog.json")["sources"]
    return {e["path"]: (Path(run_dir) / "evidence" / e["text_ref"]).read_text(encoding="utf-8")
            for e in catalog if e.get("text_ref")}


# --- analysis --------------------------------------------------------------------------

def submit_analysis(run_dir: Path, adr_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the model's ADR analysis and allocate every id. A rejection records nothing."""
    from adr_contract import validate_analysis
    from common import StageError
    if not isinstance(payload, dict):
        raise AdrError("the ADR analysis must be a JSON object")
    round_dir, lineage, base = _open_round(run_dir, adr_id, "STARTED")
    run_dir = Path(run_dir).resolve()
    digests = {e["path"]: e.get("digest") for e in read_json(round_dir / "inventory.json")["sources"]}
    checked = validate_analysis(payload, {"base": base, "texts": _round_texts(round_dir), "digests": digests,
                                          "parent_sources": set(_parent_texts(run_dir))})
    errors = checked.pop("errors")
    if errors:
        raise StageError("adr-analysis", errors)
    result = allocate(base, checked, adr_id)
    write_json(round_dir / "analysis.payload.json", payload)
    write_json(round_dir / "analysis.result.json", result)
    _set_status(round_dir, lineage, "ANALYZED", analyzed_at=now())
    writes = [e["id"] for e in result["test_cases"] if e["action"] in {"UPDATE", "CREATE"}]
    return {"adr_run_id": adr_id, "status": "ANALYZED", "decisions": len(result["decisions"]),
            "affected": len(result["test_cases"]), "procedures_required": writes,
            "allocations": result["allocations"], "next": "procedures"}


def allocate(base: dict[str, Any], checked: dict[str, Any], adr_id: str) -> dict[str, Any]:
    """Runtime-owned ids, continuing the project-wide numbering of the effective suite."""
    from adr_contract import MINTED_DECISION, next_ids
    decisions = checked["decisions"]
    minted = iter(next_ids(MINTED_DECISION, [d["id"] for d in base["decisions"]],
                           sum(not d["official_id"] for d in decisions)))
    decision_id = {}
    for decision in decisions:
        decision_id[decision["key"]] = decision["official_id"] or next(minted)
        decision.update(id=decision_id[decision["key"]], minted_id=not decision["official_id"], adr_run_id=adr_id)
    creates = [e for e in checked["test_cases"] if e["action"] == "CREATE"]
    new_ids = iter(next_ids("TC-", [c["id"] for c in base["cases"]], len(creates)))
    case_id = {e["ref"]: e["test"] for e in checked["test_cases"] if e["test"]}
    for entry in creates:
        case_id[entry["ref"]] = next(new_ids)
    for entry in checked["test_cases"]:
        entry["id"] = case_id[entry["ref"]]
        entry["decisions"] = [decision_id[k] for k in entry["decisions"]]
        if entry["superseded_by"]:
            entry["superseded_by"] = case_id[entry["superseded_by"]]
    question_id = dict(zip([q["key"] for q in checked["questions"]],
                           next_ids("Q-", [q["id"] for q in base["questions"]], len(checked["questions"]))))
    finding_id = dict(zip([f["key"] for f in checked["findings"]],
                          next_ids("FND-", [f["id"] for f in base["findings"]], len(checked["findings"]))))
    # A decision traces to the requirements it changes or relates to; one that introduces behavior
    # no requirement covers gets an ADR-derived requirement when a new Test Case, Question or
    # Finding needs one (the schema traces each of them to a requirement).
    needed = {d for e in creates for d in e["decisions"]} | \
        {decision_id[k] for item in [*checked["questions"], *checked["findings"]] for k in item["decisions"]}
    existing_adr_req = {r["source_identifier"]: r["id"] for r in base["adr_requirements"]}
    fresh = [d for d in decisions if d["id"] in needed and d["id"] not in existing_adr_req
             and not (d["previous_authority"]["requirements"] or d["related_requirements"])]
    req_ids = iter(next_ids("REQ-", [r["id"] for r in [*base["requirements"], *base["adr_requirements"]]], len(fresh)))
    requirements_of: dict[str, list[str]] = {}
    new_requirements = []
    for decision in decisions:
        refs = list(dict.fromkeys(decision["previous_authority"]["requirements"] + decision["related_requirements"]))
        if not refs and decision["id"] in existing_adr_req:
            refs = [existing_adr_req[decision["id"]]]
        elif not refs and decision in fresh:
            refs = [next(req_ids)]
            new_requirements.append({
                "id": refs[0], "statement": decision["statement"], "status": "TESTABLE",
                "source_refs": [{"source": decision["source"], "reference": decision["reference"]}],
                "source_identifier": decision["id"], "source_title": decision["affected_behavior"],
                "source_statement": decision["excerpt"], "kind": functional_kind(base), "adr_run_id": adr_id})
        requirements_of[decision["id"]] = refs
    for question in checked["questions"]:
        question["id"] = question_id[question["key"]]
        question["decisions"] = [decision_id[k] for k in question["decisions"]]
        question["tests"] = [case_id[t] for t in question["tests"]]
    for finding in checked["findings"]:
        finding["id"] = finding_id[finding["key"]]
        finding["decisions"] = [decision_id[k] for k in finding["decisions"]]
        finding["tests"] = [case_id[t] for t in finding["tests"]]
        finding["questions"] = [question_id.get(q, q) for q in finding["questions"]]
    for review in checked["dimension_reviews"]:
        review["decision"] = decision_id.get(review["decision"], review["decision"])
        review["cases"] = [case_id.get(c, c) for c in review["cases"]]
        if review["question"]:
            review["question"] = question_id.get(review["question"], review["question"])
    for item in [*checked["question_dispositions"], *checked["finding_dispositions"]]:
        item["decision"] = decision_id[item["decision"]]
    return {**checked, "adr_run_id": adr_id, "requirements_of": requirements_of,
            "new_requirements": new_requirements,
            "allocations": {"test_cases": {e["ref"]: e["id"] for e in creates}, "questions": question_id,
                            "findings": finding_id, "decisions": decision_id,
                            "requirements": [r["id"] for r in new_requirements]}}


def functional_kind(base: dict[str, Any]) -> str:
    """The parent's own functional grouping kind, so an ADR requirement groups like the others and
    the grouping of unaffected cases never changes."""
    kinds = {r.get("kind") or sources.identifier_kind(r.get("source_identifier") or "") for r in base["requirements"]}
    return next((k for k in ("FUNCTIONAL_REQUIREMENT", "USE_CASE") if k in kinds), "FUNCTIONAL_REQUIREMENT")


# --- procedures ------------------------------------------------------------------------

def submit_procedures(run_dir: Path, adr_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Every UPDATE / CREATE gets a complete procedure, validated by the same procedure gate as
    canonical Test Cases plus the ADR invention guard. The result holds each complete resulting
    Test Case and its field-level before/after record."""
    import adr_cases
    from common import StageError
    if not isinstance(payload, dict):
        raise AdrError("the ADR procedures must be a JSON object")
    round_dir, lineage, base = _open_round(run_dir, adr_id, "ANALYZED")
    run_dir = Path(run_dir).resolve()
    analysis = read_json(round_dir / "analysis.result.json")
    texts = {**_ledger_texts(run_dir, base), **_round_texts(round_dir)}
    result = adr_cases.build_cases(payload, analysis, base, {"adr_texts": texts, "parent_texts": _parent_texts(run_dir)})
    errors = result.pop("errors")
    if errors:
        raise StageError("adr-procedures", errors)
    write_json(round_dir / "procedures.payload.json", payload)
    write_json(round_dir / "procedures.result.json", result)
    _set_status(round_dir, lineage, "PROCEDURES_READY", procedures_at=now())
    return {"adr_run_id": adr_id, "status": "PROCEDURES_READY", "cases": sorted(result["cases"]),
            "statuses": {cid: case["status"] for cid, case in result["cases"].items()}, "next": "finalize"}


# --- finalize --------------------------------------------------------------------------

def build_effective(base: dict[str, Any], analysis: dict[str, Any], built: dict[str, Any],
                    entries: list[dict[str, Any]], adr_id: str) -> dict[str, Any]:
    """Base effective state + this round's overlay. Untouched Test Cases are carried over as they
    are; nothing of the parent canonical run is modified."""
    document = copy.deepcopy(base)
    document.update(adr_run_id=adr_id, previous_adr_id=base["adr_run_id"],
                    previous_effective_digest=base["effective_digest"], lineage=[*base["lineage"], adr_id])
    resulting = built["cases"]
    document["cases"] = [copy.deepcopy(resulting.get(case["id"], case)) for case in base["cases"]]
    for entry in analysis["test_cases"]:
        cid = entry["id"]
        if entry["action"] == "CREATE":
            document["cases"].append(copy.deepcopy(resulting[cid]))
            document["case_states"][cid] = {"state": "ACTIVE", "origin": "ADR", "export_key": f"adr:{cid}",
                                            "created_by": adr_id, "last_changed_by": adr_id}
        elif entry["action"] == "UPDATE":
            document["case_states"][cid]["last_changed_by"] = adr_id
        elif entry["action"] == "SUPERSEDE":
            document["case_states"][cid].update(state="SUPERSEDED", superseded_by=entry["superseded_by"],
                                                superseded_in=adr_id)
        if entry["action"] == "CREATE" and entry["supersedes"]:
            document["case_states"][cid]["supersedes"] = next(
                e["id"] for e in analysis["test_cases"] if e["action"] == "SUPERSEDE" and e["superseded_by"] == cid)
        before = next((c for c in base["cases"] if c["id"] == cid), None)
        after = resulting.get(cid, before)
        document["case_history"].setdefault(cid, []).append({
            "adr_run_id": adr_id, "action": entry["action"], "impact": entry["impact"], "decisions": entry["decisions"],
            "reason": entry["reason"], "previous_definition_digest": case_digest(before) if before else None,
            "effective_definition_digest": case_digest(after), "supersedes": document["case_states"][cid].get("supersedes"),
            "superseded_by": entry["superseded_by"], "changed_fields": built["changes"].get(cid, {}).get("changed", [])})
    for decision in analysis["decisions"]:
        document["decisions"] = [d for d in document["decisions"] if d["id"] != decision["id"]] + [decision]
    document["adr_requirements"] += analysis["new_requirements"]
    document["coverage_points"] += built["new_coverage_points"]
    document["scenarios"] += built["new_scenarios"]
    for case in document["cases"]:
        for scenario in document["scenarios"]:
            if scenario["id"] in case.get("scenario_refs", []) and case["id"] not in scenario["test_case_refs"]:
                scenario["test_case_refs"].append(case["id"])
        for point in document["coverage_points"]:
            if point.get("adr_decision") and point["id"] in case.get("coverage_point_refs", []) \
                    and case["id"] not in point["target_refs"]:
                point["target_refs"].append(case["id"])
    requirement_source = {d["id"]: [{"source": d["source"], "reference": d["reference"]}] for d in analysis["decisions"]}
    for question in analysis["questions"]:
        refs = [r for d in question["decisions"] for r in analysis["requirements_of"].get(d, [])]
        document["questions"].append({
            "id": question["id"], "related_test_cases": sorted(set(question["tests"])),
            "requirement_refs": sorted(set(refs or question["requirements"])),
            "source_refs": [r for d in question["decisions"] for r in requirement_source[d]],
            "question": question["question"], "reason": question["reason"], "blocking": question["blocking"],
            "impact": question["impact"]})
    for finding in analysis["findings"]:
        refs = [r for d in finding["decisions"] for r in analysis["requirements_of"].get(d, [])]
        document["findings"].append({
            "id": finding["id"], "type": finding["type"], "statement": finding["statement"],
            "requirement_refs": sorted(set(refs or finding["requirements"])), "source_refs": finding["source_refs"],
            "related_test_cases": sorted(set(finding["tests"])),
            "coverage_disposition": "QUESTION" if finding["questions"] else "COVERED_BY_EXISTING_SCENARIO",
            "question_refs": sorted(set(finding["questions"]))})
    for kind in ("question", "finding"):
        for item in analysis[f"{kind}_dispositions"]:
            document[f"{kind}_dispositions"].setdefault(item[kind], []).append({**item, "adr_run_id": adr_id})
    inventory_entries = {e["path"]: e for e in entries}
    for path, entry in inventory_entries.items():
        if entry["disposition"] in READABLE:
            document["sources"][path] = {
                "digest": entry["digest"], "readable": True, "read_in": adr_id, "text_ref": f"{adr_id}/{entry['text_ref']}",
                "classification": analysis["classification"].get(path),
                "decisions": [d["id"] for d in analysis["decisions"] if d["source"] == path]}
        elif entry["disposition"] in {"UNSUPPORTED", "FAILED"}:
            document["sources"][path] = {"digest": entry.get("digest"), "readable": False, "read_in": adr_id,
                                         "disposition": entry["disposition"], "reason": entry.get("reason")}
        elif entry["disposition"] == "SOURCE_REMOVED_FROM_SELECTION":
            document["sources"][path] = {**document["sources"][path], "removed_from_selection_in": adr_id}
    document["effective_digest"] = effective_digest(document)
    return document


def validate_round(base: dict[str, Any], document: dict[str, Any], analysis: dict[str, Any], built: dict[str, Any],
                   entries: list[dict[str, Any]]) -> list[str]:
    """ADR-specific invariants, independent of the eight canonical gates (which stay untouched)."""
    errors = []
    accounted = {e["path"] for e in entries}
    if any(e.get("disposition") not in SOURCE_DISPOSITIONS for e in entries) or \
            not set(base["sources"]) <= accounted:
        errors.append("ADR source accounting is incomplete")
    for decision in analysis["decisions"]:
        if decision["relationship"] not in __import__("adr_contract").RELATIONSHIPS:
            errors.append(f"decision {decision['id']} has no relationship disposition")
    decisions = {d["id"] for d in document["decisions"]}
    affected = {}
    for entry in analysis["test_cases"]:
        affected[entry["id"]] = entry["action"]
        if not entry["decisions"] or not set(entry["decisions"]) <= decisions:
            errors.append(f"{entry['id']} is affected without traceable ADR decision evidence")
        if entry["action"] in {"UPDATE", "CREATE"}:
            case = built["cases"].get(entry["id"])
            if not case or not case.get("steps") or not all(s.get("action") for s in case["steps"]):
                errors.append(f"{entry['id']} {entry['action']} has no complete resulting procedure")
            if entry["id"] not in built.get("procedures", {}):
                errors.append(f"{entry['id']} {entry['action']} was not validated by the procedure gate")
    ids = [c["id"] for c in document["cases"]]
    if len(ids) != len(set(ids)):
        errors.append("Test Case ids are not unique in the effective suite")
    for kind, prefix in (("questions", "Q-"), ("findings", "FND-")):
        values = [item["id"] for item in document[kind]]
        if len(values) != len(set(values)):
            errors.append(f"{kind} ids collide in the effective suite")
    previous = {c["id"]: case_digest(c) for c in base["cases"]}
    changed = [cid for cid, digest in previous.items()
               if cid not in affected and case_digest(next(c for c in document["cases"] if c["id"] == cid)) != digest]
    if changed:
        errors.append(f"unaffected Test Cases changed: {changed}")
    for cid, action in affected.items():
        if action in {"AFFECTED_NO_CHANGE", "REVIEW_ONLY", "CONFLICT", "SUPERSEDE"} and \
                case_digest(next(c for c in document["cases"] if c["id"] == cid)) != previous.get(cid):
            errors.append(f"{cid} is {action} but its definition changed")
    for kind in ("question", "finding"):
        known = {item["id"] for item in document[f"{kind}s"]}
        for case in document["cases"]:
            for ref in case.get(f"{kind}_refs", []):
                if ref not in known:
                    errors.append(f"{case['id']} references unknown {kind} {ref}")
    for cid, state in document["case_states"].items():
        if state.get("superseded_by") and state["superseded_by"] not in document["case_states"]:
            errors.append(f"{cid} is superseded by unknown {state['superseded_by']}")
    keys = [s["export_key"] for s in document["case_states"].values()]
    if len(keys) != len(set(keys)):
        errors.append("export keys are not unique")
    for cid, state in base["case_states"].items():
        if document["case_states"][cid]["export_key"] != state["export_key"]:
            errors.append(f"{cid} changed its export key")
    return errors


def finalize_adr(run_dir: Path, adr_id: str) -> dict[str, Any]:
    """Validate the round, write the effective suite, the ADR report and the local Azure ADR delta,
    seal the round, and only then move the current-ADR pointer. Never contacts Azure."""
    import adr_azure
    import adr_render
    run_dir = Path(run_dir).resolve()
    round_dir = _round_dir(run_dir, adr_id)
    if _round(round_dir)["status"] == "FINALIZED":
        return _complete_pointer(run_dir, adr_id)
    round_dir, lineage, base = _open_round(run_dir, adr_id, "PROCEDURES_READY")
    before = parent_snapshot(run_dir)
    if stable_digest(before) != lineage["parent_snapshot_digest"]:
        raise AdrError("the parent canonical run's files changed since this ADR round started")
    analysis = read_json(round_dir / "analysis.result.json")
    built = read_json(round_dir / "procedures.result.json")
    entries = read_json(round_dir / "inventory.json")["sources"]
    document = build_effective(base, analysis, built, entries, adr_id)
    delta = adr_azure.build_delta_package(run_dir, document, analysis, built)
    errors = validate_round(base, document, analysis, built, entries)
    errors += adr_azure.validate_delta(delta, analysis)
    if errors:
        from common import StageError
        raise StageError("adr-finalize", errors)
    lookups = read_json(round_dir / "lookups.json")["lookups"] if (round_dir / "lookups.json").is_file() else []
    metrics = round_metrics(base, document, analysis, built, entries, lookups, delta)
    write_json(round_dir / "effective-suite.json", document)
    outputs = adr_render.publish(run_dir, round_dir, document, base, analysis, built, entries, metrics, delta, lineage)
    _set_status(round_dir, lineage, "FINALIZED", finalized_at=now(), effective_digest=document["effective_digest"],
                metrics=metrics)
    files = sorted(p.relative_to(round_dir).as_posix() for p in round_dir.rglob("*")
                   if p.is_file() and p.name not in {"adr-manifest.json", "lookups.json"})
    write_json(round_dir / "adr-manifest.json", {
        "adr_run_id": adr_id, "parent_run_id": run_dir.name, "parent_canonical_digest": lineage["parent_canonical_digest"],
        "previous_adr_id": lineage["previous_adr_id"], "previous_effective_digest": lineage["previous_effective_digest"],
        "effective_digest": document["effective_digest"], "outputs": outputs,
        "files": {name: file_digest(round_dir / name) for name in files}})
    if parent_snapshot(run_dir) != before:
        raise AdrError("the parent canonical run changed during ADR finalize")
    mark_current_adr(run_dir, adr_id, document)
    return {"adr_run_id": adr_id, "status": "FINALIZED", "effective_digest": document["effective_digest"],
            "outputs": outputs, "metrics": metrics, "live_azure_calls": 0, "azure_writes": 0}


def _complete_pointer(run_dir: Path, adr_id: str) -> dict[str, Any]:
    """A round finalized just before an interruption: point at it if the pointer still names the
    state it was built on; otherwise leave the pointer alone."""
    document = load_effective(run_dir, adr_id)
    lineage = _round(_round_dir(run_dir, adr_id))
    current = current_adr(run_dir)
    if current != adr_id and current == lineage.get("previous_adr_id"):
        mark_current_adr(run_dir, adr_id, document)
    return {"adr_run_id": adr_id, "status": "FINALIZED", "effective_digest": document["effective_digest"],
            "current_adr": current_adr(run_dir), "live_azure_calls": 0, "azure_writes": 0}


def round_metrics(base: dict[str, Any], document: dict[str, Any], analysis: dict[str, Any], built: dict[str, Any],
                  entries: list[dict[str, Any]], lookups: list[dict[str, Any]], delta: dict[str, Any]) -> dict[str, Any]:
    actions = [e["action"] for e in analysis["test_cases"]]
    affected = {e["id"] for e in analysis["test_cases"]}
    statuses = {cid: case["status"] for cid, case in built["cases"].items()}
    previous = {c["id"]: case_digest(c) for c in base["cases"]}
    unaffected = [cid for cid in previous if cid not in affected]
    count = lambda name: sum(e["disposition"] == name for e in entries)  # noqa: E731
    return {
        "adr_files_total": sum(e["disposition"] != "SOURCE_REMOVED_FROM_SELECTION" for e in entries),
        "adr_files_read": count("NEW_READ") + count("CHANGED_READ"), "adr_files_new": count("NEW_READ"),
        "adr_files_changed": count("CHANGED_READ"), "adr_files_reused": count("UNCHANGED_REUSED"),
        "adr_files_unsupported": count("UNSUPPORTED"), "adr_files_failed": count("FAILED"),
        "adr_files_removed_from_selection": count("SOURCE_REMOVED_FROM_SELECTION"),
        "adr_decisions": len(analysis["decisions"]),
        "targeted_parent_lookups": len(lookups), "runtime_full_parent_source_rereads": 0,
        "directly_affected_cases": sum(e["impact"] == "DIRECT" for e in analysis["test_cases"]),
        "indirectly_affected_cases": sum(e["impact"] == "INDIRECT" for e in analysis["test_cases"]),
        "updated_cases": actions.count("UPDATE"), "created_cases": actions.count("CREATE"),
        "superseded_cases": actions.count("SUPERSEDE"), "review_only_cases": actions.count("REVIEW_ONLY"),
        "conflict_cases": actions.count("CONFLICT"), "affected_no_change_cases": actions.count("AFFECTED_NO_CHANGE"),
        "review_cases": sum(s == "NEEDS_REVIEW" for s in statuses.values()),
        "blocked_cases": sum(s.startswith("BLOCKED") for s in statuses.values()),
        "unaffected_cases": len(unaffected),
        "unaffected_cases_changed": sum(case_digest(next(c for c in document["cases"] if c["id"] == cid)) != previous[cid]
                                        for cid in unaffected),
        "procedures_generated": actions.count("CREATE"), "procedures_updated": actions.count("UPDATE"),
        "questions_created": len(analysis["questions"]), "findings_created": len(analysis["findings"]),
        "questions_resolved_by_adr": sum(d["disposition"] == "RESOLVED_BY_ADR" for d in analysis["question_dispositions"]),
        "azure_delta_test_cases": len(delta["test_cases"]), "live_azure_calls": 0,
    }


# --- dispatcher and command line -------------------------------------------------------

def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """/ftd --adr <file|folder> (alias /ftd-adr): start a round over the current validated run, or
    advance an existing round with `phase`. Never talks to Azure."""
    run_dir = resolve_canonical(request.get("run_dir") or request.get("run"),
                                request.get("output_dir") or request.get("artifact_root"))
    phase = request.get("phase") or ("start" if request.get("scope") or request.get("adr") else "status")
    if phase == "start":
        scope = request.get("scope") or request.get("adr")
        if not scope:
            raise AdrError("/ftd --adr needs the ADR file or folder to analyze")
        return start_adr(run_dir, Path(scope), base_adr=request.get("base_adr"))
    if phase == "status":
        return status(run_dir, request.get("adr_id"))
    adr_id = request.get("adr_id")
    if not adr_id:
        raise AdrError(f"phase {phase!r} needs the adr_id returned by start; an ADR round is never guessed")
    payload = request.get("payload")
    if payload is None and request.get("file"):
        payload = read_json(Path(request["file"]))
    if phase == "analysis":
        return submit_analysis(run_dir, adr_id, payload)
    if phase == "procedures":
        return submit_procedures(run_dir, adr_id, payload)
    if phase == "finalize":
        return finalize_adr(run_dir, adr_id)
    if phase == "lookup":
        return lookup(run_dir, adr_id, request["source"], query=request.get("query"),
                      line_start=request.get("line_start"), line_end=request.get("line_end"))
    raise AdrError(f"unknown ADR phase {phase!r}; use start, analysis, procedures, finalize, lookup or status")


def main(argv: list[str] | None = None) -> int:
    import argparse
    from common import StageError
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    phases = {"start": "start a round over the ADR file or folder", "submit-analysis": "submit the ADR analysis",
              "submit-procedures": "submit the procedures of every UPDATE / CREATE", "finalize": "finalize the round",
              "lookup": "bounded excerpt of a parent source", "status": "the current ADR round of the run"}
    for name, text in phases.items():
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--run", help="canonical run (default: the current validated run of --output-dir)")
        sub.add_argument("--output-dir", help="artifact root holding .ftd/current-run.json (default ./ftd-output)")
        if name == "start":
            sub.add_argument("--scope", "--adr", dest="scope", required=True, help="the ADR file or folder")
            sub.add_argument("--base-adr", help="an earlier finalized round to build on, or `none` for the canonical suite")
        else:
            sub.add_argument("--adr-id", required=name != "status")
        if name.startswith("submit-"):
            sub.add_argument("--file", required=True, type=Path)
        if name == "lookup":
            sub.add_argument("--source", required=True)
            sub.add_argument("--query")
            sub.add_argument("--lines", help="A-B")
    args = parser.parse_args(argv)
    request: dict[str, Any] = {"run": args.run, "output_dir": args.output_dir,
                               "phase": {"submit-analysis": "analysis", "submit-procedures": "procedures"}.get(
                                   args.command, args.command)}
    for field in ("scope", "base_adr", "adr_id", "file", "source", "query"):
        if getattr(args, field, None) is not None:
            request[field] = getattr(args, field)
    if getattr(args, "lines", None):
        start_line, _, end_line = args.lines.partition("-")
        request.update(line_start=int(start_line), line_end=int(end_line or start_line))
    try:
        result = dispatch(request)
    except StageError as exc:
        print(json.dumps({"errors": exc.errors}, indent=2, ensure_ascii=False))
        return 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"errors": [str(exc)]}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
