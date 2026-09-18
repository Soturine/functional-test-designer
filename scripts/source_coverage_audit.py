#!/usr/bin/env python3
"""Review source atomicity and audit claims against materialized coverage."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SOURCE_GAP_PREFIX = "[SOURCE_COVERAGE_GAP]"
ALLOWED_KEEP_ATOMIC_REASONS = {
    "INSEPARABLE_VALUE",
    "INSEPARABLE_RELATION",
    "SINGLE_OBSERVABLE_OUTCOME",
}
FORBIDDEN_KEEP_ATOMIC_REASONS = {
    "SAME_SENTENCE",
    "SAME_BULLET",
    "SAME_REQUIREMENT",
    "SAME_SCREEN",
    "SAME_EVENT",
    "FEWER_TESTS",
    "SIMPLER_OUTPUT",
}
COMPOUND_CONNECTOR = re.compile(r"(?:[,;]|\b(?:and|or|e|ou)\b)", re.IGNORECASE)
OBSERVABLE_VERB = re.compile(
    r"\b(?:show|display|search|filter|record|create|change|decrease|update|block|prevent|return|persist|"
    r"send|receive|release|complete|finali[sz]|reverse|cancel|alert|notify|generate|remove|"
    r"exibir|mostrar|buscar|pesquisar|filtrar|registrar|criar|alterar|reduzir|atualizar|bloquear|impedir|"
    r"retornar|persistir|enviar|receber|liberar|concluir|finalizar|reverter|cancelar|"
    r"alertar|notificar|gerar|remover)\w*\b",
    re.IGNORECASE,
)
DIMENSION_VERB = re.compile(r"\b(?:search|filter|buscar|pesquisar|filtrar)\w*\b", re.IGNORECASE)
BY_DIMENSIONS = re.compile(
    r"\b(?:by|por)\b[^.;:\n]*(?:,|\b(?:and|or|e|ou)\b)[^.;:\n]+",
    re.IGNORECASE,
)
REPEATED_TIME_LIMIT = re.compile(r"\b(?:within|em at[eé])\s+\d+", re.IGNORECASE)


def canonical_claim(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def claim_key(item: dict[str, Any], text_field: str) -> tuple[str, str]:
    return str(item.get("requirement_ref", "")), canonical_claim(item.get(text_field, ""))


def _unique_refs(refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for ref in refs:
        normalized = {"source": str(ref["source"]), "reference": str(ref["reference"])}
        if normalized not in result:
            result.append(normalized)
    return result


def compound_signals(text: str) -> list[str]:
    """Return conservative suspicion signals, never an automatic split decision."""
    signals: list[str] = []
    verbs = OBSERVABLE_VERB.findall(text)
    if len(verbs) >= 2 and COMPOUND_CONNECTOR.search(text):
        signals.append("MULTIPLE_OBSERVABLE_VERBS")
    if DIMENSION_VERB.search(text) and BY_DIMENSIONS.search(text):
        signals.append("MULTIPLE_SEARCH_OR_FILTER_DIMENSIONS")
    if len(REPEATED_TIME_LIMIT.findall(text)) >= 2:
        signals.append("MULTIPLE_TIME_LIMITS")
    if "/" in text and re.search(r"\b(?:pair|par)\b", text, re.IGNORECASE):
        signals.append("COMPOSITE_VALUE_PAIR")
    if (
        len(verbs) == 1
        and COMPOUND_CONNECTOR.search(text)
        and re.search(
            r"\b(?:show|display|record|create|generate|return|exibir|mostrar|registrar|criar|gerar|retornar)\w*\b",
            text,
            re.IGNORECASE,
        )
    ):
        signals.append("MULTIPLE_OBSERVABLE_OBJECTS")
    return list(dict.fromkeys(signals))


def review_source_items(source_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate explicit semantic reviews and materialize an independent claim inventory.

    Heuristics identify prose that requires attention. They never choose the split: the
    source reader must record SPLIT or KEEP_ATOMIC, and a suspicious KEEP_ATOMIC must
    use one of the narrow semantic reasons above.
    """
    claims: list[dict[str, Any]] = []
    split_items = 0
    suspicious_items = 0
    suspicious_split = 0
    suspicious_kept = 0
    for item in source_items:
        item_id = str(item.get("id", "")).strip()
        requirement_ref = str(item.get("requirement_ref", "")).strip()
        source_text = str(item.get("source_text", item.get("source_item", ""))).strip()
        source_refs = item.get("source_refs", [])
        review = item.get("atomicity_review")
        if not item_id or not requirement_ref or not source_text:
            raise ValueError("Every source item requires id, requirement_ref, and source_text")
        if not isinstance(source_refs, list) or not source_refs:
            raise ValueError(f"Source item {item_id} requires source_refs")
        if not isinstance(review, dict):
            raise ValueError(f"Source item {item_id} requires an explicit atomicity_review")

        decision = review.get("decision")
        parts = review.get("claims", [])
        signals = compound_signals(source_text)
        if signals:
            suspicious_items += 1
        if decision not in {"SPLIT", "KEEP_ATOMIC"}:
            raise ValueError(f"Source item {item_id} requires decision SPLIT or KEEP_ATOMIC")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Source item {item_id} requires at least one reviewed claim")
        if decision == "SPLIT" and len(parts) < 2:
            raise ValueError(f"Source item {item_id} uses SPLIT but materializes fewer than two claims")
        if decision == "KEEP_ATOMIC" and len(parts) != 1:
            raise ValueError(f"Source item {item_id} uses KEEP_ATOMIC but does not materialize exactly one claim")
        reason = review.get("reason")
        if decision == "KEEP_ATOMIC":
            if reason in FORBIDDEN_KEEP_ATOMIC_REASONS:
                raise ValueError(f"Source item {item_id} uses forbidden KEEP_ATOMIC reason {reason}")
            if reason not in ALLOWED_KEEP_ATOMIC_REASONS:
                raise ValueError(f"Source item {item_id} requires a valid KEEP_ATOMIC reason")
            if signals:
                suspicious_kept += 1
        else:
            split_items += 1
            if signals:
                suspicious_split += 1
        for part in parts:
            if not isinstance(part, dict) or not part.get("normalized_claim"):
                raise ValueError(f"Every atomic claim in {item_id} requires normalized_claim")
            residual_signals = compound_signals(str(part["normalized_claim"]))
            if residual_signals and decision == "SPLIT":
                residual_reason = part.get("keep_atomic_reason")
                if residual_reason not in ALLOWED_KEEP_ATOMIC_REASONS:
                    raise ValueError(
                        f"Atomic claim in {item_id} remains compound after SPLIT; "
                        "split it again or record a valid keep_atomic_reason"
                    )
            claim = dict(part)
            claim["id"] = f"CLAIM-{len(claims) + 1:03d}"
            claim["source_item_ref"] = item_id
            claim["requirement_ref"] = str(part.get("requirement_ref", requirement_ref))
            claim["authority"] = str(part.get("authority", item.get("authority", "FUNCTIONAL_AUTHORITY")))
            claim["source_refs"] = _unique_refs(part.get("source_refs", source_refs))
            claim["semantic_key"] = str(
                part.get("semantic_key", canonical_claim(part["normalized_claim"]))
            )
            claims.append(claim)
    return {
        "source_items": len(source_items),
        "atomic_source_claims_identified": len(claims),
        "compound_source_items_split": split_items,
        "compound_claims_reviewed": suspicious_items,
        "compound_claims_split": suspicious_split,
        "compound_claims_kept_atomic": suspicious_kept,
        "possible_compound_claim_warnings": 0,
        "claims": claims,
    }


def atomic_claim_inventory(source_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve legacy pre-materialized fixtures; new pipelines use review_source_items."""
    if all("atomic_claims" in item and "atomicity_review" not in item for item in source_items):
        claims: list[dict[str, Any]] = []
        split_items = 0
        for item in source_items:
            parts = item.get("atomic_claims", [])
            if not isinstance(parts, list) or not parts:
                raise ValueError("Every source item requires at least one materialized atomic_claim")
            split_items += len(parts) > 1
            for part in parts:
                if not isinstance(part, dict) or not part.get("normalized_claim"):
                    raise ValueError("Every atomic claim requires normalized_claim")
                claims.append(part)
        return {
            "source_items": len(source_items),
            "atomic_source_claims_identified": len(claims),
            "compound_source_items_split": split_items,
            "claims": claims,
        }
    return review_source_items(source_items)


def materialize_atomic_coverage(inventory: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate equivalent claims and materialize one Clause and CP per behavior."""
    claims = inventory.get("claims", [])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for claim in claims:
        requirement_ref = str(claim.get("requirement_ref", ""))
        semantic_key = canonical_claim(claim.get("semantic_key", ""))
        if not requirement_ref or not semantic_key:
            raise ValueError("Every reviewed claim requires requirement_ref and semantic_key")
        if claim.get("authority") != "FUNCTIONAL_AUTHORITY":
            raise ValueError("Only FUNCTIONAL_AUTHORITY claims can materialize normative coverage")
        groups.setdefault((requirement_ref, semantic_key), []).append(claim)

    clauses: list[dict[str, Any]] = []
    coverage_points: list[dict[str, Any]] = []
    claim_destinations: dict[str, str] = {}
    for number, ((requirement_ref, _), equivalent) in enumerate(groups.items(), 1):
        clause_id = f"CLAUSE-{number:03d}"
        refs = _unique_refs([ref for claim in equivalent for ref in claim["source_refs"]])
        normalized_claim = str(equivalent[0]["normalized_claim"])
        destination_types = {
            str(claim.get("destination_type", "COVERAGE_POINT")) for claim in equivalent
        }
        if len(destination_types) != 1:
            raise ValueError("Equivalent claims disagree on destination_type")
        destination_type = destination_types.pop()
        if destination_type not in {
            "COVERAGE_POINT", "QUESTION", "OUT_OF_SCOPE", "NOT_TESTABLE", "FINDING"
        }:
            raise ValueError(f"Unsupported atomic claim destination_type {destination_type}")
        cp_id = f"CP-{len(coverage_points) + 1:03d}"
        destination_id = cp_id if destination_type == "COVERAGE_POINT" else equivalent[0].get("destination_id")
        clause = {
            "id": clause_id,
            "requirement_ref": requirement_ref,
            "normalized_claim": normalized_claim,
            "authority": "FUNCTIONAL_AUTHORITY",
            "source_refs": refs,
            "destination_type": destination_type,
            "destination_id": destination_id,
        }
        reason = equivalent[0].get("reason")
        if reason:
            clause["reason"] = str(reason)
        clauses.append(clause)
        if destination_type == "COVERAGE_POINT":
            coverage_points.append(
                {
                    "id": cp_id,
                    "requirement_ref": requirement_ref,
                    "statement": str(equivalent[0].get("coverage_statement", normalized_claim)),
                    "clause_refs": [clause_id],
                    "source_refs": refs,
                    "disposition": str(equivalent[0].get("disposition", "TEST_CASE")),
                    "target_refs": list(equivalent[0].get("target_refs", [])),
                }
            )
        for claim in equivalent:
            claim_destinations[str(claim["id"])] = clause_id

    return {
        "normative_clauses": clauses,
        "coverage_points": coverage_points,
        "claim_destinations": claim_destinations,
        "metrics": {
            "source_claims_identified": len(claims),
            "source_claims_represented": len(claim_destinations),
            "atomic_claims_deduplicated": len(claims) - len(clauses),
            "normative_clauses_extracted": len(clauses),
            "coverage_points": len(coverage_points),
        },
    }


def audit_atomic_chain(inventory: dict[str, Any], chain: dict[str, Any]) -> dict[str, int]:
    """Gate claim -> Clause -> CP lineage without deriving claims from downstream output."""
    claims = inventory.get("claims", [])
    clauses = chain.get("normative_clauses", [])
    points = chain.get("coverage_points", [])
    destinations = chain.get("claim_destinations", {})
    clause_ids = {item.get("id") for item in clauses}
    point_by_id = {item.get("id"): item for item in points}
    missing_claims = [claim["id"] for claim in claims if destinations.get(claim["id"]) not in clause_ids]
    invalid_clauses = []
    for clause in clauses:
        destination_type = clause.get("destination_type")
        destination_id = clause.get("destination_id")
        if destination_type == "COVERAGE_POINT":
            valid = (
                destination_id in point_by_id
                and clause["id"] in point_by_id[destination_id].get("clause_refs", [])
            )
        elif destination_type in {"QUESTION", "FINDING"}:
            valid = isinstance(destination_id, str) and bool(destination_id)
        elif destination_type in {"OUT_OF_SCOPE", "NOT_TESTABLE"}:
            valid = bool(clause.get("reason"))
        else:
            valid = False
        if not valid:
            invalid_clauses.append(clause["id"])
    if missing_claims:
        raise ValueError("Atomic claims disappeared before Clause materialization: " + ", ".join(missing_claims))
    if invalid_clauses:
        raise ValueError("Clauses disappeared before atomic Coverage Points: " + ", ".join(invalid_clauses))
    return {
        "source_claims_identified": len(claims),
        "source_claims_represented": len(claims),
        "source_coverage_gaps": 0,
        "normative_clauses_mapped": len(clauses),
        "unmapped_normative_clauses": 0,
    }


def possible_compound_claims(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Flag suspicious materialized claims for review; never split them automatically."""
    warnings: list[dict[str, str]] = []
    for item in items:
        text = str(item.get("normalized_claim", item.get("statement", "")))
        signals = compound_signals(text)
        if signals:
            warnings.append(
                {
                    "id": str(item.get("id", "")),
                    "code": "POSSIBLE_COMPOUND_NORMATIVE_CLAIM",
                    "statement": text,
                    "signals": ",".join(signals),
                }
            )
    return warnings


def audit_source_claims(
    source_claims: list[dict[str, Any]],
    normative_clauses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare a fresh source-first claim inventory with clauses without interpreting raw files."""
    clause_keys = {claim_key(clause, "normalized_claim") for clause in normative_clauses}
    seen_claims: set[tuple[str, str]] = set()
    represented: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for claim in source_claims:
        key = claim_key(claim, "normalized_claim")
        if not key[0] or not key[1]:
            raise ValueError("Every source claim requires requirement_ref and normalized_claim")
        if key in seen_claims:
            duplicates.append(claim)
            continue
        seen_claims.add(key)
        (represented if key in clause_keys else gaps).append(claim)
    return {
        "source_claims_identified": len(seen_claims),
        "source_claims_represented": len(represented),
        "source_coverage_gaps": len(gaps),
        "represented_claims": represented,
        "gap_claims": gaps,
        "duplicate_source_claims": duplicates,
    }


def recovery_candidates(
    audit: dict[str, Any],
    normative_clauses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only genuinely absent claims for one bounded recovery pass."""
    existing = {claim_key(clause, "normalized_claim") for clause in normative_clauses}
    candidates: list[dict[str, Any]] = []
    for claim in audit.get("gap_claims", []):
        key = claim_key(claim, "normalized_claim")
        if key not in existing:
            existing.add(key)
            candidates.append(claim)
    return candidates


def unresolved_source_gap_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("type") == "COVERAGE_GAP"
        and str(finding.get("statement", "")).startswith(SOURCE_GAP_PREFIX)
    ]


def per_requirement_summary(
    index: dict[str, Any],
    questions: list[dict[str, Any]] | None = None,
    source_inventory: dict[str, Any] | None = None,
    claim_destinations: dict[str, str] | None = None,
) -> dict[str, dict[str, int]]:
    """Summarize coverage, preferring an independent source-first inventory when supplied.

    Contract-only callers retain the legacy Clause-plus-gap fallback for presentation. That
    fallback is not proof of source atomicity and must not be used as the generation gate.
    """
    clauses = index.get("normative_clauses", [])
    coverage = index.get("coverage_points", [])
    scenarios = index.get("scenarios", [])
    cases = index.get("test_cases", [])
    findings = index.get("findings", [])
    gaps = unresolved_source_gap_findings(findings)
    questions = questions or []
    inventory_claims = (source_inventory or {}).get("claims", [])
    destinations = claim_destinations or {}
    summaries: dict[str, dict[str, int]] = {}
    for requirement in index.get("requirements", []):
        req_id = requirement["id"]
        req_clauses = [item for item in clauses if item.get("requirement_ref") == req_id]
        req_gaps = [item for item in gaps if req_id in item.get("requirement_refs", [])]
        req_claims = [item for item in inventory_claims if item.get("requirement_ref") == req_id]
        if source_inventory is not None:
            identified = len(req_claims)
            represented = sum(str(item.get("id")) in destinations for item in req_claims)
        else:
            identified = len(req_clauses) + len(req_gaps)
            represented = len(req_clauses)
        summaries[req_id] = {
            "source_claims_identified": identified,
            "source_claims_represented": represented,
            "mapped_clauses": sum(bool(item.get("destination_type")) for item in req_clauses),
            "coverage_points": sum(item.get("requirement_ref") == req_id for item in coverage),
            "scenarios": sum(req_id in item.get("requirement_refs", []) for item in scenarios),
            "test_cases": sum(req_id in item.get("requirement_refs", []) for item in cases),
            "questions": sum(req_id in item.get("requirement_refs", []) for item in questions),
            "findings": sum(req_id in item.get("requirement_refs", []) for item in findings),
            "source_coverage_gaps": len(req_gaps),
        }
    return summaries
