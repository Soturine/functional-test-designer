#!/usr/bin/env python3
"""Stage B: expand each frozen test intent into an executable procedure, then classify
human readiness and automation separately.

READY never requires fabricated literal data: deterministic semantic fixtures
(`USER_ROLE_A`, `ENTITY_ACTIVE_A`, `ACCOUNT_B`) are executable when their properties are
clear. A Test Case needs review only when a material unknown remains.
"""

from __future__ import annotations

import re
from typing import Any

from common import StageError, similarity
from design import check_locale, unknown_keys


SUITABILITY = ("HIGH", "MEDIUM", "LOW", "MANUAL_ONLY")
LAYERS = ("UI", "API", "SERVICE", "INTEGRATION", "HARDWARE", "MIXED")
TOOL_HINTS = ("PLAYWRIGHT", "API_TEST", "TESTSPRITE", "PYTEST", "OTHER", "NONE")
# Unknowns that stop a human from executing or judging the test.
MATERIAL_UNKNOWNS = {
    "MISSING_ORACLE": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "AMBIGUOUS_POLICY": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "UNRESOLVED_PERMISSION": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "MISSING_EXECUTION_SURFACE": ("NEEDS_REVIEW", "NEEDS_ENVIRONMENT"),
    "UNKNOWN_SETUP_PATH": ("NEEDS_REVIEW", "NEEDS_FIXTURE"),
    "EXTERNAL_DEPENDENCY_UNAVAILABLE": ("BLOCKED_EXTERNAL_DEPENDENCY", "BLOCKED_EXTERNAL_DEPENDENCY"),
}
# Unknowns that only affect automation; a human tester can still run the case.
AUTOMATION_UNKNOWNS = {
    "MISSING_FIXTURE": "NEEDS_FIXTURE",
    "MISSING_SELECTOR": "NEEDS_SELECTOR",
    "MISSING_ENVIRONMENT": "NEEDS_ENVIRONMENT",
}
READINESS_ORDER = (
    "BLOCKED_EXTERNAL_DEPENDENCY", "NEEDS_POLICY", "NEEDS_ENVIRONMENT", "NEEDS_FIXTURE",
    "NEEDS_SELECTOR",
)
PROCEDURE_KEYS = {"procedures"}
PROCEDURE_FIELDS = {
    "test", "preconditions", "test_data", "steps", "postconditions", "cleanup", "oracle_step",
    "single_step_reason", "unknowns", "automation", "notes", "evidence_refs",
}
# Unknowns that honestly explain why a procedure cannot cite its execution path yet.
PATH_UNKNOWNS = {"MISSING_EXECUTION_SURFACE", "UNKNOWN_SETUP_PATH"}

GENERIC_PRECONDITION = re.compile(
    r"^\s*(?:preconditions? for|pr[eé]-?condi[cç][oõ]es? para|precondiciones? para)\b|"
    r"\b(?:as applicable|conforme aplic[aá]vel|se aplic[aá]vel)\b",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"<[^>]+>|\bTBD\b|\bXXX\b|\?\?\?|\ba definir\b", re.IGNORECASE)
ABSTRACT_ACTION = re.compile(
    r"\b(?:execute|perform|carry out|complete) (?:the )?(?:action|operation|process|flow|scenario) "
    r"(?:described|indicated|applicable|appropriate|under test|in the objective)\b|"
    r"\b(?:proceed|continue) (?:as|when) applicable\b|\buse the (?:appropriate|correct) (?:item|record|option)\b|"
    r"\b(?:executar|realizar|acionar|efetuar) (?:a|o) (?:a[cç][aã]o|opera[cç][aã]o|processo|fluxo|cen[aá]rio) "
    r"(?:descrit[oa]|indicad[oa]|aplic[aá]vel|adequad[oa]|em teste|do objetivo)\b|"
    r"\b(?:prosseguir|continuar) conforme (?:necess[aá]rio|aplic[aá]vel)\b|"
    r"\bvalidar que funcionou\b|\bvalidate that it worked\b|"
    # A whole step that names no actor, target or observable: "access the system",
    # "perform the operation", "validate it", "check if it worked", "continue the flow",
    # "do everything required". Anchored to the full step, so concrete steps that merely
    # start with the same verb are untouched.
    r"^\s*(?:"
    r"(?:access|open|enter|log into) the (?:system|application|app|platform)|"
    r"(?:perform|execute|do|complete) the (?:operation|action|process|procedure|task)|"
    r"(?:validate|verify|check|confirm) (?:it|this|that|everything|the result)|"
    r"(?:check|verify|see) (?:if|whether) it (?:worked|works|succeeded)|"
    r"(?:continue|proceed with|follow) the (?:flow|process)|"
    r"do (?:everything|all) (?:required|necessary|needed)|"
    r"acess(?:ar|e) o (?:sistema|aplicativo)|"
    r"(?:realiz|execut|efetu|faz|fa[cç])(?:ar|e|er|a) a (?:opera[cç][aã]o|a[cç][aã]o|tarefa)|"
    r"(?:valid|verific|confirm)(?:ar|e|ue) (?:isso|tudo|o resultado)|"
    r"verifi(?:car|que) se (?:funcionou|deu certo)|"
    r"(?:continu|sig)(?:ar|e|a) o fluxo|"
    r"fa(?:zer|[cç]a) tudo (?:o )?que (?:for )?(?:necess[aá]rio|preciso)"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)
ABSTRACT_OBSERVATION = re.compile(
    r"\bthe (?:step|flow|next step) (?:becomes|remains|is) available\b|\bworks as expected\b|"
    r"\bfunciona (?:conforme|como) (?:esperado|o esperado)\b|\b(?:a etapa|o fluxo) (?:fica dispon[ií]vel|segue normalmente)\b|"
    r"\bcomportamento esperado\b|\bexpected behaviou?r\b|"
    r"^\s*(?:it works|it worked|success(?:ful)?|ok|done|funciona|funcionou|deu certo|sucesso)\s*[.!]?\s*$",
    re.IGNORECASE,
)
ACTION_VERB = re.compile(
    r"\b(?:access|open|search|locate|select|enter|provide|scan|read|confirm|submit|consult|click|"
    r"verify|review|choose|cancel|finalize|save|filter|export|move|pass|start|log in|"
    r"acess|abr|pesquis|localiz|selecion|inform|fornec|confirm|envi|consult|clic|verific|"
    r"revis|escolh|cancel|finaliz|salv|filtr|export|mov|inici|autentic|reconhe[cç])\w*\b|"
    r"\b(?:ler|l[eê]|leia|lendo|passar|passe|passa)\b",
    re.IGNORECASE,
)
SEQUENCE_MARKER = re.compile(
    r"(?:;|\s(?:>|→)\s|\b(?:then|and then|next|after that|depois|e depois|em seguida|e ent[aã]o|ap[oó]s isso)\b)",
    re.IGNORECASE,
)
AUTH_ONLY = re.compile(
    r"^\s*(?:autentic\w*|fa[cç]a login|fazer login|efetuar login|entrar no (?:sistema|aplicativo)|"
    r"logar|log in|sign in|authenticate|iniciar sess[aã]o|iniciar sesi[oó]n)\b[^,;]{0,60}$",
    re.IGNORECASE,
)
AUTH_WORDS = re.compile(r"\b(?:login|autentic|authentic|sign in|senha|password|credencia|credential|sess[aã]o|session)", re.IGNORECASE)
INDEPENDENT_VARIANTS = re.compile(
    r"\b(?:separately|execute separately|valid and invalid|each variant|repeat for each|"
    r"cada variante|v[aá]lido e inv[aá]lido|separadamente|repetir para cada)\b",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def compressed_action(action: str) -> bool:
    """One written action that hides a multi-action sequence."""
    verbs = ACTION_VERB.findall(action)
    markers = SEQUENCE_MARKER.findall(action)
    commas = action.count(",")
    return (len(verbs) >= 3 and (markers or commas >= 2)) or (len(verbs) >= 2 and len(markers) >= 1)


def hidden_subtest(action: str) -> bool:
    return bool(INDEPENDENT_VARIANTS.search(action))


def classify(unknowns: list[dict[str, Any]], suitability: str, basis: str, blocking_question: bool) -> dict[str, Any]:
    """Derive execution status and automation readiness from material unknowns only."""
    kinds = [str(item["kind"]) for item in unknowns]
    material = [kind for kind in kinds if kind in MATERIAL_UNKNOWNS]
    if basis == "EXPLORATORY":
        status = "EXPLORATORY"
    elif "EXTERNAL_DEPENDENCY_UNAVAILABLE" in material:
        status = "BLOCKED_EXTERNAL_DEPENDENCY"
    elif material or blocking_question:
        status = "NEEDS_REVIEW"
    else:
        status = "READY"
    readiness_values = [MATERIAL_UNKNOWNS[kind][1] for kind in material]
    readiness_values += [AUTOMATION_UNKNOWNS[kind] for kind in kinds if kind in AUTOMATION_UNKNOWNS]
    if suitability == "MANUAL_ONLY":
        automation_readiness = "NOT_APPLICABLE"
    elif basis == "EXPLORATORY":
        automation_readiness = "NEEDS_POLICY"
    else:
        automation_readiness = next((value for value in READINESS_ORDER if value in readiness_values), "READY")
    return {
        "status": status, "automation_readiness": automation_readiness,
        "readiness_blockers": list(dict.fromkeys(kinds + (["BLOCKING_QUESTION"] if blocking_question else []))),
    }


def validate_procedures(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, PROCEDURE_KEYS, "procedures")
    locale = context["locale"]
    tests = context["tests"]
    by_ref: dict[str, dict[str, Any]] = {}
    for test in tests:
        by_ref[test["key"]] = test
        by_ref[test["id"]] = test
    question_keys = set(context["question_keys"])
    blocking_by_test = context.get("blocking_by_test", {})
    blocking_questions = set(context.get("blocking_questions", set()))
    procedures: dict[str, dict[str, Any]] = {}
    for item in payload.get("procedures", []) or []:
        ref = _text(item.get("test"))
        test = by_ref.get(ref)
        label = f"procedure for {ref or '<missing>'}"
        if test is None:
            errors.append(f"{label} names an unknown Test Case")
            continue
        if test["id"] in procedures:
            errors.append(f"{label} is supplied twice")
        extra = sorted(set(item) - PROCEDURE_FIELDS)
        if extra:
            errors.append(f"{label} contains runtime-owned or unknown fields {extra}")
        preconditions = [_text(value) for value in item.get("preconditions", []) or [] if _text(value)]
        test_data = item.get("test_data", []) or []
        steps = item.get("steps", []) or []
        if not preconditions:
            errors.append(f"{label} requires the starting context as preconditions")
        for value in preconditions:
            if GENERIC_PRECONDITION.search(value):
                errors.append(f"{label} has a generic precondition {value!r}; state the real starting context")
            check_locale(f"{label}.precondition", value, locale, errors)
        normalized_data = []
        for row in test_data:
            name, description = _text(row.get("name")), _text(row.get("description"))
            if not name or not description:
                errors.append(f"{label} test_data rows require name and description")
            if PLACEHOLDER.search(f"{name} {description}"):
                errors.append(f"{label} test data {name!r} is a placeholder; use a semantic fixture with clear properties")
            check_locale(f"{label}.test_data.{name}", description, locale, errors)
            normalized_data.append({"name": name, "description": description})
        unknowns = []
        for unknown in item.get("unknowns", []) or []:
            kind = str(unknown.get("kind", ""))
            if kind not in MATERIAL_UNKNOWNS and kind not in AUTOMATION_UNKNOWNS:
                errors.append(f"{label} unknown kind {kind!r} is not supported")
            if not _text(unknown.get("detail")):
                errors.append(f"{label} unknown {kind} requires detail")
            question = _text(unknown.get("question")) or None
            if question and question not in question_keys:
                errors.append(f"{label} unknown {kind} links unknown question {question}")
            unknowns.append({"kind": kind, "detail": _text(unknown.get("detail")), "question": question})
        missing_oracle = any(unknown["kind"] == "MISSING_ORACLE" for unknown in unknowns)
        evidence_refs = [dict(ref) for ref in item.get("evidence_refs", []) or [] if isinstance(ref, dict)]
        if not evidence_refs and not any(unknown["kind"] in PATH_UNKNOWNS for unknown in unknowns):
            errors.append(
                f"{label} is not grounded in selected evidence; cite evidence_refs for the execution path "
                "or declare MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH"
            )
        about_auth = bool(AUTH_WORDS.search(f"{test['title']} {test['trigger']} {test['objective']}"))
        normalized_steps = []
        if not steps:
            errors.append(f"{label} requires at least one step")
        for number, step in enumerate(steps, 1):
            action, expected = _text(step.get("action")), _text(step.get("expected_result"))
            if not action:
                errors.append(f"{label} step {number} requires an action")
            if not expected and not missing_oracle:
                errors.append(f"{label} step {number} requires an observable expected_result")
            if ABSTRACT_ACTION.search(action):
                errors.append(f"{label} step {number} action is abstract; say who does which atomic action to which target (and where, with which semantic data) as the evidence supports, or keep the known intent and declare MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH")
            if expected and ABSTRACT_OBSERVATION.search(expected):
                errors.append(f"{label} step {number} expected result is not observable")
            if AUTH_ONLY.search(action) and not about_auth:
                errors.append(
                    f"{label} step {number} only authenticates; put the signed-in actor in preconditions and "
                    "describe the real execution path"
                )
            if hidden_subtest(action):
                errors.append(f"{label} step {number} hides independent variants; they belong to separate Test Cases")
            check_locale(f"{label} step {number} action", action, locale, errors)
            check_locale(f"{label} step {number} expected_result", expected, locale, errors)
            normalized_steps.append({
                "step": number, "action": action, "expected_result": expected or None,
                "needs_clarification": not expected,
            })
        if len(normalized_steps) == 1:
            action = normalized_steps[0]["action"]
            if len(_text(item.get("single_step_reason")).split()) < 3:
                errors.append(
                    f"{label} has one step; explain in single_step_reason why one action completes the failure domain"
                )
            if compressed_action(action):
                errors.append(f"{label} compresses a multi-action flow into one step: {action!r}")
        oracle_step = int(item.get("oracle_step") or len(normalized_steps) or 1)
        if test["basis"] in {"ACCEPTANCE", "DERIVED", "CHARACTERIZATION"} and normalized_steps and not missing_oracle:
            if not 1 <= oracle_step <= len(normalized_steps):
                errors.append(f"{label} oracle_step {oracle_step} is outside the procedure")
            else:
                observed = normalized_steps[oracle_step - 1]["expected_result"] or ""
                if similarity(observed, test["expected"]) < 0.4:
                    errors.append(
                        f"{label} step {oracle_step} does not observe the designed oracle {test['expected']!r}"
                    )
        automation = item.get("automation") if isinstance(item.get("automation"), dict) else {}
        suitability = str(automation.get("suitability", ""))
        layer = str(automation.get("layer", ""))
        hint = str(automation.get("tool_hint", "NONE"))
        if suitability not in SUITABILITY:
            errors.append(f"{label} automation.suitability must be one of {SUITABILITY}")
        if layer not in LAYERS:
            errors.append(f"{label} automation.layer must be one of {LAYERS}")
        if hint not in TOOL_HINTS:
            errors.append(f"{label} automation.tool_hint must be one of {TOOL_HINTS}")
        blocking = bool(blocking_by_test.get(test["id"])) or any(
            unknown["question"] in blocking_questions for unknown in unknowns
        )
        classification = classify(unknowns, suitability, test["basis"], blocking)
        for value in item.get("postconditions", []) or []:
            check_locale(f"{label}.postcondition", value, locale, errors)
        procedures[test["id"]] = {
            "preconditions": preconditions, "test_data": normalized_data, "steps": normalized_steps,
            "postconditions": [_text(v) for v in item.get("postconditions", []) or [] if _text(v)],
            "cleanup": [_text(v) for v in item.get("cleanup", []) or [] if _text(v)],
            "notes": [_text(v) for v in item.get("notes", []) or [] if _text(v)],
            "unknowns": unknowns, "oracle_step": oracle_step, "evidence_refs": evidence_refs,
            "single_step_reason": _text(item.get("single_step_reason")) or None,
            "automation_suitability": suitability, "automation_layer": layer,
            "automation_tool_hint": hint, **classification,
        }
        if missing_oracle and not any(u["question"] for u in unknowns if u["kind"] == "MISSING_ORACLE"):
            errors.append(f"{label} MISSING_ORACLE requires the Question that asks for the oracle")
    missing = [test["id"] for test in tests if test["id"] not in procedures]
    if missing:
        errors.append(f"{len(missing)} Test Case(s) have no procedure: " + ", ".join(missing[:20]))
    if errors:
        raise StageError("procedures", errors)
    return {"procedures": procedures, "warnings": procedure_warnings(procedures), "metrics": procedure_metrics(procedures)}


def _template(action: str) -> str:
    text = re.sub(r"\b[A-Z][A-Z0-9_]{2,}\b", "<fixture>", action)
    return " ".join(re.sub(r"\d+", "<n>", text).casefold().split())


def procedure_metrics(procedures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actions = [_template(step["action"]) for item in procedures.values() for step in item["steps"]]
    counts: dict[str, int] = {}
    for action in actions:
        counts[action] = counts.get(action, 0) + 1
    repeated = sum(count for count in counts.values() if count > 1)
    return {
        "procedures_generated": len(procedures),
        "procedures_with_evidence_refs": sum(bool(item["evidence_refs"]) for item in procedures.values()),
        "procedures_requiring_additional_evidence": sum(
            any(u["kind"] in PATH_UNKNOWNS for u in item["unknowns"]) for item in procedures.values()
        ),
        "distinct_evidence_sources_cited": len({ref.get("source") for item in procedures.values() for ref in item["evidence_refs"]}),
        # Each distinct (source, section) pair is one targeted lookup shared by every procedure citing it.
        "targeted_source_lookups": len({(ref.get("source"), ref.get("reference")) for item in procedures.values()
                                        for ref in item["evidence_refs"]}),
        "repeated_step_template_ratio": round(repeated / len(actions), 3) if actions else 0.0,
    }


def procedure_warnings(procedures: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    metrics = procedure_metrics(procedures)
    if len(procedures) >= 10 and metrics["repeated_step_template_ratio"] > 0.5:
        warnings.append(
            f"PROCEDURE_BOILERPLATE: {metrics['repeated_step_template_ratio']:.0%} of steps repeat another step's template"
        )
    for test_id, procedure in procedures.items():
        for step in procedure["steps"]:
            if len(procedure["steps"]) > 1 and compressed_action(step["action"]):
                warnings.append(f"POSSIBLE_MULTI_ACTION_STEP: {test_id} step {step['step']}")
    return warnings


def audit_case(case: dict[str, Any]) -> list[str]:
    """Read-only quality signals for an already published Test Case (ftd-check)."""
    reasons = []
    steps = case.get("steps", [])
    if not case.get("preconditions"):
        reasons.append("MISSING_STARTING_CONTEXT")
    if any(GENERIC_PRECONDITION.search(str(value)) for value in case.get("preconditions", [])):
        reasons.append("GENERIC_PRECONDITION")
    if not steps:
        reasons.append("MISSING_TRIGGER")
    for step in steps:
        action, expected = str(step.get("action", "")), step.get("expected_result")
        if ABSTRACT_ACTION.search(action):
            reasons.append("ABSTRACT_TRIGGER")
        if expected is None:
            reasons.append("MISSING_OBSERVABLE_ASSERTION")
        elif ABSTRACT_OBSERVATION.search(str(expected)):
            reasons.append("ABSTRACT_OBSERVATION")
        if hidden_subtest(action):
            reasons.append("HIDDEN_SUBTEST")
    if len(steps) == 1 and compressed_action(str(steps[0].get("action", ""))):
        reasons.append("PATH_COMPRESSION")
    if any(PLACEHOLDER.search(f"{row.get('name')} {row.get('description')}") for row in case.get("test_data", [])):
        reasons.append("PLACEHOLDER_TEST_DATA")
    if case.get("status") not in {None, "READY"}:
        reasons.append("STATUS_NOT_READY")
    return list(dict.fromkeys(reasons))
