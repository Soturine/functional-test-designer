#!/usr/bin/env python3
"""Resolve explicitly declared normative relationships inside an in-scope catalog."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from source_coverage_audit import canonical_claim


REFERENCE_PATTERN = re.compile(r"^(?:RF|RN|CU)[-_ ]?\d+$", re.IGNORECASE)


def canonical_reference(value: Any) -> str:
    return re.sub(r"[-_ ]", "", str(value)).upper()


def resolve_applicable_rules(
    owner_ref: str,
    referenced_refs: list[str],
    in_scope_catalog: dict[str, dict[str, Any]],
    owner_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve only explicit references already present in the selected-source catalog."""
    catalog = {canonical_reference(key): value for key, value in in_scope_catalog.items()}
    resolved: list[str] = []
    unresolved: list[str] = []
    claims: list[dict[str, Any]] = []
    seen_claims: dict[str, dict[str, Any]] = {}
    combined_claims: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for claim in owner_claims or []:
        normalized = canonical_claim(claim.get("normalized_claim", ""))
        if not normalized:
            raise ValueError(f"Owner {owner_ref} contains an empty claim")
        semantic_key = str(claim.get("semantic_key", normalized))
        materialized = dict(claim)
        materialized["source_ref"] = owner_ref
        seen_claims[semantic_key] = materialized
        combined_claims.append(materialized)

    for raw_reference in referenced_refs:
        reference = canonical_reference(raw_reference)
        if not REFERENCE_PATTERN.fullmatch(reference):
            raise ValueError(f"Unsupported explicit normative reference: {raw_reference!r}")
        item = catalog.get(reference)
        if item is None:
            unresolved.append(reference)
            continue
        resolved.append(reference)
        for claim in item.get("claims", []):
            normalized = canonical_claim(claim.get("normalized_claim", ""))
            if not normalized:
                raise ValueError(f"Applicable rule {reference} contains an empty claim")
            semantic_key = str(claim.get("semantic_key", normalized))
            existing = seen_claims.get(semantic_key)
            if existing:
                if (
                    claim.get("polarity")
                    and existing.get("polarity")
                    and existing.get("polarity") != claim.get("polarity")
                ):
                    conflicts.append(
                        {
                            "type": "SOURCE_CONFLICT",
                            "owner_ref": owner_ref,
                            "references": [existing["source_ref"], reference],
                            "semantic_key": semantic_key,
                        }
                    )
                    materialized = dict(claim)
                    materialized["source_ref"] = reference
                    claims.append(materialized)
                    combined_claims.append(materialized)
                else:
                    existing.setdefault("source_refs", [existing["source_ref"]]).append(reference)
                continue
            materialized = dict(claim)
            materialized["source_ref"] = reference
            seen_claims[semantic_key] = materialized
            claims.append(materialized)
            combined_claims.append(materialized)

    return {
        "owner_ref": owner_ref,
        "referenced_normative_rules": len(dict.fromkeys(map(canonical_reference, referenced_refs))),
        "referenced_rules_resolved_in_scope": len(dict.fromkeys(resolved)),
        "referenced_rules_unresolved": len(dict.fromkeys(unresolved)),
        "resolved_refs": list(dict.fromkeys(resolved)),
        "unresolved_refs": list(dict.fromkeys(unresolved)),
        "applicable_rule_claims": claims,
        "combined_claims": combined_claims,
        "conflicts": conflicts,
    }
