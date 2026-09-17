#!/usr/bin/env python3
"""Audit independently identified normative source claims against materialized clauses."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SOURCE_GAP_PREFIX = "[SOURCE_COVERAGE_GAP]"


def canonical_claim(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def claim_key(item: dict[str, Any], text_field: str) -> tuple[str, str]:
    return str(item.get("requirement_ref", "")), canonical_claim(item.get(text_field, ""))


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
    index: dict[str, Any], questions: list[dict[str, Any]] | None = None
) -> dict[str, dict[str, int]]:
    """Derive current source/coverage counts from contract data and explicit unresolved gaps."""
    clauses = index.get("normative_clauses", [])
    coverage = index.get("coverage_points", [])
    scenarios = index.get("scenarios", [])
    cases = index.get("test_cases", [])
    findings = index.get("findings", [])
    gaps = unresolved_source_gap_findings(findings)
    questions = questions or []
    summaries: dict[str, dict[str, int]] = {}
    for requirement in index.get("requirements", []):
        req_id = requirement["id"]
        req_clauses = [item for item in clauses if item.get("requirement_ref") == req_id]
        req_gaps = [item for item in gaps if req_id in item.get("requirement_refs", [])]
        summaries[req_id] = {
            "source_claims_identified": len(req_clauses) + len(req_gaps),
            "source_claims_represented": len(req_clauses),
            "mapped_clauses": sum(bool(item.get("destination_type")) for item in req_clauses),
            "coverage_points": sum(item.get("requirement_ref") == req_id for item in coverage),
            "scenarios": sum(req_id in item.get("requirement_refs", []) for item in scenarios),
            "test_cases": sum(req_id in item.get("requirement_refs", []) for item in cases),
            "questions": sum(req_id in item.get("requirement_refs", []) for item in questions),
            "findings": sum(req_id in item.get("requirement_refs", []) for item in findings),
            "source_coverage_gaps": len(req_gaps),
        }
    return summaries
