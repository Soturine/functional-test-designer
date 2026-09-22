#!/usr/bin/env python3
"""Benchmark-only tooling. Nothing here affects normal generation.

- historical baseline comparison (PRESERVED / ADDED / REMOVED_WITH_REASON /
  UNEXPLAINED_REGRESSION; NOT_APPLIED when no baseline is loaded);
- Finding reconciliation for unchanged corpora;
- reconciliation of an external (e.g. manual) suite against the generated one;
- synthetic multi-domain packs driven through the official pipeline.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import jaccard, normalize_identifier, read_json, similarity  # noqa: E402


PACK_DIR = SCRIPT_DIR.parent / "benchmarks" / "domains"
FINDING_STATUSES = {
    "STILL_PRESENT", "RESOLVED_BY_CODE_CHANGE", "FALSE_POSITIVE_PROVEN", "SUPERSEDED",
    "UNEXPLAINED_MISSING",
}
MANUAL_DISPOSITIONS = {
    "COVERED", "SPLIT_INTO_MULTIPLE", "SUPERSEDED_BY_STRONGER_TEST", "QUESTION",
    "INVALID_AGAINST_CURRENT_AUTHORITY", "OUT_OF_SCOPE", "GAP",
}


def baseline_status(baseline: dict[str, Any] | None) -> str:
    """A baseline that was not loaded is NOT_APPLIED, never PASS."""
    return "APPLIED" if baseline else "NOT_APPLIED"


def _identifiers(values: Any) -> set[str]:
    return {normalize_identifier(value) for value in values or []}


def compare_with_baseline(canonical: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    cases = canonical["cases"]
    index = canonical["index"]
    diagnostics = canonical.get("diagnostics", {})
    reconciled = {
        (item.get("kind"), item.get("key")): item for item in baseline.get("reconciliations", [])
        if item.get("status") == "REMOVED_WITH_REASON" and str(item.get("reason", "")).strip()
    }
    items: list[dict[str, Any]] = []

    def settle(kind: str, key: str, matched: list[str]) -> None:
        if matched:
            status = "PRESERVED"
        elif (kind, key) in reconciled:
            status = "REMOVED_WITH_REASON"
        else:
            status = "UNEXPLAINED_REGRESSION"
        items.append({"kind": kind, "key": key, "status": status, "matched": matched})

    acceptance = [case for case in cases if case.get("test_basis") == "ACCEPTANCE"]
    used: set[str] = set()
    for intent in baseline.get("normative_intents", []):
        wanted = _identifiers(intent.get("identifiers"))
        matched = [
            case["id"] for case in acceptance
            if (not wanted or wanted & _identifiers(case.get("source_identifiers")))
            and jaccard(intent.get("text"), f"{case['title']} {case.get('failure_domain', '')}") >= 0.3
        ]
        used.update(matched)
        settle("NORMATIVE_INTENT", str(intent.get("key")), matched)
    for finding in baseline.get("findings", []):
        matched = [
            item["id"] for item in index.get("findings", [])
            if similarity(finding.get("statement"), item["statement"]) >= 0.6
        ]
        settle("FINDING", str(finding.get("key")), matched)
    challenge = {item["asset"]: item for item in diagnostics.get("test_asset_challenge", [])}
    for asset in baseline.get("challenge", []):
        current = challenge.get(str(asset.get("asset")))
        settle("CHALLENGE", str(asset.get("asset")), [current["disposition"]] if current else [])
    families = [item["title"] for item in index.get("scenarios", [])]
    for family in baseline.get("families", []):
        matched = [title for title in families if similarity(family.get("title"), title) >= 0.5]
        settle("FAMILY", str(family.get("key") or family.get("title")), matched)
    added = [case["id"] for case in acceptance if case["id"] not in used] if baseline.get("normative_intents") else []
    for case_id in added:
        items.append({"kind": "NORMATIVE_INTENT", "key": case_id, "status": "ADDED", "matched": [case_id]})
    counts = {status: sum(item["status"] == status for item in items) for status in (
        "PRESERVED", "ADDED", "REMOVED_WITH_REASON", "UNEXPLAINED_REGRESSION",
    )}
    return {"status": "APPLIED", "corpus": baseline.get("corpus"), "counts": counts, "items": items}


def reconcile_findings(
    previous: list[dict[str, Any]], current: list[dict[str, Any]], reconciliations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Previously confirmed Findings may not silently disappear from an unchanged corpus."""
    explained = {str(item.get("key")): item for item in reconciliations}
    results = []
    for finding in previous:
        key = str(finding.get("key"))
        present = any(similarity(finding.get("statement"), item.get("statement")) >= 0.6 for item in current)
        if present:
            status = "STILL_PRESENT"
        else:
            record = explained.get(key, {})
            status = str(record.get("status", "UNEXPLAINED_MISSING"))
            if status not in FINDING_STATUSES or status == "STILL_PRESENT" or (
                status != "UNEXPLAINED_MISSING" and not str(record.get("reason", "")).strip()
            ):
                status = "UNEXPLAINED_MISSING"
        results.append({"key": key, "status": status})
    return {
        "findings": results,
        "counts": {status: sum(item["status"] == status for item in results) for status in sorted(FINDING_STATUSES)},
    }


def reconcile_manual_suite(
    items: list[dict[str, Any]], reconciliations: list[dict[str, Any]], *,
    test_case_ids: set[str], question_ids: set[str],
) -> dict[str, Any]:
    """Explain each external suite idea without using its size as a target."""
    by_item: dict[str, dict[str, Any]] = {}
    for record in reconciliations:
        key = str(record.get("item", ""))
        if not key or key in by_item:
            raise ValueError("every external suite item requires exactly one reconciliation")
        disposition = str(record.get("disposition", ""))
        if disposition not in MANUAL_DISPOSITIONS:
            raise ValueError(f"item {key} has unsupported disposition {disposition}")
        targets = set(map(str, record.get("targets", [])))
        if disposition in {"COVERED", "SPLIT_INTO_MULTIPLE", "SUPERSEDED_BY_STRONGER_TEST"}:
            if not targets or not targets <= test_case_ids:
                raise ValueError(f"item {key} does not link valid Test Cases")
            if disposition == "SPLIT_INTO_MULTIPLE" and len(targets) < 2:
                raise ValueError(f"item {key} SPLIT_INTO_MULTIPLE links fewer than two Test Cases")
        if disposition == "QUESTION" and (not targets or not targets <= question_ids):
            raise ValueError(f"item {key} does not link valid Questions")
        if disposition in {"INVALID_AGAINST_CURRENT_AUTHORITY", "OUT_OF_SCOPE", "GAP"} and not str(record.get("reason", "")).strip():
            raise ValueError(f"item {key} requires a reason")
        by_item[key] = record
    expected = {str(item.get("id")) for item in items}
    missing, extra = sorted(expected - set(by_item)), sorted(set(by_item) - expected)
    if missing or extra:
        raise ValueError(f"reconciliation mismatch: missing={missing} extra={extra}")
    counts = {value: sum(r["disposition"] == value for r in reconciliations) for value in sorted(MANUAL_DISPOSITIONS)}
    return {"items": len(items), "counts": counts, "target_count_used_as_goal": False}


# --- synthetic multi-domain packs ----------------------------------------------------

def available_packs() -> list[Path]:
    return sorted(PACK_DIR.glob("*.json"))


def run_pack(pack: dict[str, Any], root: Path, formats: tuple[str, ...] = ("HTML", "JSON", "MARKDOWN")) -> dict[str, Any]:
    """Drive a synthetic pack through the official pipeline exactly like a model would."""
    import pipeline
    workspace = root / "workspace"
    for relative, source in pack["sources"].items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source["text"], encoding="utf-8")
    selected = [{"path": relative, "role": source["role"]} for relative, source in pack["sources"].items()]
    started = pipeline.start_run(
        workspace=workspace, sources_selected=selected, artifact_root=root / "artifacts",
        run_id=pack["name"], locale=pack.get("locale"), request_text=pack.get("request", ""),
    )
    run_dir = Path(started["run_dir"])
    for stage in ("design", "expansion", "procedures"):
        pipeline.submit_stage(run_dir, stage, pack["stages"][stage])
    return pipeline.finalize_run(run_dir, list(formats))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    metrics = commands.add_parser("metrics", help="print suite metrics from a canonical state")
    metrics.add_argument("--canonical", required=True, type=Path)
    compare = commands.add_parser("compare", help="compare a canonical state with a historical baseline")
    compare.add_argument("--canonical", required=True, type=Path)
    compare.add_argument("--baseline", type=Path)
    commands.add_parser("packs", help="run every synthetic multi-domain pack")
    args = parser.parse_args()
    if args.command == "metrics":
        import validation
        canonical = read_json(args.canonical)
        result = validation.suite_metrics(canonical["index"], canonical["cases"], canonical["questions"]["questions"])
    elif args.command == "compare":
        canonical = read_json(args.canonical)
        baseline = read_json(args.baseline) if args.baseline else None
        result = compare_with_baseline(canonical, baseline) if baseline else {"status": baseline_status(None)}
    else:
        result = {}
        for path in available_packs():
            pack = read_json(path)
            directory = Path(tempfile.mkdtemp(prefix=f"ftd-{pack['name']}-"))
            try:
                outcome = run_pack(pack, directory)
                result[pack["name"]] = {"test_cases": outcome["metrics"]["test_cases"], "status": "PASS"}
            except Exception as exc:  # report every pack, then fail
                result[pack["name"]] = {"status": "FAIL", "error": str(exc)[:500]}
            finally:
                shutil.rmtree(directory, ignore_errors=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all(item.get("status", "PASS") != "FAIL" for item in (result.values() if args.command == "packs" else [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
