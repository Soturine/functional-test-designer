#!/usr/bin/env python3
"""The FTD ADR analysis contract: what the model submits after reading the ADR material, and the
deterministic checks that protect it. Ids are runtime-owned: decisions keep an official id the
document states (never a pretended one), new Test Cases, Questions, Findings, requirements,
coverage points and scenarios continue the project-wide numbering of the effective suite.

Reuses the canonical primitives (`design.validate_test_intent`, `design.compound_signals`,
`check_locale`, the expansion dimensions, Question impacts and Finding types) — it never
weakens them and never forks the canonical stages.
"""

from __future__ import annotations

import re
from typing import Any

from design import (FINDING_TYPES, PRIORITIES, QUESTION_IMPACTS, check_locale, compound_signals,
                    mechanical_templates, unknown_keys, validate_test_intent)
from expansion import DIMENSIONS
from procedures import ABSTRACT_OBSERVATION, semantically_empty

CLASSIFICATIONS = ("APPROVED_DECISION", "DRAFT_DECISION", "SUPPORTING_CONTEXT", "REFERENCE_STANDARD",
                   "SUPERSEDED_DOCUMENT", "UNKNOWN_STATUS")
# A file's overall status; the authority of each statement inside it is tracked separately.
DOCUMENT_STATUSES = (*CLASSIFICATIONS, "MIXED_CONTENT", "NO_MATERIAL_CONTENT")
# What a material statement of the change corpus is. Not a closed ontology of prose: only what
# matters for the project's behavior is cataloged, and a statement may touch several concerns.
STATEMENT_KINDS = (
    "DECISION", "OBSERVATION", "REQUIREMENT_CHANGE", "BUSINESS_RULE", "CONSTRAINT", "ASSUMPTION", "OPEN_QUESTION",
    "RISK", "MIGRATION_CONCERN", "IMPLEMENTATION_FACT", "OPERATIONAL_FACT", "INTEGRATION_CHANGE",
    "ACTOR_OR_PERMISSION_CHANGE", "STATE_OR_WORKFLOW_CHANGE", "DATA_CHANGE", "PHYSICAL_OR_DEVICE_CHANGE",
    "NON_FUNCTIONAL_CHANGE", "PROPOSAL", "DRAFT_IDEA", "REJECTED_IDEA", "FUTURE_IDEA", "REFERENCE_INFORMATION",
)
STATEMENT_STATUSES = ("APPROVED", "DRAFT", "PROPOSED", "REJECTED", "FUTURE", "OBSERVED", "UNCERTAIN", "REFERENCE")
STATEMENT_DISPOSITIONS = ("DECISION", "QUESTION", "FINDING", "CONTEXT", "NO_TEST_IMPACT")
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")
CLAIM_DISPOSITIONS = ("COVERED_BY_EXISTING", "COVERED_BY_UPDATE", "NEW_TEST", "QUESTION", "NOT_TESTABLE")
DECISION_STATUSES = ("APPROVED", "DRAFT", "SUPPORTING", "REFERENCE", "SUPERSEDED", "UNKNOWN")
RELATIONSHIPS = ("CONFIRMS", "CLARIFIES", "ADDS_BEHAVIOR", "CHANGES", "SUPERSEDES", "REMOVES_BEHAVIOR",
                 "CONFLICTS_WITH", "NO_TEST_IMPACT", "UNCLEAR", "ALREADY_INCORPORATED", "REVOKES_DECISION")
BEHAVIOR_CHANGING = {"ADDS_BEHAVIOR", "CHANGES", "SUPERSEDES", "REMOVES_BEHAVIOR"}
NEEDS_PREVIOUS = {"CHANGES", "SUPERSEDES", "REMOVES_BEHAVIOR", "CONFLICTS_WITH"}
ACTIONS = ("AFFECTED_NO_CHANGE", "UPDATE", "CREATE", "SUPERSEDE", "REVIEW_ONLY", "CONFLICT")
WRITES_DEFINITION = {"UPDATE", "CREATE"}
IMPACTS = ("DIRECT", "INDIRECT")
BASES = ("ACCEPTANCE", "DERIVED", "CHARACTERIZATION", "EXPLORATORY")
DIMENSION_DISPOSITIONS = ("MATERIALIZED", "ALREADY_COVERED", "QUESTION_REQUIRED", "NOT_APPLICABLE")
QUESTION_DISPOSITIONS = ("RESOLVED_BY_ADR", "PARTIALLY_ANSWERED_BY_ADR", "STILL_OPEN")
FINDING_DISPOSITIONS = ("RESOLVED_BY_ADR", "STILL_APPLIES", "SUPERSEDED_BY_ADR")
ANALYSIS_KEYS = {"sources", "statements", "decisions", "test_cases", "dimension_reviews", "questions", "findings",
                 "question_dispositions", "finding_dispositions"}
DESIGN_FIELDS = {"title", "objective", "family", "actor", "state", "trigger", "expected", "failure_domain",
                 "priority", "priority_reason", "primary_type", "basis", "dimension"}
MINTED_DECISION = "ADR-DEC-"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[str]:
    return [_text(v) for v in value or [] if _text(v)]


def _quoted(excerpt: str, text: str) -> bool:
    """A verbatim excerpt (whitespace and case normalized): the evidence, not a paraphrase."""
    squash = lambda value: " ".join(value.split()).casefold()  # noqa: E731
    return bool(excerpt) and squash(excerpt) in squash(text)


def _number(value: str, prefix: str) -> int:
    match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", value)
    return int(match.group(1)) if match else 0


def next_ids(prefix: str, existing: list[str], count: int, width: int = 3) -> list[str]:
    start = max((_number(value, prefix) for value in existing), default=0)
    return [f"{prefix}{start + n:0{width}d}" for n in range(1, count + 1)]


def derive_status(statuses: list[str]) -> str:
    """A decision is APPROVED only when a statement it is built from is approved by its source."""
    if "APPROVED" in statuses:
        return "APPROVED"
    for status, derived in (("DRAFT", "DRAFT"), ("PROPOSED", "DRAFT"), ("REFERENCE", "REFERENCE"),
                            ("OBSERVED", "SUPPORTING")):
        if status in statuses:
            return derived
    return "UNKNOWN"


def validate_analysis(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """`context`: base (effective state), entries (inventory), texts ({path: text} for readable
    files), parent_sources (paths of the parent's evidence). Every problem is reported at once."""
    errors = unknown_keys(payload, ANALYSIS_KEYS, "ADR analysis")
    base, texts = context["base"], context["texts"]
    locale = base["output_locale"]
    active = {cid for cid, s in base["case_states"].items() if s["state"] == "ACTIVE"}
    known_cases = set(base["case_states"])
    requirement_ids = {r["id"] for r in base["requirements"]} | {r["id"] for r in base["adr_requirements"]}
    ledger = {d["id"]: d for d in base["decisions"]}
    question_ids = {q["id"] for q in base["questions"]}
    finding_ids = {f["id"] for f in base["findings"]}
    adr_paths = set(base["sources"]) | set(texts)

    # 1. every file read in this round is semantically reviewed; its document status is not the
    #    authority of each statement inside it (a file may mix decisions, notes, ideas, questions)
    document_status: dict[str, str] = {}
    for item in payload.get("sources", []) or []:
        path = _text(item.get("path"))
        label = f"ADR source {path or '<missing>'}"
        if path not in texts:
            errors.append(f"{label} is not a file read in this round (NEW_READ / CHANGED_READ)")
            continue
        if path in document_status:
            errors.append(f"{label} is reviewed twice")
        value = _text(item.get("document_status"))
        if value not in DOCUMENT_STATUSES:
            errors.append(f"{label} document_status must be one of {DOCUMENT_STATUSES}")
        if not _text(item.get("summary")):
            errors.append(f"{label} requires summary (what the file says, in the run's language)")
        check_locale(f"{label}.summary", item.get("summary"), locale, errors)
        document_status[path] = value
    for path in sorted(set(texts) - set(document_status)):
        errors.append(f"ADR source {path} was read but not reviewed")

    # 2. the ADR evidence catalog: material statements, each with its own status and disposition
    statements: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("statements", []) or [], 1):
        key = _text(item.get("key")) or f"S{number}"
        label = f"statement {key}"
        if key in statements:
            errors.append(f"{label} key is supplied twice")
        source = _text(item.get("source"))
        if source not in texts:
            errors.append(f"{label} source {source!r} is not a file read in this round")
        excerpt = _text(item.get("excerpt"))
        if not _quoted(excerpt, texts.get(source, "")):
            errors.append(f"{label} excerpt must be a verbatim quote of {source}")
        if not _text(item.get("reference")):
            errors.append(f"{label} requires reference (where in the file it is)")
        kind, statement_status = _text(item.get("kind")), _text(item.get("status"))
        if kind not in STATEMENT_KINDS:
            errors.append(f"{label} kind must be one of {STATEMENT_KINDS}")
        if statement_status not in STATEMENT_STATUSES:
            errors.append(f"{label} status must be one of {STATEMENT_STATUSES}")
        authority = _text(item.get("authority_evidence"))
        if statement_status == "APPROVED" and not _quoted(authority, texts.get(source, "")):
            errors.append(f"{label} is APPROVED: quote in authority_evidence the words of {source} that show the "
                          "approval — approval is never assumed or inferred from the folder")
        if _text(item.get("confidence")) not in CONFIDENCE:
            errors.append(f"{label} confidence must be one of {CONFIDENCE}")
        if not _text(item.get("meaning")):
            errors.append(f"{label} requires meaning (what it means for the project's behavior)")
        check_locale(f"{label}.meaning", item.get("meaning"), locale, errors)
        disposition = _text(item.get("disposition"))
        if disposition not in STATEMENT_DISPOSITIONS:
            errors.append(f"{label} disposition must be one of {STATEMENT_DISPOSITIONS}")
        if disposition in {"CONTEXT", "NO_TEST_IMPACT"} and len(_text(item.get("reason")).split()) < 3:
            errors.append(f"{label} {disposition} requires a reason (why it does not change any Test Case)")
        statements[key] = {
            "key": key, "source": source, "digest": context.get("digests", {}).get(source),
            "reference": _text(item.get("reference")), "excerpt": excerpt, "kind": kind, "status": statement_status,
            "authority_evidence": authority or None, "meaning": _text(item.get("meaning")),
            "concepts": _list(item.get("concepts")), "candidate_concepts": _list(item.get("candidate_concepts")),
            "confidence": _text(item.get("confidence")), "disposition": disposition,
            "reason": _text(item.get("reason")) or None}
    for path in sorted(set(texts) - {s["source"] for s in statements.values()}):
        if document_status.get(path) not in {"NO_MATERIAL_CONTENT"}:
            errors.append(f"ADR source {path} contributes no statement; catalog its material content or mark it "
                          "NO_MATERIAL_CONTENT with a summary")

    # 3. decisions: effective changes synthesized from statements (possibly across files); their
    #    authority is derived from the statements, never asserted
    decisions: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("decisions", []) or [], 1):
        key = _text(item.get("key")) or f"D{number}"
        label = f"decision {key}"
        if key in by_key or key in statements:
            errors.append(f"{label} key is not unique")
        supporting = _list(item.get("statements"))
        if not supporting:
            errors.append(f"{label} must name the statement(s) it is built from")
        unknown = [s for s in supporting if s not in statements]
        if unknown:
            errors.append(f"{label} names unknown statements {unknown}")
        backing = [statements[s] for s in supporting if s in statements]
        decision_status = derive_status([s["status"] for s in backing])
        official = _text(item.get("official_id")) or None
        if official and not any(official in texts.get(s["source"], "") for s in backing):
            errors.append(f"{label} official_id {official!r} appears in none of its sources; never pretend an id")
        relationship = _text(item.get("relationship"))
        if relationship not in RELATIONSHIPS:
            errors.append(f"{label} relationship must be one of {RELATIONSHIPS}")
        for field in ("statement", "affected_behavior"):
            if not _text(item.get(field)):
                errors.append(f"{label} requires {field}")
        check_locale(f"{label}.statement", item.get("statement"), locale, errors)
        if relationship in {"NO_TEST_IMPACT", "CONFIRMS", "CLARIFIES", "ALREADY_INCORPORATED"} and \
                len(_text(item.get("reason")).split()) < 3:
            errors.append(f"{label} {relationship} requires a reason")
        conflicting = _list(item.get("conflicting_statements"))
        for ref in conflicting:
            if ref not in statements:
                errors.append(f"{label} conflicting_statements names unknown statement {ref}")
        previous = item.get("previous_authority") if isinstance(item.get("previous_authority"), dict) else {}
        prev_reqs, prev_decisions = _list(previous.get("requirements")), _list(previous.get("decisions"))
        for ref in prev_reqs:
            if ref not in requirement_ids:
                errors.append(f"{label} previous_authority names unknown requirement {ref}")
        for ref in prev_decisions:
            if ref not in ledger:
                errors.append(f"{label} previous_authority names unknown earlier decision {ref}")
        if relationship in NEEDS_PREVIOUS and (not (prev_reqs or prev_decisions) or not _text(previous.get("statement"))):
            errors.append(f"{label} {relationship} requires previous_authority with the requirement(s) or earlier "
                          "decision(s) and the statement of the previous rule, which stays historically visible")
        if relationship in {"ALREADY_INCORPORATED", "REVOKES_DECISION"} and not prev_decisions:
            errors.append(f"{label} {relationship} requires previous_authority.decisions naming the earlier decision")
        if relationship == "REVOKES_DECISION" and decision_status != "APPROVED":
            errors.append(f"{label} only an APPROVED decision can revoke an earlier one")
        related_reqs = _list(item.get("related_requirements"))
        for ref in related_reqs:
            if ref not in requirement_ids:
                errors.append(f"{label} related_requirements names unknown requirement {ref}")
        related_tcs = _list(item.get("related_test_cases"))
        for ref in related_tcs:
            if ref not in known_cases:
                errors.append(f"{label} related_test_cases names unknown Test Case {ref}")
        for field, known in (("related_questions", question_ids), ("related_findings", finding_ids)):
            for ref in _list(item.get(field)):
                if ref not in known:
                    errors.append(f"{label} {field} names unknown {ref}")
        claims = []
        for index, claim in enumerate(item.get("claims", []) or [], 1):
            text, disposition = _text(claim.get("claim")), _text(claim.get("disposition"))
            if not text:
                errors.append(f"{label} claim {index} requires claim (the testable behavior)")
            if disposition not in CLAIM_DISPOSITIONS:
                errors.append(f"{label} claim {index} disposition must be one of {CLAIM_DISPOSITIONS}")
            claims.append({"claim": text, "disposition": disposition, "cases": _list(claim.get("cases")),
                           "question": _text(claim.get("question")) or None, "reason": _text(claim.get("reason")) or None})
        first = backing[0] if backing else {"source": "", "reference": "", "excerpt": ""}
        record = {
            "key": key, "official_id": official, "statements": supporting,
            "source": first["source"], "reference": first["reference"], "excerpt": first["excerpt"],
            "provenance": [{k: s[k] for k in ("key", "source", "digest", "reference", "excerpt", "status", "kind")}
                           for s in backing],
            "status": decision_status, "statement": _text(item.get("statement")),
            "affected_behavior": _text(item.get("affected_behavior")), "relationship": relationship,
            "reason": _text(item.get("reason")) or None, "conflicting_statements": conflicting,
            "authority_resolution": _text(item.get("authority_resolution")) or None,
            "previous_authority": {"requirements": prev_reqs, "decisions": prev_decisions,
                                   "statement": _text(previous.get("statement")) or None},
            "related_requirements": related_reqs, "related_test_cases": related_tcs,
            "related_questions": _list(item.get("related_questions")),
            "related_findings": _list(item.get("related_findings")), "claims": claims,
        }
        by_key[key] = record
        decisions.append(record)
    officials = [d["official_id"] for d in decisions if d["official_id"]]
    for official in {o for o in officials if officials.count(o) > 1}:
        errors.append(f"official decision id {official} is recorded twice in this round")
    for decision in decisions:
        earlier = ledger.get(decision["official_id"] or "")
        if earlier and earlier["source"] != decision["source"]:
            errors.append(f"decision {decision['key']} official id {decision['official_id']} already belongs to "
                          f"{earlier['source']}")
    for statement in statements.values():
        if statement["disposition"] == "DECISION" and not any(statement["key"] in d["statements"] for d in decisions):
            errors.append(f"statement {statement['key']} is dispositioned DECISION but no decision is built from it")
    classification = document_status

    # 4. Test Case actions
    entries: list[dict[str, Any]] = []
    refs: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(payload.get("test_cases", []) or [], 1):
        action = _text(item.get("action"))
        existing, key = _text(item.get("test")), _text(item.get("key"))
        ref = existing or key or f"<entry {number}>"
        label = f"test case {ref}"
        if action not in ACTIONS:
            errors.append(f"{label} action must be one of {ACTIONS}")
        if action == "CREATE":
            if existing or not key:
                errors.append(f"{label} CREATE names a new `key`, never an existing Test Case")
            if key in known_cases or key in by_key:
                errors.append(f"{label} key collides with an existing id")
        else:
            if not existing or existing not in known_cases:
                errors.append(f"{label} names unknown Test Case {existing!r}")
            elif existing not in active:
                errors.append(f"{label} is already superseded; act on its successor instead")
        if ref in refs:
            errors.append(f"{label} is listed twice")
        if _text(item.get("impact")) not in IMPACTS:
            errors.append(f"{label} impact must be DIRECT or INDIRECT")
        cited = _list(item.get("decisions"))
        if not cited:
            errors.append(f"{label} must cite the decision(s) of this round behind it")
        for decision_key in cited:
            if decision_key not in by_key:
                errors.append(f"{label} cites unknown decision {decision_key}")
        approved = [k for k in cited if by_key.get(k, {}).get("status") == "APPROVED"
                    and by_key[k]["relationship"] not in {"ALREADY_INCORPORATED", "NO_TEST_IMPACT"}]
        if action in WRITES_DEFINITION | {"SUPERSEDE"} and not approved:
            errors.append(f"{label} {action} needs an APPROVED decision that changes behavior; drafts, supporting "
                          "material and unclear authority become REVIEW_ONLY with a Question")
        reason = _text(item.get("reason"))
        if not reason:
            errors.append(f"{label} requires reason")
        check_locale(f"{label}.reason", reason, locale, errors)
        design = item.get("design") if isinstance(item.get("design"), dict) else None
        if action in WRITES_DEFINITION:
            if design is None:
                errors.append(f"{label} {action} requires the complete resulting design")
            else:
                _validate_design(design, label, locale, errors)
        elif design is not None:
            errors.append(f"{label} {action} must not carry a design; only UPDATE / CREATE change a definition")
        entry = {"ref": ref, "test": existing or None, "key": key or None, "action": action,
                 "impact": _text(item.get("impact")), "decisions": cited, "reason": reason,
                 "design": _design(design) if design else None,
                 "supersedes": _text(item.get("supersedes")) or None,
                 "superseded_by": _text(item.get("superseded_by")) or None}
        refs[ref] = entry
        entries.append(entry)
    creates = {e["key"]: e for e in entries if e["action"] == "CREATE"}
    for entry in entries:
        if entry["action"] == "SUPERSEDE":
            successor = creates.get(entry["superseded_by"] or "")
            if successor is None:
                errors.append(f"test case {entry['ref']} SUPERSEDE requires superseded_by naming a CREATE key")
            elif successor["supersedes"] != entry["test"]:
                errors.append(f"test case {successor['ref']} must declare supersedes {entry['test']}")
        if entry["action"] == "CREATE" and entry["supersedes"]:
            if refs.get(entry["supersedes"], {}).get("action") != "SUPERSEDE":
                errors.append(f"test case {entry['ref']} supersedes {entry['supersedes']}, which needs its own "
                              "SUPERSEDE entry")
    designs = [e["design"] for e in entries if e["design"]]
    errors.extend(mechanical_templates(designs, ("title", "state", "trigger", "expected"), "ADR test designs"))

    # 5. targeted expansion: every behavior-changing approved decision reviews every dimension once
    reviews = []
    for item in payload.get("dimension_reviews", []) or []:
        decision_key, dimension = _text(item.get("decision")), _text(item.get("dimension"))
        disposition, cases = _text(item.get("disposition")), _list(item.get("cases"))
        label = f"dimension review {decision_key}/{dimension}"
        if decision_key not in by_key:
            errors.append(f"{label} names unknown decision")
        if dimension not in DIMENSIONS:
            errors.append(f"{label} dimension must be one of the expansion dimensions")
        if disposition not in DIMENSION_DISPOSITIONS:
            errors.append(f"{label} disposition must be one of {DIMENSION_DISPOSITIONS}")
        if disposition == "MATERIALIZED" and not (cases and all(
                refs.get(c, {}).get("action") in WRITES_DEFINITION and decision_key in refs[c]["decisions"] for c in cases)):
            errors.append(f"{label} MATERIALIZED must name the UPDATE / CREATE entries of this decision")
        if disposition == "ALREADY_COVERED" and not (cases and all(c in active for c in cases)):
            errors.append(f"{label} ALREADY_COVERED must name the existing Test Cases that cover it")
        if disposition == "QUESTION_REQUIRED" and not _text(item.get("question")):
            errors.append(f"{label} QUESTION_REQUIRED must name the Question key")
        if disposition == "NOT_APPLICABLE" and len(_text(item.get("reason")).split()) < 3:
            errors.append(f"{label} NOT_APPLICABLE requires a reason")
        reviews.append({"decision": decision_key, "dimension": dimension, "disposition": disposition, "cases": cases,
                        "question": _text(item.get("question")) or None, "reason": _text(item.get("reason")) or None})

    # 6. Questions and Findings: linked to this round's decisions and statements, and to affected Test Cases only
    affected_refs = set(refs)
    questions = []
    for number, item in enumerate(payload.get("questions", []) or [], 1):
        key = _text(item.get("key")) or f"AQ{number}"
        label = f"question {key}"
        for field in ("question", "reason"):
            if not _text(item.get(field)):
                errors.append(f"{label} requires {field}")
            check_locale(f"{label}.{field}", item.get(field), locale, errors)
        impact = _text(item.get("impact")) or "REQUIREMENT_AMBIGUITY"
        if impact not in QUESTION_IMPACTS:
            errors.append(f"{label} impact must be one of {sorted(QUESTION_IMPACTS)}")
        linked = _list(item.get("decisions"))
        if not linked or not set(linked) <= set(by_key):
            errors.append(f"{label} must name the decision(s) of this round it is about")
        for ref in _list(item.get("requirements")):
            if ref not in requirement_ids:
                errors.append(f"{label} names unknown requirement {ref}")
        for ref in _list(item.get("tests")):
            if ref not in affected_refs:
                errors.append(f"{label} links {ref}, which is not an affected Test Case of this round; list it in "
                              "test_cases (an unaffected Test Case is never changed)")
        for ref in _list(item.get("statements")):
            if ref not in statements:
                errors.append(f"{label} names unknown statement {ref}")
        questions.append({"key": key, "question": _text(item.get("question")), "reason": _text(item.get("reason")),
                          "impact": impact, "blocking": bool(item.get("blocking", False)), "decisions": linked,
                          "statements": _list(item.get("statements")),
                          "requirements": _list(item.get("requirements")), "tests": _list(item.get("tests"))})
    question_keys = {q["key"] for q in questions}
    findings = []
    for number, item in enumerate(payload.get("findings", []) or [], 1):
        key = _text(item.get("key")) or f"AF{number}"
        label = f"finding {key}"
        if _text(item.get("type")) not in FINDING_TYPES:
            errors.append(f"{label} type must be one of {sorted(FINDING_TYPES)}")
        if not _text(item.get("statement")):
            errors.append(f"{label} requires statement")
        check_locale(f"{label}.statement", item.get("statement"), locale, errors)
        linked = _list(item.get("decisions"))
        if not linked or not set(linked) <= set(by_key):
            errors.append(f"{label} must name the decision(s) of this round it is about")
        for ref in _list(item.get("statements")):
            if ref not in statements:
                errors.append(f"{label} names unknown statement {ref}")
        for ref in _list(item.get("tests")):
            if ref not in affected_refs:
                errors.append(f"{label} links {ref}, which is not an affected Test Case of this round")
        for ref in _list(item.get("questions")):
            if ref not in question_keys and ref not in question_ids:
                errors.append(f"{label} links unknown Question {ref}")
        source_refs = [r for r in item.get("source_refs", []) or [] if isinstance(r, dict)]
        if not source_refs:
            errors.append(f"{label} requires source_refs to the evidence that shows it")
        for ref in source_refs:
            if _text(ref.get("source")) not in adr_paths | set(context["parent_sources"]) or not _text(ref.get("reference")):
                errors.append(f"{label} source_ref {ref.get('source')!r} is not an ADR file or a parent source with a locator")
        findings.append({"key": key, "type": _text(item.get("type")), "statement": _text(item.get("statement")),
                         "decisions": linked, "statements": _list(item.get("statements")),
                         "requirements": _list(item.get("requirements")),
                         "tests": _list(item.get("tests")), "questions": _list(item.get("questions")),
                         "source_refs": [{"source": _text(r.get("source")), "reference": _text(r.get("reference"))}
                                         for r in source_refs]})
    for review in reviews:
        if review["disposition"] == "QUESTION_REQUIRED" and review["question"] not in question_keys:
            errors.append(f"dimension review {review['decision']}/{review['dimension']} names unknown Question "
                          f"{review['question']}")

    # 7. dispositions of existing Questions and Findings
    question_dispositions = _dispositions(payload.get("question_dispositions"), question_ids, QUESTION_DISPOSITIONS,
                                          "question", by_key, errors)
    finding_dispositions = _dispositions(payload.get("finding_dispositions"), finding_ids, FINDING_DISPOSITIONS,
                                         "finding", by_key, errors)

    # 8. no silent supersession, no unexplained statement, decision or change
    questioned = {d for q in questions for d in q["decisions"]}
    cited = {d for e in entries for d in e["decisions"]}
    for decision in decisions:
        label = f"decision {decision['key']}"
        if decision["relationship"] in {"UNCLEAR", "CONFLICTS_WITH"} and decision["key"] not in questioned:
            errors.append(f"{label} is {decision['relationship']}: raise the Question that resolves it")
        if decision["status"] != "APPROVED" and decision["relationship"] in BEHAVIOR_CHANGING and \
                decision["key"] not in questioned:
            errors.append(f"{label} would change behavior but is {decision['status']}, not APPROVED; it never "
                          "supersedes the existing authority silently — raise a Question")
        if decision["status"] == "APPROVED" and decision["relationship"] in BEHAVIOR_CHANGING:
            if decision["key"] not in cited and decision["key"] not in questioned:
                errors.append(f"{label} changes behavior: map the Test Cases it affects (or raise a Question)")
            covered = {r["dimension"] for r in reviews if r["decision"] == decision["key"]}
            listed = [r["dimension"] for r in reviews if r["decision"] == decision["key"]]
            missing = [d for d in DIMENSIONS if d not in covered]
            if missing:
                errors.append(f"{label} changes behavior: review every expansion dimension for the affected slice "
                              f"(missing {missing})")
            if len(listed) != len(set(listed)):
                errors.append(f"{label} reviews a dimension twice")
    for statement in statements.values():
        for disposition, items in (("QUESTION", questions), ("FINDING", findings)):
            if statement["disposition"] == disposition and not any(statement["key"] in i["statements"] for i in items):
                errors.append(f"statement {statement['key']} is dispositioned {disposition} but no "
                              f"{disposition.lower()} names it")
    for decision in decisions:
        label = f"decision {decision['key']}"
        if decision["conflicting_statements"]:
            settled = decision["status"] == "APPROVED" and decision["authority_resolution"] and all(
                statements.get(s, {}).get("status") != "APPROVED" for s in decision["conflicting_statements"])
            if not settled and decision["key"] not in questioned:
                errors.append(f"{label} has conflicting statements that authority does not settle; never vote or pick "
                              "one: raise a Question (or state authority_resolution when an approved statement "
                              "overrides non-approved ones)")
        behavior = decision["status"] == "APPROVED" and decision["relationship"] in BEHAVIOR_CHANGING
        if behavior and not decision["claims"]:
            errors.append(f"{label} changes behavior: list its testable claims and how each is covered (existing, "
                          "updated, new Test Case, Question or not testable)")
        for index, claim in enumerate(decision["claims"], 1):
            where, cases = f"{label} claim {index}", claim["cases"]
            if claim["disposition"] == "COVERED_BY_EXISTING" and not (cases and all(c in active for c in cases)):
                errors.append(f"{where} COVERED_BY_EXISTING must name the existing Test Cases covering it")
            if claim["disposition"] in {"COVERED_BY_UPDATE", "NEW_TEST"}:
                wanted = "UPDATE" if claim["disposition"] == "COVERED_BY_UPDATE" else "CREATE"
                if not cases or not all(refs.get(c, {}).get("action") == wanted and decision["key"] in refs[c]["decisions"]
                                        for c in cases):
                    errors.append(f"{where} {claim['disposition']} must name the {wanted} entries of this decision")
            if claim["disposition"] == "QUESTION" and claim["question"] not in question_keys:
                errors.append(f"{where} QUESTION must name a Question key of this analysis")
            if claim["disposition"] == "NOT_TESTABLE" and len((claim["reason"] or "").split()) < 3:
                errors.append(f"{where} NOT_TESTABLE requires a reason")
    for entry in entries:
        if entry["action"] in WRITES_DEFINITION and not any(
                entry["ref"] in claim["cases"] for d in entry["decisions"] if d in by_key for claim in by_key[d]["claims"]):
            errors.append(f"test case {entry['ref']} {entry['action']} is not traced to a claim of its decisions "
                          "(COVERED_BY_UPDATE / NEW_TEST)")
    return {"errors": errors, "classification": classification, "statements": list(statements.values()),
            "decisions": decisions, "test_cases": entries,
            "dimension_reviews": reviews, "questions": questions, "findings": findings,
            "question_dispositions": question_dispositions, "finding_dispositions": finding_dispositions}


def _validate_design(design: dict[str, Any], label: str, locale: str, errors: list[str]) -> None:
    extra = sorted(set(design) - DESIGN_FIELDS)
    if extra:
        errors.append(f"{label} design contains runtime-owned or unknown fields {extra}")
    validate_test_intent(design, f"{label} design", locale, errors)
    if _text(design.get("basis") or "ACCEPTANCE") not in BASES:
        errors.append(f"{label} design basis must be one of {BASES}")
    if _text(design.get("dimension")) and _text(design.get("dimension")) not in DIMENSIONS:
        errors.append(f"{label} design dimension must be one of the expansion dimensions")
    expected = _text(design.get("expected"))
    if expected and (ABSTRACT_OBSERVATION.search(expected) or semantically_empty(expected, set())):
        errors.append(f"{label} design expected result names nothing observable ({expected!r})")
    if expected and _text(design.get("basis") or "ACCEPTANCE") == "ACCEPTANCE" and compound_signals(expected):
        errors.append(f"{label} design expected result joins independently diagnosable outcomes; one failure "
                      "domain per Test Case")


def _design(design: dict[str, Any]) -> dict[str, Any]:
    result = {field: _text(design.get(field)) for field in sorted(DESIGN_FIELDS)}
    result["basis"] = result["basis"] or "ACCEPTANCE"
    result["priority"] = result["priority"] if result["priority"] in PRIORITIES else result["priority"]
    result["dimension"] = result["dimension"] or None
    return result


def _dispositions(raw: Any, known: set[str], allowed: tuple[str, ...], kind: str, decisions: dict[str, Any],
                  errors: list[str]) -> list[dict[str, Any]]:
    result, seen = [], set()
    for item in raw or []:
        ref, disposition, decision = _text(item.get(kind)), _text(item.get("disposition")), _text(item.get("decision"))
        label = f"{kind} disposition {ref}"
        if ref not in known:
            errors.append(f"{label} names an unknown existing {kind}")
        if ref in seen:
            errors.append(f"{label} is given twice")
        seen.add(ref)
        if disposition not in allowed:
            errors.append(f"{label} must be one of {allowed}")
        if decision not in decisions:
            errors.append(f"{label} must name the decision of this round behind it")
        elif disposition in {"RESOLVED_BY_ADR", "SUPERSEDED_BY_ADR"} and decisions[decision]["status"] != "APPROVED":
            errors.append(f"{label} {disposition} needs an APPROVED decision")
        if not _text(item.get("reason")):
            errors.append(f"{label} requires reason")
        result.append({kind: ref, "disposition": disposition, "decision": decision, "reason": _text(item.get("reason"))})
    return result

