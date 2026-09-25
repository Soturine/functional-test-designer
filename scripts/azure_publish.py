#!/usr/bin/env python3
"""/ftd-azure-publish: the only FTD command that can write to Azure DevOps.

Two explicit phases over the local `/ftd-azure` package (which itself never connects):

  --prepare  authenticates, reads the explicitly named organization/project/plan and writes a
             local `publication-plan.json` (CREATE/UPDATE/UNCHANGED/CONFLICT/SKIPPED, suites and
             placements). It performs zero remote writes.
  --apply    reopens that plan, checks the FTD package and canonical digests, revalidates the
             exact target and remote versions, shows what will be written and writes only after
             explicit approval (the typed phrase `PUBLISH <project> / <plan>`, or --approved).

Publication v1 is non-destructive: no delete, no suite-membership removal, no Test Plan
creation, no overwrite of unmanaged or remotely changed Test Cases. Credentials are
runtime-only and never written anywhere. All Azure specifics live in
integrations/azure_devops.py; this module only ties them to a finalized FTD run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import file_digest, read_json, write_json  # noqa: E402
import azure_export  # noqa: E402
import pipeline  # noqa: E402
from integrations.azure_devops import (  # noqa: E402
    AzureCliCredential, EnvironmentCredential, InteractiveCredential, PublicationError, RestAzureRemote,
    apply_publication_plan, approval_phrase, build_publication_plan, load_integration_state,
    persist_integration_state, publication_preview,
)


def _package_path(run_dir: Path) -> Path:
    run = read_json(run_dir / "run.json")
    return Path(run["artifact_root"]) / "output" / "azure" / "azure-export-package.json"


def _canonical_digest(run_dir: Path) -> str | None:
    return pipeline.read_canonical(run_dir / "canonical-suite.json").get("semantic_fingerprint")


def prepare(run_dir: Path, target: dict[str, Any], remote: Any, *, include_needs_review: bool = True) -> dict[str, Any]:
    """Read-only: resolve the explicit target and write the local publication plan."""
    run_dir = Path(run_dir).resolve()
    package_path = _package_path(run_dir)
    if not package_path.is_file():
        raise PublicationError("PACKAGE_MISSING", "run /ftd-azure first: the publisher consumes its local package")
    package = read_json(package_path)
    run_id = read_json(run_dir / "run.json")["run_id"]
    if package["source_run"]["run_id"] != run_id or package["source_run"].get("canonical_digest") != _canonical_digest(run_dir):
        raise PublicationError("PACKAGE_STALE", "the local package was not built from this run's current canonical suite")
    mapping = azure_export.migrate_integration_state(load_integration_state(run_dir))
    source = {"run_id": run_id, "run_dir": str(run_dir), "package_path": str(package_path),
              "package_digest": file_digest(package_path), "canonical_digest": package["source_run"].get("canonical_digest")}
    plan = build_publication_plan(package, mapping, remote, target, source, include_needs_review=include_needs_review)
    destination = package_path.parent / "publication-plan.json"
    write_json(destination, plan)
    return {"plan": str(destination), "summary": plan["summary"], "preview": publication_preview(plan),
            "approval_phrase": approval_phrase(plan), "remote_writes": 0}


def apply(plan_path: Path, remote: Any, *, confirmation: str | None = None, approved: bool = False) -> dict[str, Any]:
    """Write the prepared plan after digest, target and version checks and explicit approval."""
    plan = read_json(Path(plan_path))
    source = plan["source"]
    run_dir = Path(source["run_dir"])
    package_path = Path(source["package_path"])
    if not package_path.is_file() or file_digest(package_path) != source["package_digest"]:
        raise PublicationError("PACKAGE_CHANGED", "the FTD package changed since prepare; prepare again")
    if _canonical_digest(run_dir) != source["canonical_digest"]:
        raise PublicationError("CANONICAL_CHANGED", "the canonical suite changed since prepare; prepare again")
    mapping = azure_export.migrate_integration_state(load_integration_state(run_dir))
    result = apply_publication_plan(plan, remote, mapping, confirmation=confirmation, approved=approved)
    if result["status"] == "APPLIED":
        persist_integration_state(run_dir, result.pop("mapping"))
    record = {key: value for key, value in result.items() if key != "mapping"}
    write_json(Path(plan_path).with_name("publication-result.json"), {**record, "target": plan["target"]})
    return record


def remote_for(organization: str, auth: str) -> RestAzureRemote:
    """Credentials are chosen by the user at runtime; nothing about them is persisted."""
    if auth == "azure-cli":
        credential: Any = AzureCliCredential()
    elif auth == "interactive":
        credential = InteractiveCredential()
    elif auth.startswith("env:") and len(auth) > 4:
        credential = EnvironmentCredential(auth[4:])
    else:
        raise PublicationError("CREDENTIAL_REQUIRED", "choose --auth azure-cli, interactive or env:<VARIABLE>")
    return RestAzureRemote(organization, credential)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--prepare", action="store_true", help="read the target and write publication-plan.json (no writes)")
    phase.add_argument("--apply", type=Path, metavar="PLAN", help="apply a prepared publication-plan.json")
    parser.add_argument("--run", type=Path, help="finalized run (with --prepare)")
    parser.add_argument("--organization", help="organization URL, e.g. https://dev.azure.com/<org>")
    parser.add_argument("--project", help="project id or exact name")
    parser.add_argument("--plan", help="Test Plan id or exact name")
    parser.add_argument("--root-suite", help="optional destination suite id or exact name")
    parser.add_argument("--auth", default="", help="azure-cli | interactive | env:<VARIABLE>")
    parser.add_argument("--approved", action="store_true", help="explicit non-interactive approval (with --apply)")
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            missing = [flag for flag, value in (("--run", args.run), ("--organization", args.organization),
                                                ("--project", args.project), ("--plan", args.plan)) if not value]
            if missing:
                raise PublicationError("TARGET_REQUIRED", f"--prepare needs {', '.join(missing)}; the destination is "
                                                          "never guessed")
            result = prepare(args.run, {"organization": args.organization, "project": args.project, "plan": args.plan,
                                        "root_suite": args.root_suite}, remote_for(args.organization, args.auth))
            print(result["preview"])
        else:
            plan = read_json(args.apply)
            remote = remote_for(plan["target"]["organization"]["url"], args.auth)
            print(publication_preview(plan))
            confirmation = None
            if not args.approved and sys.stdin.isatty():
                confirmation = input(f"Type {approval_phrase(plan)!r} to publish: ").strip()
            result = apply(args.apply, remote, confirmation=confirmation, approved=args.approved)
    except (PublicationError, ValueError, OSError) as exc:
        print(json.dumps({"errors": [str(exc)]}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({k: v for k, v in result.items() if k != "preview"}, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
