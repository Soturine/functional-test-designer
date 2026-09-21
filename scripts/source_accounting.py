#!/usr/bin/env python3
"""Account for every selected source and keep the source-first review independent.

Mapping every structured input the orchestrator receives only proves input
consistency. These gates ask the separate question of whether the selected
sources themselves were explored completely, and they refuse to answer it with
fabricated telemetry or with a reformatted copy of the primary extraction.
"""

from __future__ import annotations

from typing import Any


INSPECTION_DISPOSITIONS = {
    "INSPECTED_CONTENT",
    "METADATA_ONLY",
    "IRRELEVANT_WITH_REASON",
    "DUPLICATE_EQUIVALENT_SOURCE",
    "UNSUPPORTED_BINARY",
    "FAILED_TO_READ",
}
REASON_REQUIRED_DISPOSITIONS = INSPECTION_DISPOSITIONS - {"INSPECTED_CONTENT"}
INDEPENDENT_REVIEW_METHODS = {"SUBAGENT_INDEPENDENT", "BOUNDED_SECOND_READING"}
REQUIRED_ANCHORING_WITHHELD = {
    "final_scenario_count",
    "final_test_case_count",
    "desired_suite_size",
}
COUNTED_LEDGER_FIELDS = (
    "evidence_records",
    "source_behaviors",
    "test_asset_behaviors",
    "opportunities",
    "divergences",
)


class SourceAccountingError(ValueError):
    """Raised when selected-source exploration cannot be shown to be complete."""


def build_source_ledger(
    resolved_scope_paths: list[str],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Give every resolved selected source exactly one explicit inspection disposition.

    Accounting for a source is not the same as opening it: a binary or duplicate may
    legitimately stay unread, but only with a recorded reason. Nothing may vanish.
    """
    expected = list(dict.fromkeys(str(value) for value in resolved_scope_paths))
    expected_set = set(expected)
    seen: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for entry in entries:
        source = str(entry.get("source", "")).strip()
        if not source:
            raise SourceAccountingError("Every source ledger entry requires a source path")
        if source not in expected_set:
            raise SourceAccountingError(
                f"Source ledger entry {source} is outside the resolved selected scope"
            )
        if source in seen:
            raise SourceAccountingError(f"Source {source} has more than one inspection disposition")
        disposition = str(entry.get("disposition", ""))
        if disposition not in INSPECTION_DISPOSITIONS:
            raise SourceAccountingError(
                f"Source {source} requires a supported inspection disposition"
            )
        reason = str(entry.get("reason", "")).strip()
        if disposition in REASON_REQUIRED_DISPOSITIONS and not reason:
            raise SourceAccountingError(
                f"Source {source} is not content-inspected and requires a reason"
            )
        if not str(entry.get("inspection_method", "")).strip():
            raise SourceAccountingError(f"Source {source} requires an inspection_method")
        record = {
            "source": source,
            "source_role": str(entry.get("source_role", "")),
            "content_type": str(entry.get("content_type", "")),
            "disposition": disposition,
            "inspection_method": str(entry["inspection_method"]),
            "content_read": disposition == "INSPECTED_CONTENT",
            "reason": reason,
        }
        for field in COUNTED_LEDGER_FIELDS:
            record[field] = int(entry.get(field, 0) or 0)
        rereads = entry.get("rereads")
        record["rereads"] = None if rereads is None else int(rereads)
        seen[source] = record
        records.append(record)

    unaccounted = [value for value in expected if value not in seen]
    if unaccounted:
        raise SourceAccountingError(
            "Resolved selected sources have no inspection disposition: " + ", ".join(unaccounted)
        )

    by_disposition = {value: 0 for value in sorted(INSPECTION_DISPOSITIONS)}
    for record in records:
        by_disposition[record["disposition"]] += 1
    metrics = {
        "resolved_selected_sources": len(expected),
        "sources_inspected_content": by_disposition["INSPECTED_CONTENT"],
        "sources_metadata_only": by_disposition["METADATA_ONLY"],
        "sources_irrelevant_with_reason": by_disposition["IRRELEVANT_WITH_REASON"],
        "sources_duplicate_equivalent": by_disposition["DUPLICATE_EQUIVALENT_SOURCE"],
        "sources_unsupported_binary": by_disposition["UNSUPPORTED_BINARY"],
        "sources_failed": by_disposition["FAILED_TO_READ"],
        "sources_unaccounted": 0,
    }
    for field in COUNTED_LEDGER_FIELDS:
        metrics[f"ledger_{field}"] = sum(record[field] for record in records)
    return {
        "entries": sorted(records, key=lambda record: record["source"]),
        "dispositions": by_disposition,
        "metrics": metrics,
    }


def read_telemetry(request: dict[str, Any]) -> dict[str, Any]:
    """Report observed read/concurrency metrics, or mark them explicitly unavailable.

    A fabricated zero is worse than a null: it claims the selected sources were never
    opened when the agent in fact inspected them before invoking the shared core.
    """
    observed = request.get("source_read_telemetry")
    if not isinstance(observed, dict):
        return {
            "source_read_telemetry_available": False,
            "source_reads": None,
            "source_rereads": None,
            "source_max_concurrency": None,
            "source_workers": None,
            "agent_reasoning_seconds": None,
        }

    def value(name: str) -> Any:
        raw = observed.get(name)
        return None if raw is None else int(raw)

    return {
        "source_read_telemetry_available": True,
        "source_reads": value("source_reads"),
        "source_rereads": value("source_rereads"),
        "source_max_concurrency": value("max_concurrency"),
        "source_workers": value("workers"),
        "agent_reasoning_seconds": observed.get("agent_reasoning_seconds"),
    }


def audit_source_review_independence(
    review: dict[str, Any],
    *,
    primary_claim_count: int,
) -> dict[str, Any]:
    """Prove the source-first inventory is a second reading, not a reformatted copy.

    Structural units are inventoried before semantic normalization, so a requirement
    heading with N acceptance bullets cannot collapse into one behavior unless each
    orphaned unit carries an explicit reason.
    """
    if not isinstance(review, dict):
        raise SourceAccountingError("An independent source review is required")
    method = str(review.get("method", ""))
    if method not in INDEPENDENT_REVIEW_METHODS:
        raise SourceAccountingError(
            f"Unsupported source-first review method {method or '<missing>'}"
        )
    withheld = {str(value) for value in review.get("anchoring_inputs_withheld", [])}
    missing_withheld = sorted(REQUIRED_ANCHORING_WITHHELD - withheld)
    if missing_withheld:
        raise SourceAccountingError(
            "Source-first review saw anchoring inputs: " + ", ".join(missing_withheld)
        )

    units = review.get("structural_units", [])
    if not isinstance(units, list) or not units:
        raise SourceAccountingError("Source-first review requires a structural source inventory")
    unit_ids: list[str] = []
    for unit in units:
        unit_id = str(unit.get("id", "")).strip()
        if not unit_id:
            raise SourceAccountingError("Every structural unit requires an id")
        if unit_id in unit_ids:
            raise SourceAccountingError(f"Structural unit {unit_id} is inventoried twice")
        if not str(unit.get("kind", "")).strip():
            raise SourceAccountingError(f"Structural unit {unit_id} requires a kind")
        unit_ids.append(unit_id)

    behaviors = review.get("behaviors", [])
    if not isinstance(behaviors, list) or not behaviors:
        raise SourceAccountingError("Source-first review requires its own behavior inventory")
    claims: list[dict[str, Any]] = []
    covered: set[str] = set()
    for behavior in behaviors:
        if behavior.get("derived_from_claim_id"):
            raise SourceAccountingError(
                "Source-first behaviors cannot be derived from the primary extracted claims"
            )
        requirement_ref = str(behavior.get("requirement_ref", "")).strip()
        normalized_claim = str(behavior.get("normalized_claim", "")).strip()
        unit_ref = str(behavior.get("structural_unit_ref", "")).strip()
        if not requirement_ref or not normalized_claim:
            raise SourceAccountingError(
                "Every source-first behavior requires requirement_ref and normalized_claim"
            )
        if unit_ref not in unit_ids:
            raise SourceAccountingError(
                f"Source-first behavior references unknown structural unit {unit_ref or '<missing>'}"
            )
        covered.add(unit_ref)
        claims.append({
            "requirement_ref": requirement_ref,
            "normalized_claim": normalized_claim,
            "structural_unit_ref": unit_ref,
        })

    orphans = []
    for unit in units:
        unit_id = str(unit["id"])
        if unit_id in covered:
            continue
        if not str(unit.get("no_behavior_reason", "")).strip():
            orphans.append(unit_id)
    if orphans:
        raise SourceAccountingError(
            "Structural units lost their child behaviors without a reason: " + ", ".join(orphans)
        )

    return {
        "independent_review_method": method,
        "independent_review_source_behaviors": len(claims),
        "structural_units_inventoried": len(unit_ids),
        "structural_units_without_behavior": len(unit_ids) - len(covered),
        "primary_atomic_claims": int(primary_claim_count),
        "source_first_claims": claims,
    }
