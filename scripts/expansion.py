#!/usr/bin/env python3
"""Mandatory second-pass QA expansion after the normative baseline is frozen.

Every dimension is evaluated, operator mistakes and failure surfaces are walked as
explicit checklists, existing tests challenge the suite, and use-case journeys get an
explicit disposition. A zero-result dimension is valid only because it was evaluated.
Nothing here edits the frozen normative baseline; expansion is additive.
"""

from __future__ import annotations

from typing import Any

from common import StageError, jaccard, normalize, normalize_identifier, similarity
from design import (
    check_locale, traceability, unknown_keys, validate_questions_and_findings, validate_test_intent,
)


DIMENSIONS = (
    "NEGATIVE", "BOUNDARY", "OPERATOR_ERROR", "MISUSE", "STATE_TRANSITION", "DECISION_TABLE",
    "CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY", "INTEGRATION", "RECOVERY", "CHAOS",
    "SECURITY", "AUTHORIZATION", "DATA_INTEGRITY", "CROSS_REQUIREMENT", "E2E",
)
# Universal reasoning prompts, not domain models: the model decides how, or whether,
# each one applies to the analyzed project. Python never generates a scenario from them.
OPERATOR_PATTERNS = {
    "WRONG_RESOURCE": "the right action applied to the wrong entity or resource",
    "WRONG_ASSOCIATION": "an entity linked to the wrong parent, document or owner",
    "WRONG_ACTOR": "the action performed by an actor without the expected role",
    "WRONG_STATE": "the action attempted while the entity is in a state that does not allow it",
    "WRONG_SEQUENCE": "steps performed out of the documented order",
    "REPEATED_ACTION": "the same action submitted or triggered twice",
    "OMITTED_ACTION": "a required step skipped",
    "STALE_OPERATION": "acting on data that changed since it was displayed",
    "PARTIAL_OPERATION": "only part of a multi-entity operation performed",
    "CROSS_CONTEXT_MISTAKE": "an action meant for one context (document, account, tenant) applied to another",
    "PHYSICAL_DIGITAL_MISMATCH": "the real-world object or fact differs from what the system recorded",
    "WRONG_ACKNOWLEDGEMENT": "confirming or acknowledging the wrong alert, item or step",
    "MANUAL_AFTER_AUTOMATIC": "a manual action repeated after automatic processing already happened",
    "ABANDONED_OPERATION": "an operation started and left unfinished",
}
FAILURE_SURFACES = {
    "EXTERNAL_DEPENDENCY": "a third-party or external service the project depends on",
    "NETWORK": "network unavailable, slow or unstable",
    "MIDDLEWARE": "an intermediary between producers and the application",
    "DEVICE_HARDWARE": "client devices, equipment or hardware in the workflow",
    "CACHE": "a cache the behavior relies on",
    "DATABASE": "the persistence layer failing, locking or rolling back",
    "ASYNC_WORKER": "background jobs, schedulers or queues",
    "RETRY": "a client or integration retrying after a timeout or error",
    "DUPLICATE_EVENT": "the same event or request delivered more than once",
    "OUT_OF_ORDER_EVENT": "events arriving in a different order than produced",
    "PARTIAL_COMMIT": "a multi-part change only partly applied or confirmed",
    "PROCESS_RESTART": "the application or a component restarting mid-operation",
    "SESSION_INTERRUPTION": "a user session expiring or being lost mid-operation",
    "CONCURRENCY": "several actors or processes changing related data at once",
    "RACE_CONDITION": "outcome depending on the timing of competing operations",
}
CANDIDATE_DISPOSITIONS = {"MATERIALIZED", "ALREADY_COVERED", "QUESTION_REQUIRED", "NOT_APPLICABLE"}
EXPANSION_BASES = {"DERIVED", "CHARACTERIZATION", "EXPLORATORY"}
ASSET_DISPOSITIONS = {
    "ALREADY_COVERED_BY", "PROMOTE_DERIVED", "PROMOTE_CHARACTERIZATION", "QUESTION_REQUIRED",
    "TECHNICAL_ONLY", "DUPLICATE", "OUT_OF_SCOPE_WITH_REASON",
}
INTENT_FIELDS = ("actor", "state", "trigger", "failure_domain", "expected")
ADVERSARIAL_DIMENSIONS = {
    "NEGATIVE", "BOUNDARY", "OPERATOR_ERROR", "MISUSE", "CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY",
    "INTEGRATION", "RECOVERY", "CHAOS", "SECURITY", "AUTHORIZATION",
}
ALIGNMENT_THRESHOLDS = {
    "actor": 0.34, "state": 0.34, "trigger": 0.34, "failure_domain": 0.4, "expected": 0.34,
}
STRICT_FIELDS = {"failure_domain", "expected"}
EXPANSION_KEYS = {"dimensions", "test_assets", "questions", "findings"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def intent_alignment(intent: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Compare trigger, actor/context, state, failure domain and expected outcome.

    ALREADY_COVERED is a semantic claim: a generic Test Case that merely shares a target
    id with an unrelated behavior does not cover it.
    """
    # Context fields may be phrased more or less specifically (containment); what fails and
    # what is observed must genuinely match (Jaccard), or a generic test would absorb it.
    scores = {
        field: round((jaccard if field in STRICT_FIELDS else similarity)(intent.get(field), target.get(field)), 3)
        for field in INTENT_FIELDS
    }
    misaligned = [field for field, minimum in ALIGNMENT_THRESHOLDS.items() if scores[field] < minimum]
    return {"scores": scores, "aligned": not misaligned, "misaligned_fields": misaligned}


def _copied(intent: dict[str, Any], target: dict[str, Any]) -> bool:
    same = sum(normalize(intent.get(field)) == normalize(target.get(field)) for field in INTENT_FIELDS)
    return same >= 4


def _test_text(target: dict[str, Any]) -> str:
    return " ".join(str(target.get(field, "")) for field in ("title", "state", "trigger", "expected", "failure_domain"))


def _happy_path(target: dict[str, Any]) -> bool:
    """An Acceptance test of plain functional behavior exercises no failure condition."""
    return target["basis"] == "ACCEPTANCE" and target["primary_type"] in {"FUNCTIONAL", "FIELD", "PERFORMANCE"}


def _resolve_test(ref: str, tests_by_ref: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return tests_by_ref.get(ref)


def validate_expansion(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, EXPANSION_KEYS, "expansion")
    locale = context["locale"]
    context = {**context, "authority": {normalize_identifier(e["identifier"]): e for e in context["authority_index"]}}
    design = context["design"]
    roles = {record["path"]: record["role"] for record in context["source_records"]}
    requirement_keys = {item["key"] for item in design["requirements"]}
    claims_by_key = {claim["key"]: claim for claim in design["claims"]}
    baseline_tests = design["tests"]
    families = {normalize(test["family"]) for test in baseline_tests}
    taken = set(context["taken_keys"])
    questions, findings = validate_questions_and_findings(
        payload, requirement_keys, locale, errors, "expansion", taken,
    )
    question_keys = {item["key"] for item in [*design["questions"], *questions]}
    finding_keys = {item["key"] for item in [*design["findings"], *findings]}

    tests: list[dict[str, Any]] = []
    tests_by_ref: dict[str, dict[str, Any]] = {test["key"]: test for test in baseline_tests}
    for test in baseline_tests:
        if test.get("id"):
            tests_by_ref[test["id"]] = test
    candidates: list[dict[str, Any]] = []
    pending_coverage: list[tuple[str, dict[str, Any], list[str], dict[str, Any]]] = []
    pending_e2e: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    asset_targets: dict[tuple[str, ...], list[tuple[str, dict[str, Any]]]] = {}

    def build_test(raw: dict[str, Any], label: str, dimension: str, basis_hint: str | None) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            errors.append(f"{label} requires a test design")
            return None
        key = _text(raw.get("key"))
        if not key or key in taken:
            errors.append(f"{label} test requires a unique key")
        taken.add(key)
        basis = str(raw.get("basis") or basis_hint or "")
        if dimension == "E2E":
            basis = "E2E"
        elif basis not in EXPANSION_BASES:
            errors.append(f"{label} basis must be one of {sorted(EXPANSION_BASES)}")
        validate_test_intent(raw, label, locale, errors)
        oracle = raw.get("oracle_source")
        if basis == "DERIVED":
            if not isinstance(oracle, dict) or roles.get(str(oracle.get("source"))) != "FUNCTIONAL_AUTHORITY":
                errors.append(f"{label} is DERIVED and needs oracle_source in Functional Authority")
        if basis == "CHARACTERIZATION":
            if not isinstance(oracle, dict) or roles.get(str(oracle.get("source"))) not in {
                "IMPLEMENTATION_EVIDENCE", "TEST_ASSET",
            }:
                errors.append(f"{label} is CHARACTERIZATION and needs oracle_source in implementation evidence or a test asset")
        question_refs = [str(value) for value in raw.get("questions", []) or []]
        if basis == "EXPLORATORY" and not question_refs:
            errors.append(f"{label} is EXPLORATORY and must link the Question about the undefined policy")
        for value in question_refs:
            if value not in question_keys:
                errors.append(f"{label} links unknown question {value}")
        for value in raw.get("findings", []) or []:
            if str(value) not in finding_keys:
                errors.append(f"{label} links unknown finding {value}")
        anchors = [str(value) for value in raw.get("anchors", []) or []]
        anchored = [claims_by_key[value] for value in anchors if value in claims_by_key]
        if basis != "E2E":
            if not anchors or len(anchored) != len(anchors):
                errors.append(f"{label} must anchor to known normative claim keys")
            if any(claim["destination"] != "TEST" for claim in anchored):
                errors.append(f"{label} anchors must be claims with destination TEST")
        test = {
            "key": key, "basis": basis, "dimension": dimension,
            "claims": [claim["id"] for claim in anchored], "claim_keys": anchors,
            **traceability(anchored, raw.get("related_identifiers"), label, context["authority"],
                           context["authority_texts"], design["requirements"], errors),
            "source_refs": [ref for claim in anchored for ref in claim["source_refs"]]
            + ([dict(oracle)] if isinstance(oracle, dict) else []),
            **{field: _text(raw.get(field)) for field in (
                "title", "objective", "family", "actor", "state", "trigger", "expected",
                "failure_domain", "priority_reason",
            )},
            "primary_type": str(raw.get("primary_type", "FUNCTIONAL")),
            "priority": str(raw.get("priority", "MEDIUM")),
            "question_keys": question_refs,
            "finding_keys": [str(value) for value in raw.get("findings", []) or []],
            "event": _text(raw.get("event")) or None, "indivisible_contract": None,
            "pattern": None, "surface": None, "stage": "expansion",
            "stages": raw.get("stages", []) if basis == "E2E" else [],
            "use_case": _text(raw.get("use_case")) or None,
        }
        tests.append(test)
        tests_by_ref[key] = test
        return test

    # --- dimensions ------------------------------------------------------------------
    records = {}
    for record in payload.get("dimensions", []) or []:
        dimension = str(record.get("dimension", ""))
        if dimension not in DIMENSIONS:
            errors.append(f"unknown expansion dimension {dimension!r}")
            continue
        if dimension in records:
            errors.append(f"dimension {dimension} is evaluated twice")
        records[dimension] = record
        if not _text(record.get("summary")):
            errors.append(f"dimension {dimension} requires a summary of how it was evaluated")
        check_locale(f"dimension {dimension}.summary", record.get("summary"), locale, errors)
        for number, candidate in enumerate(record.get("candidates", []) or [], 1):
            key = _text(candidate.get("key")) or f"{dimension}-{number}"
            label = f"{dimension} candidate {key}"
            disposition = str(candidate.get("disposition", ""))
            if disposition not in CANDIDATE_DISPOSITIONS:
                errors.append(f"{label} disposition must be one of {sorted(CANDIDATE_DISPOSITIONS)}")
            if not _text(candidate.get("description")):
                errors.append(f"{label} requires a description")
            check_locale(f"{label}.description", candidate.get("description"), locale, errors)
            pattern = _text(candidate.get("pattern")) or None
            surface = _text(candidate.get("surface")) or None
            if pattern and pattern not in OPERATOR_PATTERNS:
                errors.append(f"{label} pattern must be one of {sorted(OPERATOR_PATTERNS)}")
            if surface and surface not in FAILURE_SURFACES:
                errors.append(f"{label} surface must be one of {sorted(FAILURE_SURFACES)}")
            entry = {
                "key": key, "dimension": dimension, "disposition": disposition,
                "description": _text(candidate.get("description")), "pattern": pattern,
                "surface": surface, "use_case": _text(candidate.get("use_case")) or None,
                "test_ref": None, "covered_by": [], "question": None, "reason": None,
                "alignment": None, "shared_policy": _text(candidate.get("shared_policy")) or None,
            }
            if disposition == "MATERIALIZED":
                test = build_test(candidate.get("test"), label, dimension, None)
                if test:
                    test["pattern"], test["surface"] = pattern, surface
                    if dimension == "E2E":
                        test["use_case"] = entry["use_case"] or test["use_case"]
                        pending_e2e.append((label, test, candidate))
                    entry["test_ref"] = test["key"]
            elif disposition == "ALREADY_COVERED":
                covered = [str(value) for value in candidate.get("covered_by", []) or []]
                entry["covered_by"] = covered
                if dimension == "E2E":
                    if len(covered) < 2 or not _text(candidate.get("reason")):
                        errors.append(f"{label}: a journey covered by atomics lists at least two tests and a reason")
                    entry["reason"] = _text(candidate.get("reason"))
                    pending_coverage.append((label, candidate, covered, entry | {"journey": True}))
                else:
                    if not covered:
                        errors.append(f"{label} is ALREADY_COVERED without covered_by")
                    pending_coverage.append((label, candidate, covered, entry))
            elif disposition == "QUESTION_REQUIRED":
                question = _text(candidate.get("question"))
                if question not in question_keys:
                    errors.append(f"{label} requires a known question key")
                entry["question"] = question
            elif disposition == "NOT_APPLICABLE":
                entry["reason"] = _text(candidate.get("reason"))
                if not entry["reason"]:
                    errors.append(f"{label} is NOT_APPLICABLE without a reason")
            candidates.append(entry)
    missing = [dimension for dimension in DIMENSIONS if dimension not in records]
    if missing:
        errors.append("dimensions were not evaluated: " + ", ".join(missing))

    # --- checklists: operator mistakes and failure surfaces ---------------------------
    reviews = {
        "OPERATOR_ERROR": _checklist(
            records.get("OPERATOR_ERROR", {}).get("patterns_reviewed"), OPERATOR_PATTERNS,
            "pattern", candidates, "OPERATOR_ERROR patterns_reviewed", errors,
        ),
        "CHAOS": _checklist(
            records.get("CHAOS", {}).get("surfaces_reviewed"), FAILURE_SURFACES,
            "surface", candidates, "CHAOS surfaces_reviewed", errors,
        ),
    }

    # --- test assets: existing tests challenge the suite ------------------------------
    assets = {item["asset"]: item for item in context["test_assets"]}
    challenge: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for item in payload.get("test_assets", []) or []:
        asset = _text(item.get("asset"))
        label = f"test asset {asset or '<missing>'}"
        if asset not in assets:
            errors.append(f"{label} was not discovered in the selected Test Assets")
            continue
        if asset in seen_assets:
            errors.append(f"{label} is dispositioned twice")
        seen_assets.add(asset)
        disposition = str(item.get("disposition", ""))
        if disposition not in ASSET_DISPOSITIONS:
            errors.append(f"{label} disposition must be one of {sorted(ASSET_DISPOSITIONS)}")
        intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
        record = {
            "asset": asset, "source": assets[asset]["source"], "disposition": disposition, "dimension": None,
            "intent": {field: _text(intent.get(field)) for field in INTENT_FIELDS},
            "covered_by": [], "test_ref": None, "question": None,
            "reason": _text(item.get("reason")) or None, "alignment": None,
        }
        if disposition in {"ALREADY_COVERED_BY", "PROMOTE_DERIVED", "PROMOTE_CHARACTERIZATION"}:
            if any(not record["intent"][field] for field in INTENT_FIELDS):
                errors.append(f"{label} requires a normalized intent ({', '.join(INTENT_FIELDS)})")
            else:
                for field in ("trigger", "failure_domain", "expected"):
                    check_locale(f"{label}.intent.{field}", record["intent"][field], locale, errors)
        if disposition == "ALREADY_COVERED_BY":
            covered = [str(value) for value in item.get("covered_by", []) or []]
            record["covered_by"] = covered
            if not covered:
                errors.append(f"{label} is ALREADY_COVERED_BY without covered_by")
            pending_coverage.append((label, {"intent": record["intent"]}, covered, record))
        elif disposition in {"PROMOTE_DERIVED", "PROMOTE_CHARACTERIZATION"}:
            raw = dict(item.get("test") or {})
            basis = "DERIVED" if disposition == "PROMOTE_DERIVED" else "CHARACTERIZATION"
            if basis == "CHARACTERIZATION" and not raw.get("oracle_source"):
                raw["oracle_source"] = {"source": assets[asset]["source"], "reference": assets[asset]["reference"]}
            test = build_test(raw, label, str(item.get("dimension") or "DATA_INTEGRITY"), basis)
            if test:
                test["basis"] = basis
                test["source_refs"].append({"source": assets[asset]["source"], "reference": assets[asset]["reference"]})
                record["test_ref"] = test["key"]
        elif disposition == "QUESTION_REQUIRED":
            record["question"] = _text(item.get("question"))
            if record["question"] not in question_keys:
                errors.append(f"{label} requires a known question key")
        elif disposition == "DUPLICATE":
            duplicate = _text(item.get("duplicate_of"))
            if duplicate not in assets or duplicate == asset or not record["reason"]:
                errors.append(f"{label} DUPLICATE requires duplicate_of naming another asset and a reason")
            record["duplicate_of"] = duplicate
        elif not record["reason"]:
            errors.append(f"{label} {disposition} requires a reason")
        challenge.append(record)
    unreviewed = sorted(set(assets) - seen_assets)
    if unreviewed:
        errors.append(
            f"{len(unreviewed)} discovered test asset behavior(s) have no challenge disposition: "
            + ", ".join(unreviewed[:15]) + (" ..." if len(unreviewed) > 15 else "")
        )

    # --- deferred checks that need every expansion test ---------------------------------
    for label, raw, covered, entry in pending_coverage:
        targets = [_resolve_test(ref, tests_by_ref) for ref in covered]
        if any(target is None for target in targets):
            errors.append(f"{label} covered_by references unknown tests {covered}")
            continue
        if any(target["basis"] == "E2E" for target in targets):
            errors.append(f"{label} cannot be covered by an E2E composition")
        if entry.get("journey"):
            continue
        intent = raw.get("intent") if isinstance(raw.get("intent"), dict) else {}
        if any(not _text(intent.get(field)) for field in INTENT_FIELDS):
            errors.append(f"{label} ALREADY_COVERED requires the candidate intent ({', '.join(INTENT_FIELDS)})")
            continue
        results = [intent_alignment(intent, target) for target in targets]
        best = max(results, key=lambda value: sum(value["scores"].values()))
        entry["alignment"] = best
        if not any(result["aligned"] for result in results):
            errors.append(
                f"{label} is not semantically covered by {covered}: "
                f"misaligned {best['misaligned_fields']} (scores {best['scores']})"
            )
        if any(_copied(intent, target) for target in targets):
            errors.append(
                f"{label} intent repeats the target test word for word; describe the scenario actually "
                "considered (its own trigger, context, failure condition and oracle)"
            )
        description = _text(raw.get("description"))
        if description and not any(similarity(description, _test_text(target)) >= 0.25 for target in targets):
            errors.append(f"{label} description does not describe the behavior of {covered}")
        adversarial = entry.get("pattern") or entry.get("surface") or entry.get("dimension") in ADVERSARIAL_DIMENSIONS
        if adversarial and all(_happy_path(target) for target in targets):
            errors.append(
                f"{label} is an adversarial or failure scenario; a happy-path test {covered} does not exercise it"
            )
        if entry.get("asset"):
            asset_targets.setdefault(tuple(covered), []).append((entry["asset"], intent))

    # Different existing tests may share a target only when they describe the same failure.
    for covered, members in asset_targets.items():
        for index, (left_asset, left) in enumerate(members):
            for right_asset, right in members[index + 1:]:
                if jaccard(left["failure_domain"], right["failure_domain"]) < 0.4 and jaccard(left["expected"], right["expected"]) < 0.4:
                    errors.append(
                        f"test assets {left_asset} and {right_asset} describe different behaviors but converge on {list(covered)}"
                    )

    # One unresolved Question may cover several failure surfaces only for a shared policy.
    surfaces_by_question: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["disposition"] == "QUESTION_REQUIRED" and candidate["surface"]:
            surfaces_by_question.setdefault(candidate["question"], {})[candidate["surface"]] = candidate
    for question, by_surface in surfaces_by_question.items():
        if len(by_surface) > 1 and any(len(_text(c.get("shared_policy")).split()) < 5 for c in by_surface.values()):
            errors.append(
                f"question {question} dispositions surfaces {sorted(by_surface)}; each failure surface needs its "
                "own disposition unless shared_policy explains the single unresolved policy"
            )

    for label, test, candidate in pending_e2e:
        stages = test["stages"] if isinstance(test["stages"], list) else []
        atomics = []
        for index, stage in enumerate(stages, 1):
            target = _resolve_test(_text(stage.get("test")), tests_by_ref)
            if target is None or target["basis"] == "E2E":
                errors.append(f"{label} stage {index} must compose an existing atomic test")
                continue
            if not _text(stage.get("name")) or not _text(stage.get("trigger")) or not _text(stage.get("observation")):
                errors.append(f"{label} stage {index} requires name, trigger and observation")
            triggered = similarity(stage.get("trigger"), f"{target['trigger']} {target['title']}") >= 0.34
            observed = jaccard(stage.get("observation"), target["expected"]) >= 0.3
            if not (triggered and observed):
                errors.append(
                    f"{label} stage {index} does not map to the behavior of {stage.get('test')} "
                    "(trigger/observation unrelated to the composed atomic test)"
                )
            atomics.append(target)
        distinct = {target["key"] for target in atomics}
        if len(distinct) < 2:
            errors.append(f"{label} must compose at least two distinct atomic stages")
        test["composes_keys"] = [target["key"] for target in atomics]
        test["claims"] = list(dict.fromkeys(c for target in atomics for c in target["claims"]))
        test["requirement_refs"] = list(dict.fromkeys(r for target in atomics for r in target["requirement_refs"]))
        test["identifiers"] = list(dict.fromkeys(i for target in atomics for i in target["identifiers"]))
        test["source_refs"] = [ref for target in atomics for ref in target["source_refs"]]

    journeys = _journeys(context["authority_index"], candidates, errors)
    if errors:
        raise StageError("expansion", errors)
    return {
        "tests": tests, "candidates": candidates, "questions": questions, "findings": findings,
        "dimension_summary": dimension_summary(records, candidates),
        "checklists": reviews, "test_asset_challenge": challenge, "journeys": journeys,
        "unknown_family_titles": sorted({normalize(t["family"]) for t in tests} - families),
    }


def _checklist(
    entries: Any, catalog: dict[str, str], field: str,
    candidates: list[dict[str, Any]], label: str, errors: list[str],
) -> list[dict[str, Any]]:
    """Walk a generic checklist; each item links candidates or is explicitly not applicable."""
    reviewed: dict[str, dict[str, Any]] = {}
    for entry in entries or []:
        items = [str(value) for value in entry.get("items", []) or []]
        status = str(entry.get("status", ""))
        unknown = sorted(set(items) - set(catalog))
        if unknown:
            errors.append(f"{label} names unknown items {unknown}")
        if status not in {"CANDIDATES", "NOT_APPLICABLE"}:
            errors.append(f"{label} status must be CANDIDATES or NOT_APPLICABLE")
        if status == "NOT_APPLICABLE" and not _text(entry.get("reason")):
            errors.append(f"{label} NOT_APPLICABLE requires a reason for {items}")
        for item in items:
            if item in reviewed:
                errors.append(f"{label} reviews {item} twice")
            # A mistake or failure surface may be evaluated under any dimension.
            linked = [candidate["key"] for candidate in candidates if candidate[field] == item]
            if status == "CANDIDATES" and not linked:
                errors.append(f"{label} marks {item} as CANDIDATES but no candidate carries {field}={item}")
            reviewed[item] = {
                "item": item, "status": status, "reason": _text(entry.get("reason")) or None,
                "candidates": linked,
            }
    missing = [item for item in catalog if item not in reviewed]
    if missing:
        errors.append(f"{label} did not evaluate: " + ", ".join(missing))
    return list(reviewed.values())


def _journeys(
    authority_index: list[dict[str, Any]], candidates: list[dict[str, Any]], errors: list[str],
) -> list[dict[str, Any]]:
    """Every documented use case receives one explicit end-to-end journey disposition."""
    by_use_case: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["dimension"] == "E2E" and candidate["use_case"]:
            by_use_case.setdefault(normalize_identifier(candidate["use_case"]), []).append(candidate)
    journeys = []
    for entry in authority_index:
        if entry["kind"] != "USE_CASE":
            continue
        key = normalize_identifier(entry["identifier"])
        found = by_use_case.get(key, [])
        if not found:
            errors.append(f"use case {entry['identifier']} has no E2E journey disposition")
            continue
        journeys.append({
            "use_case": entry["identifier"], "title": entry["title"],
            "dispositions": [candidate["disposition"] for candidate in found],
            "candidates": [candidate["key"] for candidate in found],
        })
    return journeys


def dimension_summary(records: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for dimension in DIMENSIONS:
        own = [candidate for candidate in candidates if candidate["dimension"] == dimension]
        summary.append({
            "dimension": dimension, "evaluated": dimension in records,
            "candidates_considered": len(own),
            "materialized": sum(item["disposition"] == "MATERIALIZED" for item in own),
            "already_covered": sum(item["disposition"] == "ALREADY_COVERED" for item in own),
            "question_required": sum(item["disposition"] == "QUESTION_REQUIRED" for item in own),
            "not_applicable": sum(item["disposition"] == "NOT_APPLICABLE" for item in own),
        })
    return summary
