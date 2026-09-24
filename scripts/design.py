#!/usr/bin/env python3
"""Normative test design: requirements, atomic claims, acceptance test intents,
identifier dispositions, the frozen normative baseline, Scenario Families and
advisory merge candidates.

The model does the QA reasoning. This module only enforces the invariants that protect
quality: every authoritative identifier is exercised or explicitly dispositioned, one
independently diagnosable failure domain becomes one atomic Test Case, official titles
are preserved, and the output speaks the run's language.
"""

from __future__ import annotations

import re
from typing import Any

from common import (
    detect_language, locale_language, normalize, normalize_identifier, stable_digest,
)
from sources import identifier_mentioned, titles_match


PRIMARY_TYPES = {
    "FUNCTIONAL", "NEGATIVE", "BOUNDARY", "SECURITY", "AUTHORIZATION", "PERFORMANCE",
    "RESILIENCE", "RECOVERY", "CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY", "INTEGRATION",
    "CONTRACT", "DATA_INTEGRITY", "AUDIT", "STATE_TRANSITION", "E2E", "FIELD",
    "HARDWARE_INTEGRATION", "CHAOS", "EXPLORATORY",
}
PRIORITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
CLAIM_DESTINATIONS = {"TEST", "QUESTION", "NOT_TESTABLE", "FINDING"}
EXPLICIT_DISPOSITIONS = {"QUESTION_REQUIRED", "NOT_TESTABLE_WITH_REASON", "SUPERSEDED_BY_AUTHORITY"}
QUESTION_IMPACTS = {
    "EXECUTION_DETAIL", "TEST_DATA", "ACTOR_PERMISSION", "EXPECTED_RESULT", "ENVIRONMENT",
    "SCOPE", "IMPLEMENTATION_LOCATION", "REQUIREMENT_AMBIGUITY",
}
FINDING_TYPES = {"IMPLEMENTATION_DIVERGENCE", "SOURCE_CONFLICT", "COVERAGE_GAP", "INFORMATION"}
FINDING_DISPOSITIONS = {
    "COVERED_BY_EXISTING_SCENARIO", "NEW_NORMATIVE_SCENARIO", "DIVERGENCE_SCENARIO",
    "IMPLEMENTATION_CHARACTERIZATION", "QUESTION", "NOT_TESTABLE", "OUT_OF_SCOPE",
}
TEST_INTENT_FIELDS = (
    "title", "objective", "family", "actor", "state", "trigger", "expected", "failure_domain",
    "priority_reason",
)
DESIGN_KEYS = {
    "domain_model", "requirements", "claims", "tests", "dispositions", "questions", "findings",
    "structure_reviews",
}
# Universal reasoning dimensions. Their values are inferred by the model from the
# selected sources; the framework stores them and never interprets their meaning.
DOMAIN_DIMENSIONS = (
    "actors", "entities", "states", "operations", "invariants", "permissions",
    "integrations", "events", "dependencies", "observables", "failure_surfaces",
)
REQUIRED_DOMAIN_DIMENSIONS = ("actors", "entities", "operations")
MISSING_IMPLEMENTATION = re.compile(
    r"\b(?:implementation|code|endpoint|screen|ui|implementa[cç][aã]o|c[oó]digo|tela)\b.*"
    r"\b(?:missing|absent|not found|unavailable|n[aã]o (?:encontrad|existe|dispon)|ausente)",
    re.IGNORECASE,
)

# Conservative suspicion signals: they never split anything, they ask for a decision.
COMPOUND_CONNECTOR = re.compile(r"(?:[,;]|\b(?:and|or|e|ou)\b)", re.IGNORECASE)
_PT_ENDING = (
    r"(?:ar|er|ir|a|e|i|ia|iam|am|em|ado|ada|ados|adas|ido|ida|idos|idas|ou|ar[aá]|ar[aã]o|"
    r"ando|endo|indo)\b"
)
OBSERVABLE_VERB = re.compile(
    r"\b(?:(?:show|display|search|filter|record|create|change|decrease|update|block|prevent|"
    r"return|persist|send|receive|release|complete|finali[sz]e|reverse|cancel|notify|generate|"
    r"remove)\w*|(?:exib|mostr|busc|pesquis|filtr|registr|cri|alter|reduz|atualiz|bloque|imped|"
    r"retorn|persist|envi|receb|liber|conclu|finaliz|revert|cancel|notific|ger|remov|mud|marc)"
    + _PT_ENDING + r")",
    re.IGNORECASE,
)
DIMENSION_VERB = re.compile(r"\b(?:search|filter|quer|busc|pesquis|filtr|consult)\w*\b", re.IGNORECASE)
BY_DIMENSIONS = re.compile(r"\b(?:by|por)\b[^.;:\n]*(?:,|\b(?:and|or|e|ou)\b)[^.;:\n]+", re.IGNORECASE)
REPEATED_TIME_LIMIT = re.compile(r"\b(?:within|em at[eé])\s+\d+", re.IGNORECASE)


def compound_signals(text: str) -> list[str]:
    signals: list[str] = []
    verbs = {verb.casefold()[:5] for verb in OBSERVABLE_VERB.findall(text)}
    if len(verbs) >= 2 and COMPOUND_CONNECTOR.search(text):
        signals.append("MULTIPLE_OBSERVABLE_OUTCOMES")
    if DIMENSION_VERB.search(text) and BY_DIMENSIONS.search(text):
        signals.append("MULTIPLE_SEARCH_OR_FILTER_DIMENSIONS")
    if len(REPEATED_TIME_LIMIT.findall(text)) >= 2:
        signals.append("MULTIPLE_TIME_LIMITS")
    return signals


def check_locale(label: str, text: Any, locale: str, errors: list[str]) -> None:
    """Reject text whose function words clearly belong to another language."""
    expected = locale_language(locale)
    detected = detect_language(text)
    if detected and expected and detected != expected:
        errors.append(f"{label} is written in '{detected}' but the run locale is {locale}")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _refs(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value or [] if isinstance(item, dict)]


def _keys(values: Any) -> list[str]:
    return [str(value) for value in values or []]


def unknown_keys(payload: dict[str, Any], allowed: set[str], stage: str) -> list[str]:
    extra = sorted(set(payload) - allowed)
    return [f"{stage} payload field {name!r} is not accepted (runtime-owned or unknown)" for name in extra]


def validate_test_intent(test: dict[str, Any], label: str, locale: str, errors: list[str]) -> None:
    """Stage A of every Test Case: what is tested, by whom, from which state, how it fails."""
    for field in TEST_INTENT_FIELDS:
        if not _text(test.get(field)):
            errors.append(f"{label} requires {field}")
    if str(test.get("primary_type", "")) not in PRIMARY_TYPES:
        errors.append(f"{label} primary_type must be one of the supported types")
    if str(test.get("priority", "")) not in PRIORITIES:
        errors.append(f"{label} priority must be CRITICAL, HIGH, MEDIUM or LOW")
    for field in ("title", "objective", "expected", "family"):
        check_locale(f"{label}.{field}", test.get(field), locale, errors)
    combined = " ".join(_text(test.get(field)) for field in ("title", "objective", "expected", "trigger", "state"))
    check_locale(f"{label} (combined intent)", combined, locale, errors)


def validate_questions_and_findings(
    payload: dict[str, Any], requirement_keys: set[str], locale: str, errors: list[str],
    stage: str, taken: set[str], prior_questions: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A Finding whose coverage disposition is QUESTION must name the real Question(s)
    that ask what has to be resolved (from this stage or an earlier one); one Question
    may serve several Findings about the same unresolved policy."""
    questions, findings = [], []
    for number, item in enumerate(payload.get("questions", []) or [], 1):
        key = _text(item.get("key")) or f"{stage}-Q{number}"
        label = f"question {key}"
        if key in taken:
            errors.append(f"{label} key is not unique")
        taken.add(key)
        for field in ("question", "reason"):
            if not _text(item.get(field)):
                errors.append(f"{label} requires {field}")
            check_locale(f"{label}.{field}", item.get(field), locale, errors)
        impact = str(item.get("impact", "REQUIREMENT_AMBIGUITY"))
        if impact not in QUESTION_IMPACTS:
            errors.append(f"{label} impact must be one of {sorted(QUESTION_IMPACTS)}")
        requirements = _keys(item.get("requirements"))
        if not requirements or not set(requirements) <= requirement_keys:
            errors.append(f"{label} must reference known requirement keys")
        questions.append({
            "key": key, "question": _text(item.get("question")), "reason": _text(item.get("reason")),
            "impact": impact, "blocking": bool(item.get("blocking", False)),
            "requirements": requirements, "tests": _keys(item.get("tests")),
            "source_refs": _refs(item.get("source_refs")), "stage": stage,
        })
    for number, item in enumerate(payload.get("findings", []) or [], 1):
        key = _text(item.get("key")) or f"{stage}-F{number}"
        label = f"finding {key}"
        if key in taken:
            errors.append(f"{label} key is not unique")
        taken.add(key)
        if str(item.get("type", "")) not in FINDING_TYPES:
            errors.append(f"{label} type must be one of {sorted(FINDING_TYPES)}")
        if not _text(item.get("statement")):
            errors.append(f"{label} requires statement")
        check_locale(f"{label}.statement", item.get("statement"), locale, errors)
        disposition = str(item.get("coverage_disposition", "QUESTION"))
        if disposition not in FINDING_DISPOSITIONS:
            errors.append(f"{label} coverage_disposition is not supported")
        requirements = _keys(item.get("requirements"))
        if not set(requirements) <= requirement_keys:
            errors.append(f"{label} references unknown requirement keys")
        if not _refs(item.get("source_refs")):
            errors.append(f"{label} requires source_refs to the evidence that shows it")
        findings.append({
            "key": key, "type": str(item.get("type", "")), "statement": _text(item.get("statement")),
            "requirements": requirements, "tests": _keys(item.get("tests")),
            "question_keys": _keys(item.get("questions")),
            "source_refs": _refs(item.get("source_refs")), "coverage_disposition": disposition,
            "stage": stage,
        })
    known = set(prior_questions or ()) | {item["key"] for item in questions}
    for finding in findings:
        label = f"finding {finding['key']}"
        unknown = [key for key in finding["question_keys"] if key not in known]
        if unknown:
            errors.append(f"{label} links unknown questions {unknown}")
        if finding["coverage_disposition"] == "QUESTION" and not finding["question_keys"]:
            errors.append(
                f"{label} has coverage_disposition QUESTION but links no Question; add `questions` naming the "
                "Question that asks what must be resolved (reuse one that already asks it)")
    return questions, findings


def validate_design(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Validate the normative design stage and materialize its canonical design state."""
    errors = unknown_keys(payload, DESIGN_KEYS, "design")
    locale = context["locale"]
    domain_model = validate_domain_model(payload.get("domain_model"), errors)
    authority = {normalize_identifier(item["identifier"]): item for item in context["authority_index"]}
    authority_texts = context["authority_texts"]

    # Requirements keep their official identifier, title and statement.
    requirements: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("requirements", []) or [], 1):
        key = _text(item.get("key")) or _text(item.get("source_identifier")) or f"R{number}"
        label = f"requirement {key}"
        if key in by_key:
            errors.append(f"{label} key is not unique")
        identifier = _text(item.get("source_identifier"))
        title = _text(item.get("source_title"))
        indexed = authority.get(normalize_identifier(identifier)) if identifier else None
        if identifier and indexed is None and not identifier_mentioned(identifier, authority_texts):
            errors.append(f"{label} source_identifier {identifier} does not appear in selected authority")
        if indexed:
            if title and not titles_match(title, indexed["title"]):
                errors.append(
                    f"{label} source_title {title!r} differs from the official title {indexed['title']!r}"
                )
            title = indexed["title"]
            identifier = indexed["identifier"]
        statement = _text(item.get("source_statement")) or _text(item.get("statement"))
        if not statement:
            errors.append(f"{label} requires source_statement")
        refs = _refs(item.get("source_refs"))
        if not refs and indexed:
            refs = [{"source": indexed["source"], "reference": f"{indexed['identifier']} (line {indexed['line']})"}]
        if not refs:
            errors.append(f"{label} requires source_refs")
        status = str(item.get("status", "TESTABLE"))
        if status not in {"TESTABLE", "NEEDS_CLARIFICATION"}:
            errors.append(f"{label} status must be TESTABLE or NEEDS_CLARIFICATION")
        requirement = {
            "id": f"REQ-{number:03d}", "key": key, "statement": statement, "status": status,
            "source_refs": refs, "source_identifier": identifier or None,
            "source_title": title or None, "source_statement": statement,
            "kind": indexed["kind"] if indexed else "GENERIC",
        }
        requirements.append(requirement)
        by_key[key] = requirement
    if not requirements:
        errors.append("design requires at least one requirement")

    taken_keys: set[str] = set(by_key)
    questions, findings = validate_questions_and_findings(
        payload, set(by_key), locale, errors, "design", taken_keys,
    )
    question_keys = {item["key"] for item in questions}
    finding_keys = {item["key"] for item in findings}

    # Claims: one independently observable obligation each.
    claims: list[dict[str, Any]] = []
    claims_by_key: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("claims", []) or [], 1):
        key = _text(item.get("key")) or f"C{number}"
        label = f"claim {key}"
        if key in claims_by_key or key in taken_keys:
            errors.append(f"{label} key is not unique")
        taken_keys.add(key)
        requirement = by_key.get(_text(item.get("requirement")))
        if requirement is None:
            errors.append(f"{label} references unknown requirement {item.get('requirement')!r}")
            continue
        text = _text(item.get("text"))
        if not text:
            errors.append(f"{label} requires text")
        destination = str(item.get("destination", "TEST"))
        if destination not in CLAIM_DESTINATIONS:
            errors.append(f"{label} destination must be one of {sorted(CLAIM_DESTINATIONS)}")
        if destination == "QUESTION" and _text(item.get("question")) not in question_keys:
            errors.append(f"{label} is a QUESTION but links no known question key")
        if destination == "FINDING" and _text(item.get("finding")) not in finding_keys:
            errors.append(f"{label} is a FINDING but links no known finding key")
        reason = _text(item.get("reason"))
        if destination == "NOT_TESTABLE":
            if not reason:
                errors.append(f"{label} is NOT_TESTABLE without a reason")
            elif MISSING_IMPLEMENTATION.search(reason):
                errors.append(
                    f"{label} cannot become NOT_TESTABLE because implementation is missing; "
                    "keep the normative test and let its procedure record the blocker"
                )
        indivisible = _text(item.get("indivisible_contract"))
        signals = compound_signals(text)
        if signals and len(indivisible.split()) < 3:
            errors.append(
                f"{label} looks compound ({', '.join(signals)}); split it into independently "
                "diagnosable claims or explain the indivisible_contract"
            )
        identifiers = [_text(value) for value in item.get("identifiers", []) or [] if _text(value)]
        if requirement["source_identifier"]:
            identifiers.insert(0, requirement["source_identifier"])
        normalized_ids = list(dict.fromkeys(normalize_identifier(value) for value in identifiers))
        for value in normalized_ids:
            if value not in authority and not identifier_mentioned(value, authority_texts):
                errors.append(f"{label} cites identifier {value} that is absent from selected authority")
        claim = {
            "id": f"CLAIM-{number:03d}", "key": key, "requirement_ref": requirement["id"],
            "requirement_key": requirement["key"], "text": text, "destination": destination,
            "identifiers": normalized_ids, "source_refs": _refs(item.get("source_refs")) or requirement["source_refs"],
            "question": _text(item.get("question")) or None, "finding": _text(item.get("finding")) or None,
            "reason": reason or None, "indivisible_contract": indivisible or None,
        }
        claims.append(claim)
        claims_by_key[key] = claim

    # Acceptance tests: the normative atomic baseline.
    tests: list[dict[str, Any]] = []
    tests_by_key: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("tests", []) or [], 1):
        key = _text(item.get("key")) or f"T{number}"
        label = f"acceptance test {key}"
        if key in tests_by_key or key in taken_keys:
            errors.append(f"{label} key is not unique")
        taken_keys.add(key)
        claim_keys = _keys(item.get("claims"))
        linked = [claims_by_key[value] for value in claim_keys if value in claims_by_key]
        if not claim_keys or len(linked) != len(claim_keys):
            errors.append(f"{label} must exercise known claim keys")
        if any(claim["destination"] != "TEST" for claim in linked):
            errors.append(f"{label} exercises a claim whose destination is not TEST")
        validate_test_intent(item, label, locale, errors)
        indivisible = _text(item.get("indivisible_contract"))
        if len(linked) > 1 and len(indivisible.split()) < 3:
            errors.append(
                f"{label} exercises {len(linked)} claims; independent failure domains need "
                "independent Test Cases unless an indivisible_contract is explained"
            )
        signals = compound_signals(_text(item.get("expected")))
        if signals and len(indivisible.split()) < 3 and not any(c.get("indivisible_contract") for c in linked):
            errors.append(f"{label} expected result looks compound ({', '.join(signals)})")
        for value in _keys(item.get("questions")):
            if value not in question_keys:
                errors.append(f"{label} links unknown question {value}")
        for value in _keys(item.get("findings")):
            if value not in finding_keys:
                errors.append(f"{label} links unknown finding {value}")
        test = {
            "key": key, "basis": "ACCEPTANCE", "claims": [claim["id"] for claim in linked],
            "claim_keys": claim_keys,
            **traceability(linked, item.get("related_identifiers"), label, authority, authority_texts, requirements, errors),
            "source_refs": [ref for claim in linked for ref in claim["source_refs"]],
            **{field: _text(item.get(field)) for field in TEST_INTENT_FIELDS},
            "primary_type": str(item.get("primary_type", "FUNCTIONAL")),
            "priority": str(item.get("priority", "MEDIUM")),
            "indivisible_contract": indivisible or None, "event": _text(item.get("event")) or None,
            "question_keys": _keys(item.get("questions")), "finding_keys": _keys(item.get("findings")),
            "stage": "design",
        }
        tests.append(test)
        tests_by_key[key] = test

    exercised = {claim_id for test in tests for claim_id in test["claims"]}
    for claim in claims:
        if claim["destination"] == "TEST" and claim["id"] not in exercised:
            errors.append(f"claim {claim['key']} has destination TEST but no acceptance test exercises it")

    explicit = validate_explicit_dispositions(payload.get("dispositions", []) or [], authority, question_keys, errors)
    reviews = structure_review(context["authority_index"], claims, payload.get("structure_reviews", []) or [], errors)
    ledger = identifier_ledger(context["authority_index"], claims, tests, explicit, errors)
    if errors:
        from common import StageError
        raise StageError("design", errors)
    return {
        "domain_model": domain_model, "requirements": requirements, "claims": claims, "tests": tests,
        "questions": questions, "findings": findings, "dispositions": explicit,
        "identifier_ledger": ledger, "baseline": baseline_snapshot(tests), "structure_reviews": reviews,
        "warnings": priority_warnings(tests),
    }


def traceability(
    claims: list[dict[str, Any]], related: Any, label: str, authority: dict[str, dict[str, Any]],
    authority_texts: list[str], requirements: list[dict[str, Any]], errors: list[str],
) -> dict[str, list[str]]:
    """Every authoritative identifier a test is grounded in stays visible on the test.

    Claims carry the identifiers they exercise (coverage). `related_identifiers` records
    further authority the test is substantively grounded in (traceability only). Both
    are decided during semantic design; the renderer never infers them.
    """
    identifiers = [i for claim in claims for i in claim["identifiers"]]
    for value in related or []:
        key = normalize_identifier(value)
        if key not in authority and not identifier_mentioned(key, authority_texts):
            errors.append(f"{label} relates identifier {value} that is absent from selected authority")
        identifiers.append(key)
    identifiers = list(dict.fromkeys(identifiers))
    by_identifier = {
        normalize_identifier(item["source_identifier"]): item["id"] for item in requirements if item.get("source_identifier")
    }
    refs = [claim["requirement_ref"] for claim in claims] + [by_identifier[i] for i in identifiers if i in by_identifier]
    return {"requirement_refs": list(dict.fromkeys(refs)), "identifiers": identifiers}


def validate_domain_model(value: Any, errors: list[str]) -> dict[str, list[str]]:
    """A lightweight project-derived model that helps reasoning; it is not an ontology."""
    if not isinstance(value, dict):
        errors.append("design requires a project-derived domain_model inferred from the sources")
        return {}
    unknown = sorted(set(value) - set(DOMAIN_DIMENSIONS))
    if unknown:
        errors.append(f"domain_model has unknown dimensions {unknown}; use {list(DOMAIN_DIMENSIONS)}")
    model = {
        key: [_text(item) for item in value.get(key, []) or [] if _text(item)]
        for key in DOMAIN_DIMENSIONS
    }
    for key in REQUIRED_DOMAIN_DIMENSIONS:
        if not model[key]:
            errors.append(f"domain_model.{key} must list what the selected sources define")
    return model


def structure_review(
    authority_index: list[dict[str, Any]], claims: list[dict[str, Any]], reviews: list[dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    """A section with several structural items may not silently become one summary claim.

    The runtime only counts bullets and substantive sentences; whether they are really
    one obligation is the model's call, recorded as a reason that stays auditable.
    """
    reasons = {normalize_identifier(item.get("identifier")): _text(item.get("reason")) for item in reviews}
    recorded = []
    for entry in authority_index:
        key = normalize_identifier(entry["identifier"])
        own = [claim for claim in claims if key in claim["identifiers"]]
        items = int(entry.get("structural_items", 0))
        if items >= 2 and len(own) == 1:
            reason = reasons.get(key, "")
            if len(reason.split()) < 5:
                errors.append(
                    f"identifier {entry['identifier']} has {items} structural items in the authority but one claim; "
                    "decompose its independently observable obligations or record a structure_review reason"
                )
            recorded.append({"identifier": entry["identifier"], "structural_items": items, "claims": 1, "reason": reason})
    unknown = sorted(set(reasons) - {normalize_identifier(e["identifier"]) for e in authority_index})
    if unknown:
        errors.append(f"structure_reviews name identifiers the authority does not define: {unknown}")
    return recorded


def validate_explicit_dispositions(
    items: list[dict[str, Any]], authority: dict[str, dict[str, Any]],
    question_keys: set[str], errors: list[str],
) -> dict[str, dict[str, Any]]:
    explicit: dict[str, dict[str, Any]] = {}
    for item in items:
        identifier = normalize_identifier(item.get("identifier"))
        label = f"disposition for {identifier or '<missing>'}"
        if identifier not in authority:
            errors.append(f"{label} names an identifier that selected authority does not define")
            continue
        if identifier in explicit:
            errors.append(f"{label} is declared twice")
        disposition = str(item.get("disposition", ""))
        reason = _text(item.get("reason"))
        if disposition not in EXPLICIT_DISPOSITIONS:
            errors.append(
                f"{label} must be one of {sorted(EXPLICIT_DISPOSITIONS)}; coverage and blocking "
                "are derived from the designed Test Cases"
            )
        if not reason:
            errors.append(f"{label} requires a reason")
        if disposition == "QUESTION_REQUIRED" and _text(item.get("question")) not in question_keys:
            errors.append(f"{label} requires a known question key")
        if disposition == "NOT_TESTABLE_WITH_REASON" and MISSING_IMPLEMENTATION.search(reason):
            errors.append(
                f"{label}: normative behavior without implementation evidence is still designed; "
                "missing implementation is a procedure blocker, not a disposition"
            )
        if disposition == "SUPERSEDED_BY_AUTHORITY":
            target = normalize_identifier(item.get("superseded_by"))
            if target not in authority or target == identifier:
                errors.append(f"{label} requires superseded_by naming another authority identifier")
        explicit[identifier] = {
            "identifier": identifier, "disposition": disposition, "reason": reason,
            "question": _text(item.get("question")) or None,
            "superseded_by": normalize_identifier(item.get("superseded_by")) or None,
        }
    return explicit


def identifier_ledger(
    authority_index: list[dict[str, Any]], claims: list[dict[str, Any]],
    tests: list[dict[str, Any]], explicit: dict[str, dict[str, Any]], errors: list[str],
    *, statuses: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Give every authoritative identifier one disposition; completeness means exercised."""
    statuses = statuses or {}
    ledger = []
    for entry in authority_index:
        key = normalize_identifier(entry["identifier"])
        own_claims = [claim for claim in claims if key in claim["identifiers"]]
        covering = [
            test for test in tests
            if test["basis"] == "ACCEPTANCE" and any(claim["id"] in test["claims"] for claim in own_claims)
        ]
        test_ids = [test.get("id") or test["key"] for test in covering]
        record = {
            "identifier": entry["identifier"], "kind": entry["kind"], "title": entry["title"],
            "source": entry["source"], "line": entry["line"],
            "claim_refs": [claim["id"] for claim in own_claims], "test_refs": test_ids,
            "reason": None, "question_refs": [],
        }
        if covering and key in explicit:
            errors.append(
                f"identifier {entry['identifier']} is exercised by Test Cases and also has an explicit disposition"
            )
        if covering:
            blocked = [value for value in test_ids if statuses.get(value) == "BLOCKED_EXTERNAL_DEPENDENCY"]
            if statuses and len(blocked) == len(test_ids):
                record["disposition"] = "BLOCKED_EXTERNAL_DEPENDENCY"
            else:
                record["disposition"] = (
                    "COVERED_BY_ATOMIC_TC" if len(covering) == 1 else "COVERED_BY_MULTIPLE_ATOMIC_TCS"
                )
        elif key in explicit:
            record["disposition"] = explicit[key]["disposition"]
            record["reason"] = explicit[key]["reason"]
            record["question_refs"] = [explicit[key]["question"]] if explicit[key]["question"] else []
        elif own_claims and all(claim["destination"] == "QUESTION" for claim in own_claims):
            record["disposition"] = "QUESTION_REQUIRED"
            record["question_refs"] = [claim["question"] for claim in own_claims]
        elif own_claims and all(claim["destination"] in {"QUESTION", "NOT_TESTABLE"} for claim in own_claims):
            record["disposition"] = "NOT_TESTABLE_WITH_REASON"
            record["reason"] = "; ".join(claim["reason"] or "" for claim in own_claims if claim["reason"])
        else:
            record["disposition"] = None
            detail = "claims exist but none is exercised" if own_claims else "no claim, Test Case or disposition"
            errors.append(f"identifier {entry['identifier']} ({entry['kind']}) is unaccounted: {detail}")
        ledger.append(record)
    return ledger


def baseline_snapshot(tests: list[dict[str, Any]]) -> dict[str, Any]:
    frozen = [{
        "key": test["key"], "claims": test["claims"], "title": test["title"],
        "expected": test["expected"], "failure_domain": test["failure_domain"],
    } for test in tests if test["basis"] == "ACCEPTANCE"]
    return {"tests": frozen, "digest": stable_digest(frozen), "count": len(frozen)}


def baseline_preserved(snapshot: dict[str, Any], tests: list[dict[str, Any]]) -> list[str]:
    """Additive stages may add tests; they may never remove or redefine the baseline."""
    current = baseline_snapshot([test for test in tests if test.get("stage") == "design"])
    if current["digest"] == snapshot["digest"]:
        return []
    before = {item["key"]: item for item in snapshot["tests"]}
    after = {item["key"]: item for item in current["tests"]}
    problems = [f"baseline test {key} was removed" for key in sorted(set(before) - set(after))]
    problems += [f"baseline test {key} was redefined" for key in sorted(before.keys() & after.keys()) if before[key] != after[key]]
    return problems or ["normative baseline digest changed"]


def priority_warnings(tests: list[dict[str, Any]]) -> list[str]:
    if len(tests) < 5:
        return []
    counts: dict[str, int] = {}
    for test in tests:
        counts[test["priority"]] = counts.get(test["priority"], 0) + 1
    priority, count = max(counts.items(), key=lambda item: item[1])
    if count / len(tests) > 0.9:
        return [f"PRIORITY_FLATTENING: {count}/{len(tests)} tests are {priority}; review impact reasons"]
    return []


def build_families(tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scenario Families organize Test Cases; they never change a Test Case's identity."""
    order: list[str] = []
    titles: dict[str, str] = {}
    for test in tests:
        key = normalize(test["family"])
        if key not in titles:
            order.append(key)
            titles[key] = test["family"]
    families = []
    for number, key in enumerate(order, 1):
        members = [test for test in tests if normalize(test["family"]) == key]
        families.append({
            "id": f"SCN-{number:03d}", "title": titles[key], "type": "SCENARIO_FAMILY",
            "requirement_refs": list(dict.fromkeys(ref for test in members for ref in test["requirement_refs"])),
            "coverage_point_refs": list(dict.fromkeys(ref for test in members for ref in test["cp_refs"])),
            "test_case_refs": [test["id"] for test in members],
        })
    return families


def merge_candidates(tests: list[dict[str, Any]]) -> dict[str, Any]:
    """Advisory manual-execution groupings; canonical atomic Test Cases never change."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for test in tests:
        if test["basis"] == "E2E":
            continue
        if test.get("event"):
            key = ("event", normalize(test["event"]))
        else:
            key = ("setup", normalize(test["actor"]), normalize(test["state"]), normalize(test["trigger"]))
        groups.setdefault(key, []).append(test)
    candidates = []
    for key, members in groups.items():
        domains = {normalize(test["failure_domain"]) for test in members}
        if len(members) < 2 or len(domains) < 2:
            continue
        shared_event = key[0] == "event"
        candidates.append({
            "merge_candidate_id": f"MC-{len(candidates) + 1:03d}",
            "test_case_ids": [test["id"] for test in members],
            "reason": (
                "same business event with complementary observations" if shared_event
                else "same actor, starting state and trigger with complementary observations"
            ),
            "shared_setup": not shared_event, "shared_business_event": shared_event,
            "manual_execution_benefit": "HIGH" if len(members) > 2 else "MEDIUM",
            "automation_tradeoff": "LOSES_INDEPENDENT_FAILURE_DIAGNOSIS",
            "confidence": "HIGH" if shared_event else "MEDIUM",
        })
    return {"detector_ran": True, "tests_examined": len(tests), "candidates": candidates}
