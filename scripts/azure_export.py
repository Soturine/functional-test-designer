#!/usr/bin/env python3
"""ftd-azure: FTD-run aggregation for a normalized Azure DevOps Test Plans input,
organized requirement by requirement. Local and deterministic: it never contacts Azure.

This module owns only the FTD side: selecting a canonical run and its finalized chaos
runs (/ftd-chaos; stored internally under `challenges/<id>`), minting stable scoped
export keys, normalizing canonical/chaos cases into common export records, and
building requirement -> case relationships. Every Azure-specific concern — payload
mapping, Suite placement, create/update/unchanged/conflict diffing, external ids,
content hashes, integration state and transport/publish — stays owned by
`integrations/azure_devops.py`; this module calls into it rather than reimplementing it.

A chaos case (`CH-017`) never becomes `TC-244`: locally it stays a chaos identity
forever. Only its Azure *export key* — `chaos:<chaos_run_id>:CH-017` — identifies it as
a Test Case work item, so two chaos runs that both mint `CH-001` never collide. Keys
written by earlier versions as `challenge:<id>:CH-017` are migrated deterministically.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import normalize_identifier, read_json, write_json
import pipeline
from integrations.azure_devops import (
    build_group_suite_mapping, build_preview, load_integration_state, persist_integration_state,
    write_fallback_export,
)

UNASSIGNED = "Unassigned"
SCHEMA_VERSION = "2"
LEGACY_CHAOS_PREFIX = "challenge:"


def canonical_export_key(local_id: str) -> str:
    return f"canonical:{local_id}"


def chaos_export_key(chaos_run_id: str, local_id: str) -> str:
    return f"chaos:{chaos_run_id}:{local_id}"


def migrate_export_key(key: str) -> str:
    """`challenge:<id>:CH-001` (pre-ftd-chaos) -> `chaos:<id>:CH-001`; other keys unchanged."""
    return "chaos:" + key[len(LEGACY_CHAOS_PREFIX):] if key.startswith(LEGACY_CHAOS_PREFIX) else key


def migrate_integration_state(state: dict[str, Any]) -> dict[str, Any]:
    """Integration state keyed by legacy export keys, re-keyed without losing external ids."""
    entries = state.get("test_cases", {})
    return {**state, "test_cases": {migrate_export_key(key): value for key, value in entries.items()}}


def state_contract(cleanup: list[str]) -> str:
    """How an executor restores state after the case: the case's own cleanup steps, or a
    harness that resets the fixtures it declares in test_data before the next case."""
    return "SELF_CLEANING" if cleanup else "REQUIRES_FIXTURE_RESET"


def _export_canonical_case(case: dict[str, Any]) -> dict[str, Any]:
    cleanup = list(case.get("cleanup", []))
    return {
        "export_key": canonical_export_key(case["id"]), "local_id": case["id"], "source_kind": "CANONICAL",
        "title": case["title"], "priority": case["priority"], "status": case["status"],
        "preconditions": case.get("preconditions", []),
        "test_data": case.get("test_data", []),
        "steps": [{"action": s["action"], "expected_result": s.get("expected_result")} for s in case.get("steps", [])],
        "postconditions": case.get("postconditions", []), "cleanup": cleanup, "state_contract": state_contract(cleanup),
        "requirement_refs": case.get("source_identifiers", []),
        "related_test_cases": [], "execution_tags": list(case.get("tags", [])),
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": case.get("automation_readiness"),
        "readiness_blockers": list(case.get("readiness_blockers", [])),
        "automation_layer": case.get("automation_layer"), "automation_tool_hint": case.get("automation_tool_hint"),
        "execution_variants": case.get("execution_variants", []), "request_contract": case.get("request_contract"),
        "environment_requirements": [], "required_resources": [], "chaos_run_id": None,
    }


def _export_chaos_case(chaos_run_id: str, case: dict[str, Any]) -> dict[str, Any]:
    return {
        "export_key": chaos_export_key(chaos_run_id, case["id"]), "local_id": case["id"],
        "source_kind": "CHAOS", "title": case["title"], "priority": case.get("priority", "MEDIUM"),
        "status": case.get("status", "NEEDS_REVIEW"),
        "preconditions": case.get("preconditions", []), "test_data": case.get("test_data", []),
        "steps": [{"action": s["action"], "expected_result": s.get("expected_result")} for s in case.get("steps", [])],
        "postconditions": case.get("postconditions", []), "cleanup": [], "state_contract": state_contract([]),
        "requirement_refs": case.get("related_source_identifiers", []),
        "related_test_cases": case.get("related_test_cases", []), "execution_tags": case.get("execution_tags", []),
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": None,
        "readiness_blockers": sorted({u["kind"] for u in case.get("unknowns", []) if u.get("kind")}),
        "automation_layer": None, "automation_tool_hint": None, "execution_variants": [], "request_contract": None,
        "environment_requirements": case.get("environment_requirements", []),
        "required_resources": case.get("required_resources", []), "chaos_run_id": chaos_run_id,
    }


def build_export_package(
    run_dir: Path, *, chaos_ids: list[str] | None = None, requirement_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`chaos_ids=None` includes every finalized chaos run under this parent; an empty
    list means canonical-only; a specific list includes exactly those (each must be
    FINALIZED — an unfinished run is never consumed, and naming one is an error)."""
    run_dir = Path(run_dir).resolve()
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    run = read_json(run_dir / "run.json")
    # Finalized chaos runs of this run and of the revision it explicitly supersedes; the
    # internal storage folder keeps its historical name `challenges/`.
    finalized = {item["chaos_run_id"]: item for item in pipeline._chaos_runs_for(run_dir)}
    if chaos_ids is None:
        picked = list(finalized.values())
    else:
        picked = []
        parents = [run_dir] + ([run_dir.parent / run["supersedes"]] if run.get("supersedes") else [])
        for chaos_id in chaos_ids:
            if chaos_id in finalized:
                picked.append(finalized[chaos_id])
            elif any((parent / "challenges" / chaos_id / "challenge-run.json").is_file() for parent in parents):
                raise ValueError(f"chaos run {chaos_id!r} is not finalized; only a finalized run can be exported")
            else:
                raise ValueError(f"chaos run {chaos_id!r} does not exist under {run_dir}")
    chaos_runs: list[dict[str, Any]] = []
    export_cases: list[dict[str, Any]] = [_export_canonical_case(case) for case in canonical["cases"]]
    for item in picked:
        export_cases.extend(_export_chaos_case(item["chaos_run_id"], case) for case in item["cases"])
        chaos_runs.append({"chaos_run_id": item["chaos_run_id"], "parent_run_id": item["parent_run_id"],
                           "cases": len(item["cases"])})
    requirement_mapping = requirement_mapping or {}
    by_identifier: dict[str, list[str]] = {}
    for entry in export_cases:
        origin = "DIRECT"
        idents = [normalize_identifier(v) for v in entry["requirement_refs"] if v]
        if not idents and entry["source_kind"] == "CHAOS" and entry["related_test_cases"]:
            related = [c for c in export_cases if c["source_kind"] == "CANONICAL" and c["local_id"] in entry["related_test_cases"]]
            idents = sorted({normalize_identifier(i) for case in related for i in case["requirement_refs"] if i})
            origin = "INHERITED_FROM_RELATED_TC"
        entry["trace_origin"] = origin if idents else "UNASSIGNED"
        for identifier in idents or [UNASSIGNED]:
            by_identifier.setdefault(identifier, []).append(entry["export_key"])
    req_titles = {normalize_identifier(r["source_identifier"]): (r["source_identifier"], r.get("source_title"))
                  for r in canonical["index"]["requirements"]}
    requirements = []
    for identifier, keys in sorted(by_identifier.items(), key=lambda item: (item[0] == UNASSIGNED, item[0])):
        if identifier == UNASSIGNED:
            requirements.append({"identifier": None, "title": None, "suite_name": UNASSIGNED,
                                 "external_id": None, "test_case_refs": sorted(set(keys))})
            continue
        display, title = req_titles.get(identifier, (identifier, None))
        requirements.append({
            "identifier": display, "title": title, "suite_name": suite_name(display, title),
            "external_id": (requirement_mapping.get(display) or {}).get("external_id"),
            "test_case_refs": sorted(set(keys)),
        })
    canonical_count = sum(1 for c in export_cases if c["source_kind"] == "CANONICAL")
    suites = _organization_suites(run_dir, canonical, picked, requirements)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_run": {"run_id": run["run_id"], "canonical_digest": canonical.get("semantic_fingerprint")},
        "chaos_runs": chaos_runs,
        "requirements": requirements,
        "suites": suites,
        "test_cases": export_cases,
        "diagnostics": {
            "canonical_test_cases": canonical_count,
            "chaos_test_cases": len(export_cases) - canonical_count,
            "requirement_groups": sum(1 for r in requirements if r["identifier"]),
            "unassigned_cases": len(by_identifier.get(UNASSIGNED, [])),
            "suites": len(suites),
            "suite_placements": sum(len(s["test_case_refs"]) for s in suites),
            "multi_suite_cases": sum(1 for count in _placements(suites).values() if count > 1),
            "cloned_test_cases": 0,
        },
    }


def suite_name(identifier: str | None, title: str | None) -> str:
    """`identifier — official title` when both exist; any official identifier scheme works."""
    if identifier and title and title.strip() and title.strip() != identifier:
        return f"{identifier} — {title.strip()}"
    return identifier or title or UNASSIGNED


SUITE_TYPES = {"FUNCTIONAL": "REQUIREMENT_BASED", "USE_CASE": "STATIC", "TRANSVERSAL": "STATIC", "EXECUTION_VIEW": "STATIC"}


def _placements(suites: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for suite in suites:
        for key in suite["test_case_refs"]:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _organization_suites(run_dir: Path, canonical: dict[str, Any], chaos_runs: list[dict[str, Any]],
                         requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suites follow the publication organization (functional groups in operational order,
    transversal rules, execution views). Requirement identifiers stay trace metadata on each
    case. Without a persisted organization input, one suite per requirement is kept."""
    if not ((run_dir / "sources.json").is_file() and (run_dir / "run.json").is_file()):
        return [{"suite_name": r["suite_name"], "group": r["identifier"], "kind": "FUNCTIONAL",
                 "suite_type": "REQUIREMENT_BASED", "order_source": "CANONICAL_ORDER",
                 "test_case_refs": r["test_case_refs"]} for r in requirements]
    organization = pipeline.organization_for_run(run_dir, canonical, chaos_runs=chaos_runs)
    suites = []
    for group in organization["groups"]:
        keys = [canonical_export_key(m["case"]) if m["origin"] == "CANONICAL"
                else chaos_export_key(m["chaos_run_id"], m["case"]) for m in group["members"]]
        suites.append({
            "suite_name": group["label"], "group": group["id"], "kind": group["kind"],
            "suite_type": SUITE_TYPES.get(group["kind"], "STATIC"), "order_source": group["order_source"],
            "flow_reference": group.get("flow_reference"), "identifier": group.get("identifier"),
            "test_case_refs": list(dict.fromkeys(keys)),
        })
    placed = set(_placements(suites))
    orphans = [r for req in requirements for r in req["test_case_refs"] if r not in placed]
    if orphans:  # e.g. a chaos case related to nothing and tagged for no execution view
        suites.append({"suite_name": UNASSIGNED, "group": None, "kind": "UNASSIGNED", "suite_type": "STATIC",
                       "order_source": "CANONICAL_ORDER", "test_case_refs": list(dict.fromkeys(orphans))})
    return suites


def _suite_groups(package: dict[str, Any]) -> list[dict[str, Any]]:
    """FTD's own organization as the generic named groups `azure_devops.build_group_suite_mapping`
    expects. Naming a group is FTD aggregation; turning groups into Azure Suite placements is
    delegated."""
    return [{"suite": s["suite_name"], "suite_type": s["suite_type"], "export_keys": s["test_case_refs"]}
            for s in package["suites"]]


def preview_export(
    package: dict[str, Any], *, project: str, plan: str, suite: str, mapping: dict[str, Any] | None = None,
    include_needs_review: bool = True,
) -> dict[str, Any]:
    """Local and read-only: no remote call happens here. All Azure-specific mapping,
    diffing and Suite placement is delegated to integrations/azure_devops.py."""
    carried = ("title", "priority", "status", "preconditions", "test_data", "steps", "postconditions", "cleanup",
               "state_contract", "requirement_refs", "related_test_cases", "source_kind", "automation_suitability",
               "automation_readiness", "readiness_blockers", "automation_layer", "automation_tool_hint",
               "required_resources", "environment_requirements", "chaos_run_id", "execution_variants",
               "request_contract")
    azure_cases = [{"id": case["export_key"], "tags": case["execution_tags"], "coverage_point_refs": [],
                    **{field: case.get(field) for field in carried}} for case in package["test_cases"]]
    return build_preview(
        azure_cases, mapping or {}, project=project, plan=plan, suite=suite,
        include_needs_review=include_needs_review,
        suite_mapping=build_group_suite_mapping(_suite_groups(package)),
    )


def convert_run(
    run_dir: Path, *, chaos_ids: list[str] | None = None, output: Any = "json",
    requirement_mapping: dict[str, Any] | None = None, target: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """/ftd-azure: validated FTD state -> local Azure DevOps input JSON. Writes
    `<artifact_root>/output/azure/azure-export-package.json` (requirement-grouped input) and
    `azure-preview.json` (create/update/unchanged/skipped/conflicts plus Suite placements,
    diffed against local integration state). Never authenticates, never calls Azure."""
    formats = {str(token).strip().casefold() for token in (output.split(",") if isinstance(output, str) else output)}
    if formats != {"json"}:
        raise ValueError("/ftd-azure produces local JSON only; use --output json")
    run_dir = Path(run_dir).resolve()
    run = read_json(run_dir / "run.json")
    package = build_export_package(run_dir, chaos_ids=chaos_ids, requirement_mapping=requirement_mapping)
    target = target or {}
    state = migrate_integration_state(load_integration_state(run_dir))
    preview = preview_export(
        package, project=target.get("project"), plan=target.get("plan") or run["run_id"],
        suite=target.get("suite") or run["run_id"], mapping={"test_cases": state.get("test_cases", {})},
    )
    preview["operation"] = "LOCAL_PREVIEW_ONLY"
    destination = Path(run["artifact_root"]) / "output" / "azure"
    write_json(destination / "azure-export-package.json", package)
    write_json(destination / "azure-preview.json", preview)
    return {
        "package": str(destination / "azure-export-package.json"),
        "preview": str(destination / "azure-preview.json"),
        "chaos_runs": [c["chaos_run_id"] for c in package["chaos_runs"]],
        **package["diagnostics"],
        "create": len(preview["create"]), "update": len(preview["update"]),
        "unchanged": len(preview["unchanged"]), "skipped": len(preview["skipped"]),
        "conflicts": len(preview["conflicts"]), "live_azure_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="/ftd-azure: local Azure DevOps input JSON from a finalized run.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", default="json")
    parser.add_argument("--chaos-id", action="append", default=None, help="repeatable; omit for all finalized chaos runs")
    parser.add_argument("--canonical-only", action="store_true", help="include no chaos runs")
    parser.add_argument("--requirement-mapping", help="path to {identifier: {external_id}} JSON")
    parser.add_argument("--project")
    parser.add_argument("--plan")
    parser.add_argument("--suite")
    args = parser.parse_args(argv)
    try:
        result = convert_run(
            args.run, chaos_ids=[] if args.canonical_only else args.chaos_id, output=args.output,
            requirement_mapping=read_json(args.requirement_mapping) if args.requirement_mapping else None,
            target={"project": args.project, "plan": args.plan, "suite": args.suite},
        )
    except (ValueError, OSError) as exc:
        print(json.dumps({"errors": [str(exc)]}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
