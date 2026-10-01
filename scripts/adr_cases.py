#!/usr/bin/env python3
"""FTD ADR resulting Test Cases: complete executable procedures for every UPDATE / CREATE.

Procedures go through `procedures.validate_procedures` — the very gate canonical Test Cases
pass — with the ADR designs as the designed tests. ADR adds one stricter check, never a weaker
one: a URL, route, selector or quoted message in a procedure must appear in the selected evidence
(the ADR material, the parent's evidence snapshot or the case's previous definition); otherwise
the procedure declares MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH and the case is not READY.
Each resulting case is assembled in the canonical shape and checked against the public Test Case
schema; an updated case also gets a field-level before/after record of its persisted definition.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from common import StageError, normalize, stable_digest
from design import unknown_keys
import procedures as procedure_stage

ROUTE = re.compile(r"https?://[^\s\"'<>)]+|(?<![\w/.])/[A-Za-z0-9_\-{}.:]+(?:/[A-Za-z0-9_\-{}.:]*)*")
SELECTOR = re.compile(r"\b(?:data-testid|data-test|aria-label|testid)\s*=\s*[\"']?[\w\-:. ]+|(?<![\w&])#[A-Za-z][\w\-]*")
QUOTED = re.compile(r"\"([^\"]{2,})\"|“([^”]{2,})”")
DEFINITION_FIELDS = ("title", "objective", "status", "priority", "type", "requirement_refs", "preconditions",
                     "test_data", "steps", "postconditions", "cleanup", "state_contract", "automation_suitability",
                     "automation_readiness", "readiness_blockers", "automation_layer", "automation_tool_hint",
                     "execution_variants", "request_contract", "question_refs", "finding_refs", "failure_domain",
                     "test_basis", "primary_type", "tags", "notes")


def _squash(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def invented_literals(texts: list[str], corpus: str) -> list[str]:
    """Technical literals a procedure states that no selected evidence contains."""
    found = []
    for text in texts:
        literals = [m.group(0) for m in ROUTE.finditer(text)] + [m.group(0) for m in SELECTOR.finditer(text)]
        literals += [m.group(1) or m.group(2) for m in QUOTED.finditer(text)]
        found += [lit for lit in literals if _squash(lit.rstrip(".,;:")) not in corpus]
    return list(dict.fromkeys(found))


def build_cases(payload: dict[str, Any], analysis: dict[str, Any], base: dict[str, Any],
                context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, {"procedures"}, "ADR procedures")
    writes = [e for e in analysis["test_cases"] if e["action"] in {"UPDATE", "CREATE"}]
    by_id = {c["id"]: c for c in base["cases"]}
    locale = base["output_locale"]
    new_questions = analysis["questions"]
    resolved = {d["question"] for d in analysis["question_dispositions"] if d["disposition"] == "RESOLVED_BY_ADR"} | \
        {q for q, items in base["question_dispositions"].items() if items[-1]["disposition"] == "RESOLVED_BY_ADR"}
    question_keys = {q["id"] for q in base["questions"]} | {q["key"] for q in new_questions} | {q["id"] for q in new_questions}
    blocking = {q["id"] for q in base["questions"] if q["blocking"] and q["id"] not in resolved}
    blocking |= {q["key"] for q in new_questions if q["blocking"]} | {q["id"] for q in new_questions if q["blocking"]}
    tests, blocking_by_test = [], {}
    for entry in writes:
        design = entry["design"]
        tests.append({"key": entry["key"] or entry["id"], "id": entry["id"], "title": design["title"],
                      "trigger": design["trigger"], "objective": design["objective"], "expected": design["expected"],
                      "basis": design["basis"], "primary_type": design["primary_type"]})
        linked = {q["id"] for q in new_questions if entry["id"] in q["tests"] and q["blocking"]}
        previous = by_id.get(entry["id"], {})
        linked |= set(previous.get("question_refs", [])) & blocking
        blocking_by_test[entry["id"]] = bool(linked)
    adr_texts, parent_texts = context["adr_texts"], context["parent_texts"]
    validated: dict[str, Any] = {}
    try:
        validated = procedure_stage.validate_procedures(payload, {
            "locale": locale, "tests": tests, "question_keys": sorted(question_keys),
            "blocking_by_test": blocking_by_test, "blocking_questions": blocking,
            "source_tokens": procedure_stage.source_vocabulary([*adr_texts.values(), *parent_texts.values()]),
        })["procedures"]
    except StageError as exc:
        errors.extend(exc.errors)
    known_sources = {**parent_texts, **adr_texts}
    corpus = _squash(" ".join(known_sources.values()))
    for item in payload.get("procedures", []) or []:
        ref = str(item.get("test") or "")
        entry = next((e for e in writes if ref in {e["id"], e["key"]}), None)
        label = f"procedure for {ref or '<missing>'}"
        for evidence in [r for r in item.get("evidence_refs", []) or [] if isinstance(r, dict)]:
            source = str(evidence.get("source", ""))
            if source not in known_sources:
                errors.append(f"{label} evidence_refs source {source!r} is neither an ADR file nor a parent source")
                continue
            start, end = evidence.get("line_start"), evidence.get("line_end", evidence.get("line_start"))
            total = len(known_sources[source].splitlines())
            if start is not None and not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= total):
                errors.append(f"{label} evidence_refs {source}:{start}-{end} is not a valid line range ({total} lines)")
        if entry is None:
            continue
        own = corpus + " " + _squash(json.dumps(by_id.get(entry["id"], {}), ensure_ascii=False))
        texts = [str(v) for v in item.get("preconditions", []) or []]
        texts += [f"{s.get('action', '')} {s.get('expected_result') or ''}" for s in item.get("steps", []) or []]
        contract = item.get("request_contract") if isinstance(item.get("request_contract"), dict) else {}
        texts += [str(contract.get(field) or "") for field in ("endpoint", "body")]
        invented = invented_literals(texts, own)
        if invented:
            errors.append(f"{label} states {invented}, which no selected evidence contains; never invent a route, "
                          "selector, URL or message — cite it, or keep the step's intent and declare "
                          "MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH")
    cases, changes = {}, {}
    if errors:
        return {"errors": errors, "cases": cases, "changes": changes}
    allocations = _new_structures(writes, analysis, base)
    for entry in writes:
        procedure = validated[entry["id"]]
        case = assemble(entry, procedure, by_id.get(entry["id"]), analysis, base, allocations)
        _schema(case, f"resulting {entry['id']}", errors)
        cases[entry["id"]] = case
        if entry["action"] == "UPDATE":
            changes[entry["id"]] = change_record(by_id[entry["id"]], case)
    return {"errors": errors, "cases": cases, "changes": changes, "procedures": validated,
            "new_scenarios": allocations["scenarios"], "new_coverage_points": allocations["coverage_points"]}


def _new_structures(writes: list[dict[str, Any]], analysis: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Scenario families and coverage points a CREATE needs, continuing the project numbering."""
    from adr_contract import next_ids
    scenarios = {normalize(s.get("title")): s["id"] for s in base["scenarios"]}
    new_scenarios: list[dict[str, Any]] = []
    points = {p.get("adr_decision"): p["id"] for p in base["coverage_points"] if p.get("adr_decision")}
    new_points: list[dict[str, Any]] = []
    decisions = {d["id"]: d for d in [*base["decisions"], *analysis["decisions"]]}
    for entry in writes:
        if entry["action"] != "CREATE":
            continue
        family = normalize(entry["design"]["family"])
        if family not in scenarios:
            scenarios[family] = next_ids("SCN-", [s["id"] for s in [*base["scenarios"], *new_scenarios]], 1)[0]
            new_scenarios.append({"id": scenarios[family], "title": entry["design"]["family"], "type": "SCENARIO_FAMILY",
                                  "requirement_refs": [], "coverage_point_refs": [], "test_case_refs": []})
        for decision_id in entry["decisions"]:
            if decision_id not in points:
                points[decision_id] = next_ids("CP-", [p["id"] for p in [*base["coverage_points"], *new_points]], 1)[0]
                decision = decisions[decision_id]
                new_points.append({"id": points[decision_id],
                                   "requirement_ref": (analysis["requirements_of"].get(decision_id) or [None])[0],
                                   "statement": decision["statement"], "clause_refs": [],
                                   "source_refs": [{"source": decision["source"], "reference": decision["reference"]}],
                                   "disposition": "TEST_CASE", "target_refs": [], "adr_decision": decision_id})
    return {"scenario_of": scenarios, "scenarios": new_scenarios, "point_of": points, "coverage_points": new_points}


def assemble(entry: dict[str, Any], procedure: dict[str, Any], previous: dict[str, Any] | None,
             analysis: dict[str, Any], base: dict[str, Any], allocations: dict[str, Any]) -> dict[str, Any]:
    """The complete resulting Test Case, in the canonical shape (the same fields build_canonical writes)."""
    design = entry["design"]
    decisions = {d["id"]: d for d in [*base["decisions"], *analysis["decisions"]]}
    requirements = {r["id"]: r for r in [*base["requirements"], *base["adr_requirements"], *analysis["new_requirements"]]}
    decision_reqs = [r for d in entry["decisions"] for r in analysis["requirements_of"].get(d, [])]
    requirement_refs = list(dict.fromkeys([*(previous or {}).get("requirement_refs", []), *decision_reqs]))
    identifiers = list(dict.fromkeys(requirements[r]["source_identifier"] for r in requirement_refs
                                     if requirements.get(r, {}).get("source_identifier")))
    resolved = {d["question"] for d in analysis["question_dispositions"] if d["disposition"] == "RESOLVED_BY_ADR"}
    question_ids = {q["key"]: q["id"] for q in analysis["questions"]}
    questions = [q for q in (previous or {}).get("question_refs", []) if q not in resolved]
    questions += [q["id"] for q in analysis["questions"] if entry["id"] in q["tests"]]
    questions += [question_ids.get(u["question"], u["question"]) for u in procedure["unknowns"] if u["question"]]
    findings = list((previous or {}).get("finding_refs", [])) + [f["id"] for f in analysis["findings"] if entry["id"] in f["tests"]]
    decision_refs = [{"source": decisions[d]["source"], "reference": decisions[d]["reference"]} for d in entry["decisions"]]
    source_refs = []
    for ref in [*decision_refs, *(previous or {}).get("source_refs", []), *procedure.get("evidence_refs", [])]:
        clean = {"source": str(ref.get("source")), "reference": str(ref.get("reference") or ref.get("locator") or "")}
        if clean["reference"] and clean not in source_refs:
            source_refs.append(clean)
    if previous:
        scenario_refs, point_refs = previous["scenario_refs"], previous["coverage_point_refs"]
    else:
        scenario_refs = [allocations["scenario_of"][normalize(design["family"])]]
        point_refs = list(dict.fromkeys(allocations["point_of"][d] for d in entry["decisions"]))
    case = {
        "schema_version": "2.2", "id": entry["id"], "title": design["title"], "status": procedure["status"],
        "priority": design["priority"], "type": design["primary_type"], "objective": design["objective"],
        "requirement_refs": requirement_refs, "scenario_refs": scenario_refs, "coverage_point_refs": point_refs,
        "source_refs": source_refs, "preconditions": procedure["preconditions"], "test_data": procedure["test_data"],
        "steps": procedure["steps"], "postconditions": procedure["postconditions"], "cleanup": procedure["cleanup"],
        "state_contract": procedure_stage.state_contract(procedure["cleanup"]), "tags": identifiers,
        "notes": procedure["notes"] + [f"{u['kind']}: {u['detail']}" for u in procedure["unknowns"]],
        "test_basis": design["basis"], "primary_type": design["primary_type"],
        "secondary_tags": list((previous or {}).get("secondary_tags", [])), "execution_status": procedure["status"],
        "question_refs": sorted(set(questions)), "finding_refs": sorted(set(findings)),
        "composes": list((previous or {}).get("composes", [])),
        "automation_candidate": procedure["automation_suitability"] in {"HIGH", "MEDIUM"},
        "automation_layer": procedure["automation_layer"], "automation_tool_hint": procedure["automation_tool_hint"],
        "deterministic": design["basis"] != "EXPLORATORY", "priority_reason": design["priority_reason"],
        "automation_suitability": procedure["automation_suitability"],
        "automation_readiness": procedure["automation_readiness"], "readiness_blockers": procedure["readiness_blockers"],
        "failure_domain": design["failure_domain"], "source_identifiers": identifiers,
    }
    if previous and previous.get("claim_exercise_map"):
        case["claim_exercise_map"] = copy.deepcopy(previous["claim_exercise_map"])
    for field in ("execution_variants", "request_contract"):
        if procedure.get(field):
            case[field] = procedure[field]
    if design.get("dimension"):
        case["expansion_dimension"] = design["dimension"]
    if procedure.get("single_step_reason"):
        case["single_step_reason"] = procedure["single_step_reason"]
    return case


def _schema(case: dict[str, Any], label: str, errors: list[str]) -> None:
    import validation
    validation.validate_schema(case, "test-case.schema.json", label, errors)


def change_record(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Field-level before/after of the persisted definitions — never reconstructed from prose."""
    changed, unchanged, fields = [], [], {}
    for field in DEFINITION_FIELDS:
        if before.get(field) == after.get(field):
            unchanged.append(field)
            continue
        changed.append(field)
        fields[field] = {"before": before.get(field), "after": after.get(field)}
    steps = []
    old, new = before.get("steps", []), after.get("steps", [])
    for number in range(1, max(len(old), len(new)) + 1):
        a = old[number - 1] if number <= len(old) else None
        b = new[number - 1] if number <= len(new) else None
        if a is None or b is None:
            steps.append({"step": number, "change": "ADDED" if a is None else "REMOVED"})
        else:
            parts = [p for p in ("action", "expected_result") if a.get(p) != b.get(p)]
            if parts:
                steps.append({"step": number, "change": "CHANGED", "parts": parts})
    return {"changed": changed, "unchanged": unchanged, "fields": fields, "steps": steps,
            "previous_definition_digest": stable_digest(before), "effective_definition_digest": stable_digest(after)}
