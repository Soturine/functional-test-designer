#!/usr/bin/env python3
"""ftd-azure: FTD-run aggregation for a normalized Azure DevOps Test Plans package,
organized requirement by requirement.

This module owns only the FTD side: selecting a canonical run and its finalized
Challenge runs, minting stable scoped export keys, normalizing canonical/Challenge
cases into common export records, and building requirement -> case relationships.
Every Azure-specific concern — payload mapping, Suite placement, create/update/
unchanged/conflict diffing, external ids, content hashes, integration state and
transport/publish — stays owned by `integrations/azure_devops.py`; this module calls
into it rather than reimplementing any of it. `ftd-mcp` (canonical-only, single suite)
keeps working unchanged; `ftd-azure` is the richer canonical+Challenge, requirement-
grouped packaging workflow, sharing the same underlying primitives.

A Challenge case (`CH-017`) never becomes `TC-244`: locally it stays a Challenge
identity forever. Only its Azure *export key* — `challenge:<challenge_id>:CH-017` —
identifies it as a Test Case work item to Azure, so two challenge runs that both
happen to mint `CH-001` never collide remotely.
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

UNASSIGNED = "Challenge / Unassigned"
SCHEMA_VERSION = "1"


def canonical_export_key(local_id: str) -> str:
    return f"canonical:{local_id}"


def challenge_export_key(challenge_run_id: str, local_id: str) -> str:
    return f"challenge:{challenge_run_id}:{local_id}"


def _export_canonical_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "export_key": canonical_export_key(case["id"]), "local_id": case["id"], "source_kind": "CANONICAL",
        "title": case["title"], "priority": case["priority"], "status": case["status"],
        "preconditions": case.get("preconditions", []),
        "test_data": case.get("test_data", []),
        "steps": [{"action": s["action"], "expected_result": s.get("expected_result")} for s in case.get("steps", [])],
        "postconditions": case.get("postconditions", []),
        "requirement_refs": case.get("source_identifiers", []),
        "related_test_cases": [], "execution_tags": list(case.get("tags", [])),
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": case.get("automation_readiness"),
        "environment_requirements": [], "required_resources": [], "challenge_run_id": None,
    }


def _export_challenge_case(challenge_run_id: str, case: dict[str, Any]) -> dict[str, Any]:
    return {
        "export_key": challenge_export_key(challenge_run_id, case["id"]), "local_id": case["id"],
        "source_kind": "CHALLENGE", "title": case["title"], "priority": case.get("priority", "MEDIUM"),
        "status": case.get("status", "NEEDS_REVIEW"),
        "preconditions": case.get("preconditions", []), "test_data": case.get("test_data", []),
        "steps": [{"action": s["action"], "expected_result": s.get("expected_result")} for s in case.get("steps", [])],
        "postconditions": case.get("postconditions", []),
        "requirement_refs": case.get("related_source_identifiers", []),
        "related_test_cases": case.get("related_test_cases", []), "execution_tags": case.get("execution_tags", []),
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": None,
        "environment_requirements": case.get("environment_requirements", []),
        "required_resources": case.get("required_resources", []), "challenge_run_id": challenge_run_id,
    }


def build_export_package(
    run_dir: Path, *, challenge_ids: list[str] | None = None, requirement_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`challenge_ids=None` includes every finalized challenge run under this parent;
    an empty list means canonical-only; a specific list includes exactly those (each
    must be FINALIZED — an unfinished run is never consumed)."""
    run_dir = Path(run_dir).resolve()
    canonical = pipeline.read_canonical(run_dir / "canonical-suite.json")
    run = read_json(run_dir / "run.json")
    challenges_dir = run_dir / "challenges"
    available = sorted(p.name for p in challenges_dir.iterdir()) if challenges_dir.is_dir() else []
    selected = available if challenge_ids is None else challenge_ids
    challenge_runs: list[dict[str, Any]] = []
    export_cases: list[dict[str, Any]] = [_export_canonical_case(case) for case in canonical["cases"]]
    for challenge_id in selected:
        lineage_path = challenges_dir / challenge_id / "challenge-run.json"
        cases_path = challenges_dir / challenge_id / "challenge-cases.json"
        if not lineage_path.is_file():
            raise ValueError(f"challenge {challenge_id!r} does not exist under {run_dir}")
        lineage = read_json(lineage_path)
        if lineage.get("status") != "FINALIZED" or not cases_path.is_file():
            if challenge_ids is not None:
                raise ValueError(f"challenge {challenge_id!r} is not finalized; only a finalized run can be exported")
            continue
        cases = read_json(cases_path)["cases"]
        export_cases.extend(_export_challenge_case(challenge_id, case) for case in cases)
        challenge_runs.append({"challenge_run_id": challenge_id, "cases": len(cases)})
    requirement_mapping = requirement_mapping or {}
    requirements = []
    by_identifier: dict[str, list[str]] = {}
    by_export_key = {c["export_key"]: c for c in export_cases}
    known_canonical_ids = {c["local_id"] for c in export_cases if c["source_kind"] == "CANONICAL"}
    for entry in export_cases:
        origin = "DIRECT"
        idents = [normalize_identifier(v) for v in entry["requirement_refs"] if v]
        if not idents and entry["source_kind"] == "CHALLENGE" and entry["related_test_cases"]:
            related = [c for c in export_cases if c["source_kind"] == "CANONICAL" and c["local_id"] in entry["related_test_cases"]]
            idents = sorted({normalize_identifier(i) for case in related for i in case["requirement_refs"] if i})
            origin = "INHERITED_FROM_RELATED_TC"
        entry["trace_origin"] = origin if idents else "UNASSIGNED"
        for identifier in idents or [UNASSIGNED]:
            by_identifier.setdefault(identifier, []).append(entry["export_key"])
    req_titles = {normalize_identifier(r["source_identifier"]): (r["source_identifier"], r.get("source_title"))
                 for r in canonical["index"]["requirements"]}
    for identifier, keys in sorted(by_identifier.items()):
        if identifier == UNASSIGNED:
            requirements.append({"identifier": None, "title": UNASSIGNED, "external_id": None,
                                 "test_case_refs": sorted(set(keys))})
            continue
        display, title = req_titles.get(identifier, (identifier, None))
        requirements.append({
            "identifier": display, "title": title,
            "external_id": (requirement_mapping.get(display) or {}).get("external_id"),
            "test_case_refs": sorted(set(keys)),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "source_run": {"run_id": run["run_id"], "canonical_digest": canonical.get("semantic_fingerprint")},
        "challenge_runs": challenge_runs,
        "requirements": requirements,
        "test_cases": export_cases,
        "diagnostics": {
            "canonical_test_cases": len(known_canonical_ids),
            "challenge_test_cases": len(export_cases) - len(known_canonical_ids),
            "requirement_groups": sum(1 for r in requirements if r["identifier"]),
            "unassigned_challenge_cases": len(by_identifier.get(UNASSIGNED, [])),
        },
    }


def _requirement_groups(package: dict[str, Any]) -> list[dict[str, Any]]:
    """FTD's own requirement -> case relationships, expressed as the generic named
    groups `azure_devops.build_group_suite_mapping` expects. Naming a group by its
    requirement title (or identifier, or the Unassigned bucket) is FTD aggregation;
    turning those groups into Azure Suite placements is not — that part is delegated."""
    return [{"suite": r["title"] or r["identifier"] or UNASSIGNED, "export_keys": r["test_case_refs"]}
            for r in package["requirements"]]


def preview_export(
    package: dict[str, Any], *, project: str, plan: str, suite: str, mapping: dict[str, Any] | None = None,
    include_needs_review: bool = True,
) -> dict[str, Any]:
    """Local and read-only: no remote call happens here. All Azure-specific mapping,
    diffing and Suite placement is delegated to integrations/azure_devops.py."""
    azure_cases = [{
        "id": case["export_key"], "title": case["title"], "priority": case["priority"], "status": case["status"],
        "preconditions": case["preconditions"], "steps": case["steps"], "tags": case["execution_tags"],
        "requirement_refs": case["requirement_refs"], "coverage_point_refs": [],
        "automation_suitability": case.get("automation_suitability"),
        "automation_readiness": case.get("automation_readiness"),
    } for case in package["test_cases"]]
    return build_preview(
        azure_cases, mapping or {}, project=project, plan=plan, suite=suite,
        include_needs_review=include_needs_review,
        suite_mapping=build_group_suite_mapping(_requirement_groups(package)),
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Project canonical + Challenge Test Cases into an Azure DevOps package.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--run", required=True)
    prepare.add_argument("--challenge-id", action="append", default=None, help="repeatable; omit for all finalized")
    prepare.add_argument("--requirement-mapping", help="path to {identifier: {external_id}} JSON")
    prepare.add_argument("--out", default="azure-export-package.json")

    preview = sub.add_parser("preview")
    preview.add_argument("--run", required=True)
    preview.add_argument("--package", default="azure-export-package.json")
    preview.add_argument("--project", required=True)
    preview.add_argument("--plan", required=True)
    preview.add_argument("--suite", required=True)
    preview.add_argument("--out", default="azure-preview.json")

    publish = sub.add_parser("publish")
    publish.add_argument("--run", required=True)
    publish.add_argument("--preview", default="azure-preview.json")
    publish.add_argument("--approved", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "prepare":
        req_mapping = read_json(args.requirement_mapping) if args.requirement_mapping else None
        package = build_export_package(args.run, challenge_ids=args.challenge_id, requirement_mapping=req_mapping)
        out = Path(args.run) / args.out
        write_json(out, package)
        result = {"package": str(out), **package["diagnostics"]}
    elif args.command == "preview":
        package = read_json(Path(args.run) / args.package)
        state = load_integration_state(args.run)
        preview = preview_export(package, project=args.project, plan=args.plan, suite=args.suite,
                                 mapping={"test_cases": state.get("test_cases", {})})
        out = Path(args.run) / args.out
        write_json(out, preview)
        result = {"preview": str(out), "create": len(preview["create"]), "update": len(preview["update"]),
                  "unchanged": len(preview["unchanged"]), "skipped": len(preview["skipped"]),
                  "conflicts": len(preview["conflicts"])}
    else:
        preview = read_json(Path(args.run) / args.preview)
        if not args.approved:
            result = {"published": False, "reason": "remote publication requires --approved"}
        else:
            fallback = write_fallback_export(Path(args.run), preview)
            result = {"published": False, "reason": "no live Azure transport is configured in this environment; "
                      "wrote a deterministic fallback export instead", "fallback_exports": [str(p) for p in fallback]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
