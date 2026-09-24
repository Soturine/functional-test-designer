#!/usr/bin/env python3
"""Post-suite semantic challenge: an optional, additive pass over an already-frozen suite.

Generate the canonical suite first. Challenge it second. The frozen canonical run is
never mutated: challenge cases live in a separate `CH-*` namespace, under
`<run>/challenges/<challenge-id>/`, and are validated against the parent's own
recorded state. Human-authored seed Markdown files are inspiration, never authority;
the model is expected to go beyond them using the actors, rules, states, findings and
evidence the parent run already established. This module is the same kind of thin
deterministic shell as the rest of the pipeline: it owns identity, grounding checks
and canonical immutability, never the scenario reasoning itself.

State machine per challenge run: STARTED -> SUBMITTED -> FINALIZED. Each transition is
one-way; a mistake is corrected by starting a new challenge_id, never by rewriting one
already advanced.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import StageError, file_digest, normalize_identifier, now, read_json, write_json
from design import check_locale, unknown_keys
from procedures import (
    ABSTRACT_ACTION, ABSTRACT_OBSERVATION, ACTION_ECHO, ALTERNATIVE_OUTCOMES, AUTH_ONLY, ENVIRONMENT_CONTROL,
    FIXTURE_NAME, GENERIC_PRECONDITION, LOAD_THRESHOLD, PLACEHOLDER, SUITABILITY, MATERIAL_UNKNOWNS,
    AUTOMATION_UNKNOWNS, PATH_UNKNOWNS, compressed_action, hidden_subtest, source_vocabulary,
)
import pipeline


class ChallengeError(ValueError):
    """A challenge run tried to act on a parent that is not frozen, or one it no longer matches."""


DISCOVERIES = ("HUMAN_SEEDED", "MODEL_DERIVED", "HUMAN_AND_MODEL")
SEED_DISPOSITIONS = ("MATERIALIZED", "ALREADY_COVERED", "MERGED", "QUESTIONED", "NOT_APPLICABLE")
# Recognized for rendering/grouping in the Manual/Physical/Field plan; not a closed
# ontology — a well-formed project-specific tag beyond this set is accepted too.
CORE_EXECUTION_TAGS = (
    "AUTOMATABLE", "MANUAL", "PHYSICAL_DEVICE", "EXTERNAL_ENVIRONMENT", "EXPLORATORY", "CHAOS_RECOVERY",
)
TAG_FORMAT = re.compile(r"^[A-Z][A-Z0-9_]*$")
CASE_FIELDS = {
    "key", "title", "discovery", "inspired_by", "related_test_cases", "related_source_identifiers",
    "related_findings", "related_questions", "rationale", "execution_tags", "automation_suitability",
    "priority", "required_resources", "environment_requirements", "preconditions", "test_data", "steps",
    "postconditions", "evidence_refs", "unknowns", "canonical_gap_candidate", "notes",
}
PAYLOAD_KEYS = {"cases", "seed_dispositions"}
BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_id(value: str, label: str) -> str:
    if not value or any(part in value for part in ("/", "\\", "..")):
        raise ValueError(f"{label} must be a safe local identifier")
    return value


def _challenge_dir(run_dir: Path, challenge_id: str) -> Path:
    return Path(run_dir) / "challenges" / _safe_id(challenge_id, "challenge_id")


def _canonical_digest(run_dir: Path) -> str:
    path = Path(run_dir) / "canonical-suite.json"
    if not path.is_file():
        raise ChallengeError(f"{run_dir} has no canonical-suite.json; finalize the parent run first")
    return file_digest(path)


def _require_frozen(run_dir: Path) -> dict[str, Any]:
    state = pipeline._state(run_dir)
    if state.get("status") != "VALIDATED":
        raise ChallengeError(
            "the canonical suite must be finalized before it can be challenged "
            f"(run status is {state.get('status')!r}, not VALIDATED)"
        )
    return state


def _lineage(challenge_dir: Path) -> dict[str, Any]:
    if not challenge_dir.is_dir():
        raise ChallengeError(f"challenge {challenge_dir.name!r} was not started; run start first")
    return read_json(challenge_dir / "challenge-run.json")


def _require_parent_unchanged(challenge_dir: Path, run_dir: Path) -> str:
    """Contract 1: canonical immutability. Every challenge action re-checks this."""
    lineage = _lineage(challenge_dir)
    current = _canonical_digest(run_dir)
    if current != lineage["parent_canonical_digest"]:
        raise ChallengeError(
            "the parent canonical suite changed since this challenge run started; "
            "a challenge never adapts to a moving parent, start a new challenge run"
        )
    return current


# --- seed item segmentation (structural, not semantic) ---------------------------------

def segment_seed(name: str, content: str) -> list[dict[str, Any]]:
    """Split a seed file into addressable items: one per top-level bullet, else one per
    non-empty paragraph. This is a structural split, the same kind design.py already
    does for bullet/sentence counting — it never interprets what an idea means."""
    items: list[dict[str, Any]] = []
    lines = content.splitlines()
    bullets = [(number, BULLET.match(line)) for number, line in enumerate(lines, 1)]
    bullets = [(number, match.group(1)) for number, match in bullets if match]
    if bullets:
        for text_number, (line_number, text) in enumerate(bullets, 1):
            items.append({"anchor": f"{name}#seed-{text_number:03d}", "text": text, "line": line_number})
        return items
    paragraph, start_line = [], 1
    for number, line in enumerate(lines + [""], 1):
        if line.strip():
            if not paragraph:
                start_line = number
            paragraph.append(line.strip())
        elif paragraph:
            items.append({"text": " ".join(paragraph), "line": start_line})
            paragraph = []
    for text_number, item in enumerate(items, 1):
        item["anchor"] = f"{name}#seed-{text_number:03d}"
    return items


# --- start ---------------------------------------------------------------------------

def _domain_model_summary(run_dir: Path) -> dict[str, Any]:
    design_result = run_dir / "stages" / "design.result.json"
    if not design_result.is_file():
        return {}
    return read_json(design_result).get("domain_model", {})


def start_challenge(
    run_dir: Path, challenge_id: str, *, seeds: list[Path] | None = None, focus: str = "",
    seed_items: list[dict[str, Any]] | None = None, seed_source: dict[str, Any] | None = None,
    formats: list[str] | None = None,
) -> dict[str, Any]:
    """`seeds` are Markdown seed files segmented structurally; `seed_items` are already
    anchored items (e.g. `instructions.md#seed-003`) normalized by the host from an
    instructions file described by `seed_source` ({"path", "digest"}). Both are
    inspiration only. `formats` are the public outputs published at finalize."""
    run_dir = Path(run_dir).resolve()
    _require_frozen(run_dir)
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    if challenge_dir.is_dir():
        raise ChallengeError(f"challenge {challenge_id!r} already exists; use a new challenge_id to rerun")
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    seed_files = []
    for seed_path in seeds or []:
        seed_path = Path(seed_path)
        if not seed_path.is_file():
            raise ChallengeError(f"seed file not found: {seed_path}")
        content = seed_path.read_text(encoding="utf-8")
        items = segment_seed(seed_path.name, content)
        seed_files.append({
            "path": seed_path.name, "digest": file_digest(seed_path), "content": content, "items": items,
        })
    if seed_items:
        anchors = [str(item.get("anchor", "")) for item in seed_items]
        if len(set(anchors)) != len(anchors) or not all(anchors):
            raise ChallengeError("seed items need unique, non-empty anchors")
        source = seed_source or {}
        seed_files.append({
            "path": Path(str(source.get("path") or "instructions.md")).name, "digest": source.get("digest"),
            "content": "\n".join(f"- {item['text']}" for item in seed_items),
            "items": [{"anchor": item["anchor"], "text": item["text"],
                       **({"section": item["section"]} if item.get("section") else {})} for item in seed_items],
        })
    sources_state = read_json(run_dir / "sources.json")
    evidence_index = [
        {"path": record["path"], "role": record["role"]} for record in sources_state["records"]
        if record["status"] in {"READ", "TRANSCRIBED"}
    ]
    cases_index = [{
        "id": case["id"], "title": case["title"], "basis": case.get("test_basis") or case.get("basis"),
        "status": case["status"], "primary_type": case.get("primary_type"),
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": case.get("automation_readiness"),
        "automation_layer": case.get("automation_layer"),
        "source_identifiers": case.get("source_identifiers", []),
        "failure_domain": case.get("failure_domain"),
    } for case in canonical["cases"]]
    work_order = {
        "parent_run_id": read_json(run_dir / "run.json")["run_id"],
        "challenge_run_id": challenge_id,
        "parent_canonical_digest": file_digest(run_dir / "canonical-suite.json"),
        "output_locale": canonical["index"].get("output_locale"),
        "focus": focus,
        "seeds": [{"path": s["path"], "content": s["content"], "items": s["items"]} for s in seed_files],
        "domain_model": _domain_model_summary(run_dir),
        "canonical_cases": cases_index,
        "requirements": [
            {"id": r["id"], "source_identifier": r["source_identifier"], "title": r.get("source_title")}
            for r in canonical["index"]["requirements"]
        ],
        "authority_excerpts": [
            {"identifier": e["identifier"], "title": e.get("title"), "excerpt": e.get("excerpt")}
            for e in sources_state["authority_index"]
        ],
        "findings": [{"id": f["id"], "statement": f["statement"]} for f in canonical["index"]["findings"]],
        "questions": [{"id": q["id"], "question": q["question"]} for q in canonical["questions"]["questions"]],
        "evidence_index": evidence_index,
        "instructions": (
            "Read the frozen canonical suite, domain model, findings and questions above; read the seed "
            "files if any (inspiration, never authority — do not promote an unsupported seed rule to a "
            "normative test). Each seed item already has a stable anchor (e.g. qa-notes.md#seed-001); "
            "disposition every meaningful item honestly in seed_dispositions, then go beyond the seeds "
            "using the project's own actors, rules, states, integrations, devices and evidence: operator "
            "mistakes, physical/digital mismatches, interruption and recovery, concurrency, long-running "
            "operation, manual-after-automatic sequences, and anything else this project's own evidence "
            "supports. A CH case is not a canonical Test Case: it may be exploratory, physical, manual, or "
            "blocked, and it must say so honestly rather than invent a screen, device or oracle. To ground "
            "a step in real evidence beyond the excerpts above, request a bounded lookup first: "
            "`python scripts/challenge.py lookup --run <run> --challenge-id "
            f"{challenge_id} --source <selected path> --query \"...\"` (or --lines A-B), then cite it in "
            "evidence_refs. Submit `python scripts/challenge.py submit --run <run> --challenge-id "
            f"{challenge_id} --file <payload.json>`, then `finalize`."
        ),
    }
    challenge_dir.mkdir(parents=True, exist_ok=True)
    write_json(challenge_dir / "work-order.json", work_order)
    write_json(challenge_dir / "challenge-run.json", {
        "challenge_run_id": challenge_id, "parent_run_id": work_order["parent_run_id"],
        "parent_canonical_digest": work_order["parent_canonical_digest"],
        "seed_refs": [{"path": s["path"], "digest": s["digest"]} for s in seed_files],
        "seed_items": [item["anchor"] for s in seed_files for item in s["items"]],
        "focus": focus, "formats": list(formats or ["JSON", "MARKDOWN", "HTML"]),
        "created_at": now(), "status": "STARTED",
    })
    return {"challenge_dir": str(challenge_dir), "work_order": str(challenge_dir / "work-order.json"),
            "seeds_received": len(seed_files),
            "seed_items_received": sum(len(s["items"]) for s in seed_files),
            "canonical_cases": len(cases_index)}


# --- targeted evidence lookup -----------------------------------------------------------

def lookup_evidence(
    run_dir: Path, challenge_id: str, source: str, *, query: str | None = None,
    line_start: int | None = None, line_end: int | None = None,
) -> dict[str, Any]:
    """A real, bounded, scope-checked read from the run's own persisted evidence
    snapshot — never the original corpus. Every call is recorded; the recorded count,
    not the presence of an evidence_ref, is what `targeted_source_lookups` reports."""
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    _require_parent_unchanged(challenge_dir, run_dir)
    catalog = read_json(run_dir / "evidence" / "source-catalog.json")["sources"]
    entry = next((item for item in catalog if item["path"] == source), None)
    if entry is None:
        raise ChallengeError(f"{source!r} is outside the selected scope of this run")
    if not entry["text_ref"]:
        raise ChallengeError(f"{source!r} has no readable text ({entry['status']}); it cannot be looked up")
    text = (run_dir / "evidence" / entry["text_ref"]).read_text(encoding="utf-8")
    lines = text.splitlines()
    if line_start is not None:
        line_end = line_end or line_start
        if not (1 <= line_start <= line_end <= len(lines)):
            raise ChallengeError(f"{source}:{line_start}-{line_end} is not a valid line range ({len(lines)} lines)")
        excerpt = "\n".join(lines[line_start - 1:line_end])
        locator = f"lines {line_start}-{line_end}"
    elif query:
        match = next((i for i, line in enumerate(lines) if query.casefold() in line.casefold()), None)
        if match is None:
            raise ChallengeError(f"{query!r} was not found in {source}")
        window = lines[max(0, match - 2):match + 3]
        excerpt = "\n".join(window)
        locator = f"near {query!r} (line {match + 1})"
    else:
        raise ChallengeError("lookup requires a query or a line range")
    record = {"source": source, "locator": locator, "at": now(), "source_digest": entry["content_digest"]}
    lookups_path = challenge_dir / "lookups.json"
    lookups = read_json(lookups_path)["lookups"] if lookups_path.is_file() else []
    lookups.append(record)
    write_json(lookups_path, {"lookups": lookups})
    return {"source": source, "locator": locator, "excerpt": excerpt}


# --- submit ----------------------------------------------------------------------------

def _validate_steps(steps: list[dict[str, Any]], label: str, locale: str, errors: list[str]) -> list[dict[str, Any]]:
    normalized = []
    for number, step in enumerate(steps, 1):
        action, expected = _text(step.get("action")), _text(step.get("expected_result"))
        if not action:
            errors.append(f"{label} step {number} requires an action")
        if ABSTRACT_ACTION.search(action):
            errors.append(f"{label} step {number} action is abstract; say who does which atomic action to which target (and where, with which semantic data) as the evidence supports, or keep the known intent and declare MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH")
        if expected and ABSTRACT_OBSERVATION.search(expected):
            errors.append(f"{label} step {number} expected result is not observable")
        if expected and ACTION_ECHO.search(expected):
            errors.append(f"{label} step {number} expected result only says the action happened; state what becomes observable")
        if expected and ALTERNATIVE_OUTCOMES.search(expected):
            errors.append(f"{label} step {number} expected result offers alternative outcomes; state one result or declare the unknown")
        if AUTH_ONLY.search(action):
            errors.append(f"{label} step {number} only authenticates; describe the real execution path")
        if hidden_subtest(action):
            errors.append(f"{label} step {number} hides independent variants; split into separate cases")
        check_locale(f"{label} step {number} action", action, locale, errors)
        check_locale(f"{label} step {number} expected_result", expected, locale, errors)
        normalized.append({"step": number, "action": action, "expected_result": expected or None})
    if len(normalized) == 1 and compressed_action(normalized[0]["action"]):
        errors.append(f"{label} compresses a multi-action flow into one step: {normalized[0]['action']!r}")
    return normalized


def _validate_evidence_refs(
    evidence_refs: list[dict[str, Any]], label: str, known_sources: set[str],
    source_lines: dict[str, int], errors: list[str],
) -> None:
    """The same fundamental scope/provenance checks `sources.check_source_refs` applies
    to any FTD evidence reference: a known selected source, a real locator, and a valid
    line range if one is given — checked against the source's real length."""
    for ref in evidence_refs:
        source = str(ref.get("source", ""))
        if source not in known_sources:
            errors.append(f"{label} evidence_refs source {source!r} is outside the selected scope")
            continue
        if not _text(ref.get("reference")):
            errors.append(f"{label} evidence_refs for {source} has no locator")
        start, end = ref.get("line_start"), ref.get("line_end", ref.get("line_start"))
        if start is not None:
            total = source_lines.get(source, 0)
            if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= total):
                errors.append(f"{label} evidence_refs {source}:{start}-{end} is not a valid line range ({total} lines)")


def validate_challenge_payload(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, PAYLOAD_KEYS, "challenge")
    locale = context["locale"]
    known_case_ids = set(context["case_ids"])
    known_identifiers = set(context["identifiers"])
    known_finding_ids = set(context["finding_ids"])
    known_question_ids = set(context["question_ids"])
    known_sources = set(context["known_sources"])
    seed_items = set(context["seed_items"])
    cases: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    key_to_id: dict[str, str] = {}
    for index, item in enumerate(payload.get("cases", []) or [], 1):
        key = _text(item.get("key")) or f"<case {index}>"
        label = f"challenge case {key}"
        if key in seen_keys:
            errors.append(f"{label} key is supplied twice")
        seen_keys.add(key)
        assigned_id = f"CH-{index:03d}"
        key_to_id[key] = assigned_id
        extra = sorted(set(item) - CASE_FIELDS)
        if extra:
            errors.append(f"{label} contains runtime-owned or unknown fields {extra}")
        title = _text(item.get("title"))
        if not title:
            errors.append(f"{label} requires a title")
        check_locale(f"{label}.title", title, locale, errors)
        discovery = _text(item.get("discovery"))
        if discovery not in DISCOVERIES:
            errors.append(f"{label} discovery must be one of {DISCOVERIES}")
        inspired_by = [_text(v) for v in item.get("inspired_by", []) or [] if _text(v)]
        if discovery in {"HUMAN_SEEDED", "HUMAN_AND_MODEL"} and not inspired_by:
            errors.append(f"{label} discovery {discovery} requires inspired_by")
        for ref in inspired_by:
            if ref not in seed_items:
                errors.append(f"{label} inspired_by {ref!r} does not name a seed item passed to this challenge run")
        related_tests = [_text(v) for v in item.get("related_test_cases", []) or [] if _text(v)]
        for ref in related_tests:
            if ref not in known_case_ids:
                errors.append(f"{label} related_test_cases references unknown canonical Test Case {ref}")
        for ref in item.get("related_source_identifiers", []) or []:
            if normalize_identifier(ref) not in known_identifiers:
                errors.append(f"{label} related_source_identifiers references an identifier outside the parent authority: {ref}")
        for ref in item.get("related_findings", []) or []:
            if _text(ref) not in known_finding_ids:
                errors.append(f"{label} related_findings references unknown Finding {ref}")
        for ref in item.get("related_questions", []) or []:
            if _text(ref) not in known_question_ids:
                errors.append(f"{label} related_questions references unknown Question {ref}")
        tags = [_text(v) for v in item.get("execution_tags", []) or [] if _text(v)]
        if not tags:
            errors.append(f"{label} requires at least one execution_tags")
        malformed = sorted(tag for tag in tags if not TAG_FORMAT.match(tag))
        if malformed:
            errors.append(f"{label} execution_tags {malformed} must be UPPER_SNAKE_CASE words")
        suitability = _text(item.get("automation_suitability"))
        if suitability and suitability not in SUITABILITY:
            errors.append(f"{label} automation_suitability must be one of {SUITABILITY}")
        rationale = _text(item.get("rationale"))
        if not rationale:
            errors.append(f"{label} requires a rationale")
        check_locale(f"{label}.rationale", rationale, locale, errors)
        gap = item.get("canonical_gap_candidate")
        if gap is not None:
            if not isinstance(gap, dict) or not _text(gap.get("authority_evidence")) or not _text(gap.get("why_normative")):
                errors.append(f"{label} canonical_gap_candidate requires authority_evidence and why_normative")
        preconditions = [_text(v) for v in item.get("preconditions", []) or [] if _text(v)]
        for value in preconditions:
            if GENERIC_PRECONDITION.search(value):
                errors.append(f"{label} has a generic precondition {value!r}")
            check_locale(f"{label}.precondition", value, locale, errors)
        test_data = []
        for row in item.get("test_data", []) or []:
            name, description = _text(row.get("name")), _text(row.get("description"))
            if PLACEHOLDER.search(f"{name} {description}"):
                errors.append(f"{label} test data {name!r} is a placeholder")
            test_data.append({"name": name, "description": description})
        unknowns = []
        for unknown in item.get("unknowns", []) or []:
            kind = _text(unknown.get("kind"))
            if kind not in MATERIAL_UNKNOWNS and kind not in AUTOMATION_UNKNOWNS:
                errors.append(f"{label} unknown kind {kind!r} is not supported")
            if not _text(unknown.get("detail")):
                errors.append(f"{label} unknown {kind} requires detail")
            question = _text(unknown.get("question")) or None
            if question and question not in known_question_ids:
                errors.append(f"{label} unknown {kind} links unknown Question {question}")
            unknowns.append({"kind": kind, "detail": _text(unknown.get("detail")), "question": question})
        evidence_refs = [dict(ref) for ref in item.get("evidence_refs", []) or [] if isinstance(ref, dict)]
        _validate_evidence_refs(evidence_refs, label, known_sources, context["source_lines"], errors)
        steps = item.get("steps", []) or []
        normalized_steps = []
        if steps:
            if not evidence_refs and not any(u["kind"] in PATH_UNKNOWNS for u in unknowns):
                errors.append(
                    f"{label} has steps but no evidence_refs; cite the execution path or declare "
                    "MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH"
                )
            normalized_steps = _validate_steps(steps, label, locale, errors)
            # The same execution rules as canonical procedures: no invented technique for a
            # controlled condition, no invented threshold, every fixture described.
            supported = {int(n) for ref in evidence_refs for n in ref.get("supports", []) or [] if str(n).isdigit()}
            path_unknown = any(u["kind"] in PATH_UNKNOWNS for u in unknowns)
            stated = " ".join(context.get("case_texts", {}).get(ref, "") for ref in related_tests)
            stated_numbers = {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", stated)}
            for step in normalized_steps:
                if ENVIRONMENT_CONTROL.search(step["action"]) and step["step"] not in supported and not path_unknown:
                    errors.append(
                        f"{label} step {step['step']} changes the environment or suppresses a signal; cite the "
                        "evidence that says how (evidence_ref supports) or declare UNKNOWN_SETUP_PATH / "
                        "MISSING_EXECUTION_SURFACE — never invent the technique")
                for threshold in LOAD_THRESHOLD.finditer(step["expected_result"] or ""):
                    if threshold.group("number").replace(",", ".") not in stated_numbers:
                        errors.append(
                            f"{label} step {step['step']} asserts the threshold {threshold.group(0)!r}, which no related "
                            "canonical Test Case states; record observed values instead")
            used = " ".join([*preconditions, *(s["action"] + " " + (s["expected_result"] or "") for s in normalized_steps)])
            undefined = sorted(set(FIXTURE_NAME.findall(used)) - {row["name"] for row in test_data}
                               - set(context.get("source_tokens", set())))
            if undefined:
                errors.append(f"{label} uses fixtures {undefined} that test_data does not describe")
        cases.append({
            "key": key, "title": title, "discovery": discovery, "inspired_by": inspired_by,
            "related_test_cases": related_tests,
            "related_source_identifiers": [_text(v) for v in item.get("related_source_identifiers", []) or []],
            "related_findings": [_text(v) for v in item.get("related_findings", []) or []],
            "related_questions": [_text(v) for v in item.get("related_questions", []) or []],
            "rationale": rationale, "execution_tags": tags, "automation_suitability": suitability or None,
            "priority": _text(item.get("priority")) or "MEDIUM",
            "required_resources": [_text(v) for v in item.get("required_resources", []) or [] if _text(v)],
            "environment_requirements": [_text(v) for v in item.get("environment_requirements", []) or [] if _text(v)],
            "preconditions": preconditions, "test_data": test_data, "steps": normalized_steps,
            "postconditions": [_text(v) for v in item.get("postconditions", []) or [] if _text(v)],
            "evidence_refs": evidence_refs, "unknowns": unknowns,
            "canonical_gap_candidate": gap if isinstance(gap, dict) else None,
            "notes": [_text(v) for v in item.get("notes", []) or [] if _text(v)],
        })
    known_result_ids = known_case_ids | set(key_to_id.values())
    dispositions = []
    for item in payload.get("seed_dispositions", []) or []:
        seed_ref = _text(item.get("seed_ref") or item.get("seed"))
        disposition = _text(item.get("disposition"))
        if seed_ref not in seed_items:
            errors.append(f"seed_dispositions references unknown seed item {seed_ref!r}")
        if disposition not in SEED_DISPOSITIONS:
            errors.append(f"seed_dispositions for {seed_ref!r} must use one of {SEED_DISPOSITIONS}")
        raw_cases = [_text(v) for v in item.get("cases", []) or [] if _text(v)]
        resolved_cases = []
        for ref in raw_cases:
            resolved = key_to_id.get(ref, ref)
            if resolved not in known_result_ids:
                errors.append(f"seed_dispositions {seed_ref!r} cases references unknown case {ref!r}")
            resolved_cases.append(resolved)
        covered_by = [_text(v) for v in item.get("covered_by", []) or [] if _text(v)]
        if disposition == "ALREADY_COVERED" and not covered_by:
            errors.append(f"seed_dispositions {seed_ref!r} disposition ALREADY_COVERED requires covered_by")
        for ref in covered_by:
            resolved = key_to_id.get(ref, ref)
            if resolved not in known_result_ids:
                errors.append(f"seed_dispositions {seed_ref!r} covered_by references unknown Test Case {ref!r}")
        dispositions.append({
            "seed_ref": seed_ref, "disposition": disposition, "summary": _text(item.get("summary")),
            "cases": resolved_cases, "covered_by": [key_to_id.get(v, v) for v in covered_by],
        })
    dispositioned = {d["seed_ref"] for d in dispositions}
    missing_disposition = sorted(seed_items - dispositioned)
    if missing_disposition:
        errors.append(f"every seed item needs a seed_dispositions entry; missing: {missing_disposition}")
    if errors:
        raise StageError("challenge", errors)
    for case in cases:
        case["id"] = key_to_id[case["key"]]
    return {
        "cases": cases, "seed_dispositions": dispositions,
        "diagnostics": {
            "seed_items_received": len(seed_items),
            "challenge_cases_generated": len(cases),
            "model_derived_cases": sum(c["discovery"] == "MODEL_DERIVED" for c in cases),
            "human_seeded_cases": sum(c["discovery"] in {"HUMAN_SEEDED", "HUMAN_AND_MODEL"} for c in cases),
            "seed_items_materialized": sum(d["disposition"] == "MATERIALIZED" for d in dispositions),
            "seed_items_already_covered": sum(d["disposition"] == "ALREADY_COVERED" for d in dispositions),
            "seed_items_merged": sum(d["disposition"] == "MERGED" for d in dispositions),
            "seed_items_questioned": sum(d["disposition"] == "QUESTIONED" for d in dispositions),
            "seed_items_not_applicable": sum(d["disposition"] == "NOT_APPLICABLE" for d in dispositions),
            "canonical_gap_candidates": sum(c["canonical_gap_candidate"] is not None for c in cases),
        },
    }


def submit_challenge(run_dir: Path, challenge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    lineage = _lineage(challenge_dir)
    if lineage["status"] != "STARTED":
        raise ChallengeError(f"challenge {challenge_id!r} is {lineage['status']}; a submitted run cannot be resubmitted")
    _require_parent_unchanged(challenge_dir, run_dir)
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    sources_state = read_json(run_dir / "sources.json")
    evidence_catalog = read_json(run_dir / "evidence" / "source-catalog.json")["sources"]
    context = {
        "locale": canonical["index"].get("output_locale") or "en",
        "case_ids": {case["id"] for case in canonical["cases"]},
        "identifiers": {normalize_identifier(v) for case in canonical["cases"] for v in case.get("source_identifiers", [])}
        | {normalize_identifier(r["source_identifier"]) for r in canonical["index"]["requirements"]},
        "finding_ids": {f["id"] for f in canonical["index"]["findings"]},
        "question_ids": {q["id"] for q in canonical["questions"]["questions"]},
        "known_sources": {record["path"] for record in sources_state["records"]},
        "source_lines": {e["path"]: e["line_count"] for e in evidence_catalog if e["line_count"]},
        "seed_items": set(lineage["seed_items"]),
        "case_texts": {case["id"]: " ".join([case.get("title", ""), case.get("objective", ""),
                                             *(s.get("expected_result") or "" for s in case.get("steps", []))])
                       for case in canonical["cases"]},
        "source_tokens": source_vocabulary(path.read_text(encoding="utf-8")
                                           for path in sorted((run_dir / "evidence" / "text").glob("*.txt"))),
    }
    result = validate_challenge_payload(payload, context)
    lookups_path = challenge_dir / "lookups.json"
    lookups = read_json(lookups_path)["lookups"] if lookups_path.is_file() else []
    result["diagnostics"].update({
        "runtime_targeted_lookups": len({(item["source"], item["locator"]) for item in lookups}),
        "runtime_full_source_rereads": 0,  # the corpus is never reopened; only the run's own evidence snapshot is read
        "model_source_rereads": "NOT_OBSERVABLE",  # the runtime cannot see what the invoking agent read outside this API
    })
    write_json(challenge_dir / "challenge-payload.json", payload)
    write_json(challenge_dir / "challenge-result.json", result)
    lineage.update({"status": "SUBMITTED", "submitted_at": now(), "diagnostics": result["diagnostics"]})
    write_json(challenge_dir / "challenge-run.json", lineage)
    return {"challenge_dir": str(challenge_dir), "recorded": True, **result["diagnostics"]}


# --- finalize ----------------------------------------------------------------------------

def _plan_bucket(tags: list[str], status: str) -> str:
    if "PHYSICAL_DEVICE" in tags:
        return "physical_device"
    if "EXTERNAL_ENVIRONMENT" in tags:
        return "external_environment"
    if "CHAOS_RECOVERY" in tags:
        return "chaos_recovery"
    if "EXPLORATORY" in tags or status == "EXPLORATORY":
        return "exploratory"
    return "manual_operational"


PLAN_SECTIONS = (
    ("physical_device", "Physical device tests"),
    ("external_environment", "External environment / integrator tests"),
    ("manual_operational", "Manual operational tests"),
    ("chaos_recovery", "Chaos / recovery"),
    ("exploratory", "Exploratory tests"),
    ("blocked", "Blocked tests and prerequisites"),
)


def classify_challenge_case(case: dict[str, Any]) -> dict[str, str]:
    """Case nature (exploratory/etc.) and readiness are related but distinct, the same
    way procedures.classify keeps them distinct for canonical Test Cases."""
    tags = case["execution_tags"]
    unknowns = case["unknowns"]
    if "EXPLORATORY" in tags:
        return {"status": "EXPLORATORY"}
    if any(u["kind"] == "EXTERNAL_DEPENDENCY_UNAVAILABLE" for u in unknowns):
        return {"status": "BLOCKED_EXTERNAL_DEPENDENCY"}
    if any(u["kind"] in MATERIAL_UNKNOWNS for u in unknowns):
        return {"status": "NEEDS_REVIEW"}
    if not case["steps"] and case["canonical_gap_candidate"]:
        return {"status": "PROPOSED"}
    return {"status": "READY"}


def _canonical_plan_line(case: dict[str, Any]) -> str:
    parts = [f"- **{case['id']}** — {case['title']}",
             f"origin: canonical | status: `{case['status']}`",
             f"automation: {case.get('automation_suitability') or 'n/a'}/{case.get('automation_layer') or 'n/a'}"]
    if case.get("source_identifiers"):
        parts.append("requirements: " + ", ".join(case["source_identifiers"]))
    return " — ".join(parts)


def _ch_plan_line(case: dict[str, Any]) -> str:
    lines = [f"- **{case['id']}** — {case['title']}  ", f"  origin: challenge | status: `{case['status']}` | tags: `{'/'.join(case['execution_tags'])}`"]
    if case.get("rationale"):
        lines.append(f"  why: {case['rationale']}")
    if case.get("related_test_cases"):
        lines.append(f"  related canonical tests: {', '.join(case['related_test_cases'])}")
    if case.get("related_source_identifiers"):
        lines.append(f"  related requirements: {', '.join(case['related_source_identifiers'])}")
    if case.get("required_resources"):
        lines.append(f"  required resources: {', '.join(case['required_resources'])}")
    if case.get("environment_requirements"):
        lines.append(f"  environment: {', '.join(case['environment_requirements'])}")
    if case.get("preconditions"):
        lines.append(f"  preconditions: {'; '.join(case['preconditions'])}")
    for step in case.get("steps", []):
        lines.append(f"  step {step['step']}: {step['action']} → {step.get('expected_result') or '(unresolved)'}")
    if case.get("evidence_refs"):
        cites = ", ".join(f"{ref.get('source')} ({ref.get('reference')})" for ref in case["evidence_refs"])
        lines.append(f"  evidence to collect: {cites}")
    for unknown in case.get("unknowns", []):
        blocker = f"  blocker: {unknown['kind']} — {unknown['detail']}"
        if unknown.get("question"):
            blocker += f" (see {unknown['question']})"
        lines.append(blocker)
    return "\n".join(lines)


def render_manual_plan(canonical: dict[str, Any], ch_cases: list[dict[str, Any]]) -> str:
    buckets: dict[str, list[str]] = {key: [] for key, _ in PLAN_SECTIONS}
    for case in canonical["cases"]:
        manual_like = case.get("automation_suitability") in {"LOW", "MANUAL_ONLY"}
        hardware_like = case.get("automation_layer") in {"HARDWARE", "MIXED"}
        blocked_like = case["status"] in {"BLOCKED_EXTERNAL_DEPENDENCY", "EXPLORATORY", "NEEDS_REVIEW"}
        if manual_like or hardware_like or blocked_like:
            bucket = "physical_device" if hardware_like else (
                "blocked" if case["status"] == "BLOCKED_EXTERNAL_DEPENDENCY" else (
                    "exploratory" if case["status"] == "EXPLORATORY" else "manual_operational"
                )
            )
            buckets[bucket].append(_canonical_plan_line(case))
    for case in ch_cases:
        bucket = _plan_bucket(case["execution_tags"], case.get("status", ""))
        buckets[bucket].append(_ch_plan_line(case))
    lines = ["# Manual / Physical / Field Test Plan", ""]
    for key, heading in PLAN_SECTIONS:
        lines.append(f"## {heading}")
        lines.append("")
        lines.extend(buckets[key] or ["_None._"])
        lines.append("")
    gaps = [case for case in ch_cases if case.get("canonical_gap_candidate")]
    lines.append("## Potential canonical gaps")
    lines.append("")
    if gaps:
        for case in gaps:
            gap = case["canonical_gap_candidate"]
            lines.append(f"- **{case['id']}** — {case['title']}: {gap['why_normative']} "
                         f"(evidence: {gap['authority_evidence']}). Recommended action: review and, if accepted, "
                         "run a new canonical generation; this challenge run does not modify the frozen suite.")
    else:
        lines.append("_None._")
    lines.append("")
    return "\n".join(lines)


def finalize_challenge(
    run_dir: Path, challenge_id: str, *, azure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    lineage = _lineage(challenge_dir)
    if lineage["status"] == "STARTED":
        raise ChallengeError(f"challenge {challenge_id!r} was not submitted yet")
    if lineage["status"] == "FINALIZED":
        raise ChallengeError(f"challenge {challenge_id!r} is already finalized; start a new challenge_id to redo it")
    _require_parent_unchanged(challenge_dir, run_dir)
    result = read_json(challenge_dir / "challenge-result.json")
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    for case in result["cases"]:
        case.update(classify_challenge_case(case))
    write_json(challenge_dir / "challenge-cases.json", {"cases": result["cases"]})
    write_json(challenge_dir / "seed-dispositions.json", {"seed_dispositions": result["seed_dispositions"]})
    plan = render_manual_plan(canonical, result["cases"])
    (challenge_dir / "challenge-plan.md").write_text(plan, encoding="utf-8")
    files = ["challenge-cases.json", "seed-dispositions.json", "challenge-plan.md"]
    # Marked FINALIZED before the (optional) Azure package build, which reads this
    # challenge run's own finalized state back from disk like any other consumer would.
    lineage.update({"status": "FINALIZED", "finalized_at": now(), "outputs": files})
    write_json(challenge_dir / "challenge-run.json", lineage)
    if azure:
        import azure_export
        # Reuses the shared canonical+Challenge packaging path, scoped to just this
        # chaos run, so a CH case is previewed with its stable chaos:<id>:CH-nnn
        # export key and never collides with another challenge run's own CH-001.
        package = azure_export.build_export_package(run_dir, chaos_ids=[challenge_id])
        state = azure_export.migrate_integration_state(azure_export.load_integration_state(run_dir))
        preview = azure_export.preview_export(
            package, project=azure["project"], plan=azure["plan"], suite=azure["suite"],
            mapping={"test_cases": state.get("test_cases", {})},
        )
        write_json(challenge_dir / "azure-devops-preview.json", preview)
        files.append("azure-devops-preview.json")
    lineage.update({"outputs": files})  # picks up azure-devops-preview.json when it was produced above
    write_json(challenge_dir / "challenge-run.json", lineage)
    published = publish_outputs(run_dir, challenge_id, lineage.get("formats") or ["JSON", "MARKDOWN", "HTML"])
    return {"challenge_dir": str(challenge_dir), "files": files, "cases": len(result["cases"]),
            "published": [str(path) for path in published]}


def _inline_html(text: str) -> str:
    import html
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<![\w*])_(.+?)_(?![\w*])", r"<em>\1</em>", escaped)
    return escaped


def plan_html(markdown: str, title: str) -> str:
    """Self-contained, offline HTML for the Manual/Physical/Field plan (its own small
    heading/bullet/paragraph Markdown subset; no external assets)."""
    import html
    body: list[str] = []
    in_list = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_html(stripped[2:])}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            body.append(f"<h{level}>{_inline_html(stripped[level:].strip())}</h{level}>")
        elif stripped:
            body.append(f"<p>{_inline_html(stripped)}</p>")
    if in_list:
        body.append("</ul>")
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>"
        ":root{--bg:#fff;--fg:#1d2330;--muted:#5b6475;--line:#d9dee7}"
        "@media (prefers-color-scheme: dark){:root{--bg:#14171d;--fg:#e6e9ef;--muted:#a3abba;--line:#2c323d}}"
        "body{margin:0 auto;max-width:960px;padding:24px 16px;background:var(--bg);color:var(--fg);"
        "font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}"
        "h1{font-size:1.6rem}h2{font-size:1.15rem;margin-top:2rem;border-bottom:1px solid var(--line);"
        "padding-bottom:.3rem}li{margin:.35rem 0}em{color:var(--muted)}"
        "</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n"
    )


def publish_outputs(run_dir: Path, challenge_id: str, formats: list[str]) -> list[Path]:
    """Public, local chaos outputs under `<artifact_root>/output/chaos/<id>/` in the
    requested formats. The private challenge state stays under the run."""
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    run = read_json(run_dir / "run.json")
    destination = Path(run["artifact_root"]) / "output" / "chaos" / challenge_id
    destination.mkdir(parents=True, exist_ok=True)
    selected = {str(value).upper() for value in formats}
    written: list[Path] = []
    if "JSON" in selected:
        cases = read_json(challenge_dir / "challenge-cases.json")
        dispositions = read_json(challenge_dir / "seed-dispositions.json")
        write_json(destination / "chaos-cases.json", {"chaos_run_id": challenge_id, **cases})
        write_json(destination / "seed-dispositions.json", dispositions)
        written += [destination / "chaos-cases.json", destination / "seed-dispositions.json"]
    plan = (challenge_dir / "challenge-plan.md").read_text(encoding="utf-8")
    if "MARKDOWN" in selected:
        (destination / "chaos-plan.md").write_text(plan, encoding="utf-8")
        written.append(destination / "chaos-plan.md")
    if "HTML" in selected:
        (destination / "chaos-plan.html").write_text(plan_html(plan, f"Chaos plan — {challenge_id}"), encoding="utf-8")
        written.append(destination / "chaos-plan.html")
    return written


def verify_challenge(run_dir: Path, challenge_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    digest = _require_parent_unchanged(challenge_dir, run_dir)
    result_path = challenge_dir / "challenge-result.json"
    if not result_path.is_file():
        return {"verified": True, "parent_canonical_digest": digest, "cases": 0, "status": _lineage(challenge_dir)["status"]}
    result = read_json(result_path)
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    known_case_ids = {case["id"] for case in canonical["cases"]}
    for case in result["cases"]:
        unresolved = [ref for ref in case["related_test_cases"] if ref not in known_case_ids]
        if unresolved:
            raise ChallengeError(f"{case['id']} references Test Cases no longer in the parent suite: {unresolved}")
    return {"verified": True, "parent_canonical_digest": digest, "cases": len(result["cases"])}


# --- CLI -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Post-suite semantic challenge over a frozen canonical run.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--run", required=True)
    start.add_argument("--challenge-id", required=True)
    start.add_argument("--seed", action="append", default=[], help="path to a Markdown seed file (repeatable)")
    start.add_argument("--focus", default="")

    lookup = sub.add_parser("lookup")
    lookup.add_argument("--run", required=True)
    lookup.add_argument("--challenge-id", required=True)
    lookup.add_argument("--source", required=True)
    lookup.add_argument("--query")
    lookup.add_argument("--lines", help="A-B line range")

    submit = sub.add_parser("submit")
    submit.add_argument("--run", required=True)
    submit.add_argument("--challenge-id", required=True)
    submit.add_argument("--file", required=True)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run", required=True)
    finalize.add_argument("--challenge-id", required=True)
    finalize.add_argument("--azure-project")
    finalize.add_argument("--azure-plan")
    finalize.add_argument("--azure-suite")

    verify = sub.add_parser("verify")
    verify.add_argument("--run", required=True)
    verify.add_argument("--challenge-id", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start_challenge(args.run, args.challenge_id, seeds=[Path(p) for p in args.seed], focus=args.focus)
        elif args.command == "lookup":
            line_start = line_end = None
            if args.lines:
                start_text, _, end_text = args.lines.partition("-")
                line_start, line_end = int(start_text), int(end_text or start_text)
            result = lookup_evidence(args.run, args.challenge_id, args.source, query=args.query,
                                     line_start=line_start, line_end=line_end)
        elif args.command == "submit":
            result = submit_challenge(args.run, args.challenge_id, read_json(args.file))
        elif args.command == "finalize":
            azure = None
            if args.azure_project:
                azure = {"project": args.azure_project, "plan": args.azure_plan, "suite": args.azure_suite}
            result = finalize_challenge(args.run, args.challenge_id, azure=azure)
        else:
            result = verify_challenge(args.run, args.challenge_id)
    except (StageError, ChallengeError) as exc:
        print(json.dumps({"errors": getattr(exc, "errors", [str(exc)])}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
