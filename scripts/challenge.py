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
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import StageError, file_digest, jaccard, normalize_identifier, now, read_json, similarity, write_json
from design import check_locale, unknown_keys
from procedures import (
    ABSTRACT_ACTION, ABSTRACT_OBSERVATION, AUTH_ONLY, GENERIC_PRECONDITION, PLACEHOLDER,
    SUITABILITY, compressed_action, hidden_subtest,
)
import pipeline


class ChallengeError(ValueError):
    """A challenge run tried to act on a parent that is not frozen, or one it no longer matches."""


DISCOVERIES = ("HUMAN_SEEDED", "MODEL_DERIVED", "HUMAN_AND_MODEL")
SEED_DISPOSITIONS = ("MATERIALIZED", "ALREADY_COVERED", "MERGED", "QUESTIONED", "NOT_APPLICABLE")
EXECUTION_TAGS = (
    "AUTOMATABLE", "MANUAL", "PHYSICAL_DEVICE", "EXTERNAL_ENVIRONMENT", "EXPLORATORY", "CHAOS_RECOVERY",
)
CASE_FIELDS = {
    "key", "title", "discovery", "inspired_by", "related_test_cases", "related_source_identifiers",
    "related_findings", "related_questions", "rationale", "execution_tags", "automation_suitability",
    "priority", "required_resources", "environment_requirements", "preconditions", "test_data", "steps",
    "postconditions", "evidence_refs", "unknowns", "canonical_gap_candidate", "notes",
}
PAYLOAD_KEYS = {"cases", "seed_dispositions"}
# Same material/automation-only unknown vocabulary as procedures.py; challenge cases are
# graded on the same honesty standard, not a looser one.
from procedures import MATERIAL_UNKNOWNS, AUTOMATION_UNKNOWNS, PATH_UNKNOWNS  # noqa: E402


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


def _require_parent_unchanged(challenge_dir: Path, run_dir: Path) -> str:
    """Contract 1: canonical immutability. Every challenge action re-checks this."""
    lineage = read_json(challenge_dir / "challenge-run.json")
    current = _canonical_digest(run_dir)
    if current != lineage["parent_canonical_digest"]:
        raise ChallengeError(
            "the parent canonical suite changed since this challenge run started; "
            "a challenge never adapts to a moving parent, start a new challenge run"
        )
    return current


# --- start ---------------------------------------------------------------------------

def start_challenge(
    run_dir: Path, challenge_id: str, *, seeds: list[Path] | None = None, focus: str = "",
) -> dict[str, Any]:
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
        seed_files.append({
            "path": seed_path.name, "digest": file_digest(seed_path), "content": content,
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
        "source_identifiers": case.get("source_identifiers", []),
        "failure_domain": case.get("failure_domain"),
    } for case in canonical["cases"]]
    work_order = {
        "parent_run_id": read_json(run_dir / "run.json")["run_id"],
        "challenge_run_id": challenge_id,
        "parent_canonical_digest": file_digest(run_dir / "canonical-suite.json"),
        "output_locale": canonical["index"].get("output_locale"),
        "focus": focus,
        "seeds": seed_files,
        "canonical_cases": cases_index,
        "requirements": [
            {"id": r["id"], "source_identifier": r["source_identifier"], "title": r.get("source_title")}
            for r in canonical["index"]["requirements"]
        ],
        "findings": [{"id": f["id"], "statement": f["statement"]} for f in canonical["index"]["findings"]],
        "questions": [{"id": q["id"], "question": q["question"]} for q in canonical["questions"]["questions"]],
        "evidence_index": evidence_index,
        "instructions": (
            "Read the frozen canonical suite, findings and questions above; read the seed files if any "
            "(inspiration, never authority — do not promote an unsupported seed rule to a normative test). "
            "Analyze every meaningful seed idea and disposition it (seed_dispositions), then go beyond the "
            "seeds using the project's own actors, rules, states, integrations, devices and evidence: "
            "operator mistakes, physical/digital mismatches, interruption and recovery, concurrency, "
            "long-running operation, manual-after-automatic sequences, and anything else this project's "
            "own evidence supports. A CH case is not a canonical Test Case: it may be exploratory, physical, "
            "manual, or blocked, and it must say so honestly rather than invent a screen, device or oracle. "
            "Submit `python scripts/challenge.py submit --run <run> --challenge-id "
            f"{challenge_id} --file <payload.json>`, then `finalize`."
        ),
    }
    challenge_dir.mkdir(parents=True, exist_ok=True)
    write_json(challenge_dir / "work-order.json", work_order)
    write_json(challenge_dir / "challenge-run.json", {
        "challenge_run_id": challenge_id, "parent_run_id": work_order["parent_run_id"],
        "parent_canonical_digest": work_order["parent_canonical_digest"],
        "seed_refs": [{"path": s["path"], "digest": s["digest"]} for s in seed_files],
        "focus": focus, "created_at": now(), "status": "STARTED",
    })
    return {"challenge_dir": str(challenge_dir), "work_order": str(challenge_dir / "work-order.json"),
            "seeds_received": len(seed_files), "canonical_cases": len(cases_index)}


# --- submit ----------------------------------------------------------------------------

def _validate_steps(steps: list[dict[str, Any]], label: str, locale: str, errors: list[str]) -> list[dict[str, Any]]:
    normalized = []
    for number, step in enumerate(steps, 1):
        action, expected = _text(step.get("action")), _text(step.get("expected_result"))
        if not action:
            errors.append(f"{label} step {number} requires an action")
        if ABSTRACT_ACTION.search(action):
            errors.append(f"{label} step {number} action is abstract; name the concrete operation")
        if expected and ABSTRACT_OBSERVATION.search(expected):
            errors.append(f"{label} step {number} expected result is not observable")
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


def validate_challenge_payload(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, PAYLOAD_KEYS, "challenge")
    locale = context["locale"]
    known_case_ids = set(context["case_ids"])
    known_identifiers = set(context["identifiers"])
    known_finding_ids = set(context["finding_ids"])
    known_question_ids = set(context["question_ids"])
    seed_paths = set(context["seed_paths"])
    seed_hits: set[str] = set()
    cases: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(payload.get("cases", []) or [], 1):
        key = _text(item.get("key")) or f"<case {index}>"
        label = f"challenge case {key}"
        if key in seen_keys:
            errors.append(f"{label} key is supplied twice")
        seen_keys.add(key)
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
            seed_name = ref.split("#", 1)[0]
            if seed_name not in seed_paths:
                errors.append(f"{label} inspired_by {ref!r} does not name a seed file passed to this challenge run")
            else:
                seed_hits.add(seed_name)
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
        unsupported = sorted(set(tags) - set(EXECUTION_TAGS))
        if unsupported:
            errors.append(f"{label} execution_tags {unsupported} are not supported")
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
        steps = item.get("steps", []) or []
        normalized_steps = []
        if steps:
            if not evidence_refs and not any(u["kind"] in PATH_UNKNOWNS for u in unknowns):
                errors.append(
                    f"{label} has steps but no evidence_refs; cite the execution path or declare "
                    "MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH"
                )
            normalized_steps = _validate_steps(steps, label, locale, errors)
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
    dispositions = []
    disposition_hits: set[str] = set()
    for item in payload.get("seed_dispositions", []) or []:
        seed = _text(item.get("seed"))
        disposition = _text(item.get("disposition"))
        if seed not in seed_paths:
            errors.append(f"seed_dispositions references unknown seed file {seed!r}")
        else:
            disposition_hits.add(seed)
        if disposition not in SEED_DISPOSITIONS:
            errors.append(f"seed_dispositions for {seed!r} must use one of {SEED_DISPOSITIONS}")
        dispositions.append({
            "seed": seed, "disposition": disposition, "summary": _text(item.get("summary")),
            "cases": [_text(v) for v in item.get("cases", []) or [] if _text(v)],
        })
    missing_disposition = sorted(seed_paths - disposition_hits)
    if missing_disposition:
        errors.append(f"every seed file needs at least one seed_disposition entry; missing: {missing_disposition}")
    if errors:
        raise StageError("challenge", errors)
    targeted_source_lookups = len({(ref.get("source"), ref.get("reference")) for case in cases for ref in case["evidence_refs"]})
    return {
        "cases": cases, "seed_dispositions": dispositions,
        "diagnostics": {
            "seed_items_received": len(seed_paths),
            "challenge_cases_generated": len(cases),
            "model_derived_cases": sum(c["discovery"] == "MODEL_DERIVED" for c in cases),
            "human_seeded_cases": sum(c["discovery"] in {"HUMAN_SEEDED", "HUMAN_AND_MODEL"} for c in cases),
            "seed_items_materialized": sum(d["disposition"] == "MATERIALIZED" for d in dispositions),
            "seed_items_already_covered": sum(d["disposition"] == "ALREADY_COVERED" for d in dispositions),
            "seed_items_merged": sum(d["disposition"] == "MERGED" for d in dispositions),
            "seed_items_questioned": sum(d["disposition"] == "QUESTIONED" for d in dispositions),
            "seed_items_not_applicable": sum(d["disposition"] == "NOT_APPLICABLE" for d in dispositions),
            "canonical_gap_candidates": sum(c["canonical_gap_candidate"] is not None for c in cases),
            "targeted_source_lookups": targeted_source_lookups, "full_source_rereads": 0,
        },
    }


def submit_challenge(run_dir: Path, challenge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    if not challenge_dir.is_dir():
        raise ChallengeError(f"challenge {challenge_id!r} was not started; run start first")
    _require_parent_unchanged(challenge_dir, run_dir)
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    lineage = read_json(challenge_dir / "challenge-run.json")
    context = {
        "locale": canonical["index"].get("output_locale") or "en",
        "case_ids": {case["id"] for case in canonical["cases"]},
        "identifiers": {normalize_identifier(v) for case in canonical["cases"] for v in case.get("source_identifiers", [])}
        | {normalize_identifier(r["source_identifier"]) for r in canonical["index"]["requirements"]},
        "finding_ids": {f["id"] for f in canonical["index"]["findings"]},
        "question_ids": {q["id"] for q in canonical["questions"]["questions"]},
        "seed_paths": {ref["path"] for ref in lineage["seed_refs"]},
    }
    result = validate_challenge_payload(payload, context)
    for index, case in enumerate(result["cases"], 1):
        case["id"] = f"CH-{index:03d}"
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
    if "MANUAL" in tags:
        return "manual_operational"
    return "manual_operational"


PLAN_SECTIONS = (
    ("physical_device", "Physical device tests"),
    ("external_environment", "External environment / integrator tests"),
    ("manual_operational", "Manual operational tests"),
    ("chaos_recovery", "Chaos / recovery"),
    ("exploratory", "Exploratory tests"),
    ("blocked", "Blocked tests and prerequisites"),
)


def render_manual_plan(canonical: dict[str, Any], ch_cases: list[dict[str, Any]]) -> str:
    buckets: dict[str, list[str]] = {key: [] for key, _ in PLAN_SECTIONS}
    for case in canonical["cases"]:
        if case.get("automation_suitability") in {"LOW", "MANUAL_ONLY"} or case["status"] in {
            "BLOCKED_EXTERNAL_DEPENDENCY", "EXPLORATORY", "NEEDS_REVIEW",
        }:
            bucket = "blocked" if case["status"] == "BLOCKED_EXTERNAL_DEPENDENCY" else (
                "exploratory" if case["status"] == "EXPLORATORY" else "manual_operational"
            )
            buckets[bucket].append(
                f"- **{case['id']}** — {case['title']} (`{case['status']}`, canonical, {case.get('automation_layer') or 'n/a'})"
            )
    for case in ch_cases:
        bucket = _plan_bucket(case["execution_tags"], case.get("status", ""))
        line = f"- **{case['id']}** — {case['title']} (`{'/'.join(case['execution_tags'])}`)"
        if case.get("related_test_cases"):
            line += f" — related: {', '.join(case['related_test_cases'])}"
        buckets[bucket].append(line)
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
    if not challenge_dir.is_dir():
        raise ChallengeError(f"challenge {challenge_id!r} was not started")
    _require_parent_unchanged(challenge_dir, run_dir)
    result_path = challenge_dir / "challenge-result.json"
    if not result_path.is_file():
        raise ChallengeError(f"challenge {challenge_id!r} was not submitted yet")
    result = read_json(result_path)
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    for case in result["cases"]:
        case.setdefault("status", "READY" if not case["unknowns"] else "NEEDS_REVIEW")
    write_json(challenge_dir / "challenge-cases.json", {"cases": result["cases"]})
    write_json(challenge_dir / "seed-dispositions.json", {"seed_dispositions": result["seed_dispositions"]})
    plan = render_manual_plan(canonical, result["cases"])
    (challenge_dir / "challenge-plan.md").write_text(plan, encoding="utf-8")
    files = ["challenge-cases.json", "seed-dispositions.json", "challenge-plan.md"]
    if azure:
        from integrations.azure_devops import build_preview
        azure_cases = [{
            "id": case["id"], "title": case["title"], "priority": case["priority"],
            "preconditions": case["preconditions"],
            "steps": [{"action": s["action"], "expected_result": s["expected_result"]} for s in case["steps"]],
            "tags": case["execution_tags"],
            "requirement_refs": case["related_source_identifiers"], "coverage_point_refs": [],
            "status": case["status"], "automation_suitability": case.get("automation_suitability"),
            "automation_readiness": None,
        } for case in result["cases"]]
        preview = build_preview(
            azure_cases, azure.get("mapping", {}), project=azure["project"], plan=azure["plan"],
            suite=azure["suite"], include_needs_review=azure.get("include_needs_review", True),
        )
        write_json(challenge_dir / "azure-devops-preview.json", preview)
        files.append("azure-devops-preview.json")
    lineage = read_json(challenge_dir / "challenge-run.json")
    lineage.update({"status": "FINALIZED", "finalized_at": now(), "outputs": files})
    write_json(challenge_dir / "challenge-run.json", lineage)
    return {"challenge_dir": str(challenge_dir), "files": files, "cases": len(result["cases"])}


def verify_challenge(run_dir: Path, challenge_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    challenge_dir = _challenge_dir(run_dir, challenge_id)
    digest = _require_parent_unchanged(challenge_dir, run_dir)
    result = read_json(challenge_dir / "challenge-result.json")
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
