#!/usr/bin/env python3
"""FTD ADR and Azure DevOps: a LOCAL delta package, and an explicit, guarded ADR publication.

`/ftd --adr` only writes the local delta (`output/adr/<adr-id>/azure/`): the Test Cases whose
Azure definition must change — UPDATE of existing cases, CREATE of new ones — never the untouched
suite. An existing case keeps its export key (`canonical:TC-042`), so the publisher finds the same
Work Item; a case created by an ADR round gets `adr:TC-244`, stable across later rounds and free of
the transient round id. Work Item fields are the v2.4 fields (`FTD_METADATA_V1` untouched) plus one
additive, independently versioned `FTD_ADR_METADATA_V1` block.

`/ftd-azure-publish --prepare --adr <adr-id>` reuses the guarded publisher (read-only prepare,
target lock, revision conflicts, explicit approval, no delete) and adds ADR protections: the
Work Item must carry its ftd-key, and a semantic change to a Test Case that was executed — or
whose execution history cannot be read — is REVIEW_REQUIRED instead of UPDATE until the human
decides. Supersession is only a proposal. Execution runs, results, attachments and evidence are
never written: the remote write surface stays the four allowlisted Test Case / Suite operations.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from common import file_digest, read_json, stable_digest, write_json
import azure_export
import pipeline
from integrations import azure_devops as ado

ADR_METADATA_VERSION = "FTD_ADR_METADATA_V1"
# Fields whose change alters what an execution observes; a change only elsewhere is not semantic.
SEMANTIC_FIELDS = {"title", "objective", "preconditions", "test_data", "steps", "postconditions", "cleanup",
                   "requirement_refs", "type", "primary_type", "test_basis", "failure_domain", "request_contract",
                   "execution_variants", "status"}
REVIEW_UPDATE_SAME = "UPDATE_SAME_TEST_CASE"


def effective_canonical(run_dir: Path, document: dict[str, Any]) -> dict[str, Any]:
    """The effective suite in the canonical shape the organization builder reads (active cases)."""
    canonical = pipeline.read_canonical(Path(run_dir) / "canonical-suite.json")
    index = dict(canonical["index"], requirements=[*document["requirements"], *document["adr_requirements"]],
                 coverage_points=document["coverage_points"], scenarios=document["scenarios"])
    active = [c for c in document["cases"] if document["case_states"][c["id"]]["state"] == "ACTIVE"]
    return {**canonical, "index": index, "cases": active, "questions": {"questions": document["questions"]}}


def effective_suites(run_dir: Path, document: dict[str, Any]) -> list[dict[str, Any]]:
    """Suites of the effective organization, keyed by the stable export keys, in v2.4.2 display order."""
    organization = pipeline.organization_for_run(run_dir, effective_canonical(run_dir, document), chaos_runs=[])
    key_of = {cid: state["export_key"] for cid, state in document["case_states"].items()}
    suites = []
    for group in organization["groups"]:
        keys = [key_of[m["case"]] for m in group["members"] if m["origin"] == "CANONICAL"]
        suites.append({"suite_name": group["label"], "group": group["id"], "kind": group["kind"],
                       "suite_type": azure_export.SUITE_TYPES.get(group["kind"], "STATIC"),
                       "order_source": group["order_source"], "identifier": group.get("identifier"),
                       "test_case_refs": list(dict.fromkeys(keys))})
    return azure_export._display_ordered(suites)


def build_delta_package(run_dir: Path, document: dict[str, Any], analysis: dict[str, Any],
                        built: dict[str, Any]) -> dict[str, Any]:
    states = document["case_states"]
    history = document["case_history"]
    writes = [e for e in analysis["test_cases"] if e["action"] in {"UPDATE", "CREATE"}]
    records = []
    for entry in writes:
        case = built["cases"][entry["id"]]
        record = azure_export._export_canonical_case(case)
        record["export_key"] = states[entry["id"]]["export_key"]
        last = history[entry["id"]][-1]
        record["adr"] = {
            "adr_run_id": document["adr_run_id"], "action": entry["action"], "impact": entry["impact"],
            "decision_refs": entry["decisions"], "previous_definition_digest": last["previous_definition_digest"],
            "effective_definition_digest": last["effective_definition_digest"],
            "supersedes": states[entry["id"]].get("supersedes"),
            "changed_fields": last["changed_fields"],
            "semantic_change": entry["action"] == "UPDATE" and bool(set(last["changed_fields"]) & SEMANTIC_FIELDS),
            "source_refs": [{"source": p["source"], "reference": p["reference"]}
                            for d in analysis["decisions"] if d["id"] in entry["decisions"] for p in d["provenance"]],
        }
        records.append(record)
    keys = {r["export_key"] for r in records}
    suites = [{**s, "test_case_refs": [k for k in s["test_case_refs"] if k in keys]} for s in effective_suites(run_dir, document)]
    suites = [s for s in suites if s["test_case_refs"]]
    proposals = [{"export_key": states[e["id"]]["export_key"], "local_id": e["id"],
                  "superseded_by": states[e["superseded_by"]]["export_key"], "decision_refs": e["decisions"],
                  "reason": e["reason"]} for e in analysis["test_cases"] if e["action"] == "SUPERSEDE"]
    active = sum(s["state"] == "ACTIVE" for s in states.values())
    return {
        "schema_version": "adr-1", "kind": "FTD_ADR_AZURE_DELTA",
        "source_run": {"run_id": Path(run_dir).name, "canonical_digest": document["parent"]["canonical_digest"]},
        "adr": {"adr_run_id": document["adr_run_id"], "effective_digest": document["effective_digest"],
                "previous_adr_id": document["previous_adr_id"], "lineage": document["lineage"]},
        "test_cases": records, "suites": suites, "supersede_proposals": proposals,
        "diagnostics": {"create": sum(e["action"] == "CREATE" for e in writes),
                        "update": sum(e["action"] == "UPDATE" for e in writes),
                        "supersede_proposals": len(proposals), "untouched": active - len(records),
                        "delete_operations": 0, "live_azure_calls": 0},
    }


def validate_delta(package: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    """The delta holds exactly the intended definitions: no unaffected case, no duplicate key."""
    intended = {e["id"] for e in analysis["test_cases"] if e["action"] in {"UPDATE", "CREATE"}}
    present = [r["local_id"] for r in package["test_cases"]]
    errors = []
    if set(present) != intended or len(present) != len(set(present)):
        errors.append(f"the Azure ADR delta holds {sorted(present)} instead of exactly {sorted(intended)}")
    for record in package["test_cases"]:
        created = record["adr"]["action"] == "CREATE"
        expected = f"adr:{record['local_id']}" if created else None
        if created and record["export_key"] != expected:
            errors.append(f"{record['local_id']} must keep the stable key {expected}")
        if not created and not record["export_key"].startswith(("canonical:", "adr:")):
            errors.append(f"{record['local_id']} lost its existing export key")
        if document_round(record["export_key"]):
            errors.append(f"{record['export_key']} embeds an ADR round id")
    return errors


def document_round(key: str) -> bool:
    return any(part.startswith("adr-") for part in key.split(":"))


def adr_metadata(record: dict[str, Any]) -> dict[str, Any]:
    adr = record["adr"]
    return {"schema": ADR_METADATA_VERSION, "export_key": record["export_key"], "adr_run_id": adr["adr_run_id"],
            "action": adr["action"], "decision_refs": adr["decision_refs"],
            "previous_definition_digest": adr["previous_definition_digest"],
            "effective_definition_digest": adr["effective_definition_digest"], "supersedes": adr["supersedes"],
            "source_refs": adr["source_refs"]}


def adr_fields(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """The v2.4 Work Item fields, unchanged, plus one additive ADR block at the end of the description."""
    fields = ado.work_item_fields(payload, record["export_key"])
    block = json.dumps(adr_metadata(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fields["System.Description"] += f"<h3>FTD ADR metadata</h3><pre>{ADR_METADATA_VERSION} {html.escape(block)}</pre>"
    return fields


def read_adr_metadata(description: str) -> dict[str, Any] | None:
    import re
    match = re.search(re.escape(ADR_METADATA_VERSION) + r"(.*?)</pre>", description or "", re.S)
    if not match:
        return None
    return json.loads(html.unescape(re.sub(r"<[^>]*>", "", match.group(1))).strip())


# --- explicit ADR publication ----------------------------------------------------------

def _package(run_dir: Path, adr_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """The finalized round's delta, verified against the round manifest and the effective state."""
    import adr
    document = adr.load_effective(Path(run_dir), adr_id)
    manifest = adr.verify_round_manifest(adr._round_dir(Path(run_dir), adr_id))
    path = Path(manifest["outputs"]["azure/azure-adr-export-package.json"]["path"])
    if not path.is_file() or file_digest(path) != manifest["outputs"]["azure/azure-adr-export-package.json"]["digest"]:
        raise ado.PublicationError("PACKAGE_CHANGED", "the ADR delta package changed since finalize; finalize a new ADR round")
    package = read_json(path)
    if package["adr"]["effective_digest"] != document["effective_digest"]:
        raise ado.PublicationError("PACKAGE_STALE", "the ADR delta does not match the round's effective state")
    return path, package, document


def prepare_adr(run_dir: Path, adr_id: str, target: dict[str, Any], remote: Any, *,
                review_decisions: dict[str, str] | None = None) -> dict[str, Any]:
    """Read-only: plan the ADR delta against the explicit target. Zero remote writes."""
    run_dir = Path(run_dir).resolve()
    path, package, document = _package(run_dir, adr_id)
    review_decisions = review_decisions or {}
    mapping = azure_export.migrate_integration_state(ado.load_integration_state(run_dir))
    by_key = {r["export_key"]: r for r in package["test_cases"]}
    source = {"run_id": run_dir.name, "run_dir": str(run_dir), "adr_run_id": adr_id, "package_path": str(path),
              "package_digest": file_digest(path), "canonical_digest": package["source_run"]["canonical_digest"],
              "effective_digest": document["effective_digest"]}
    plan = ado.build_publication_plan(package, mapping, remote, target, source,
                                      emit=lambda case, payload: adr_fields(by_key[case["export_key"]], payload))
    reader = ado.ReadOnlyRemote(remote)
    project_id, plan_id = plan["target"]["project"]["id"], plan["target"]["plan"]["id"]
    updates = [op for op in plan["operations"]["test_cases"] if op["action"] == "UPDATE"]
    current = reader.get_work_items(project_id, [int(op["work_item_id"]) for op in updates]) if updates else {}
    for op in updates:
        record = by_key[op["export_key"]]
        work_item = int(op["work_item_id"])
        tags = [t.strip() for t in str(current.get(work_item, {}).get("tags", "")).split(";")]
        if f"ftd-key:{op['export_key']}" not in tags:
            op.update(action="CONFLICT", reason="FTD_KEY_OWNERSHIP_MISMATCH")
            continue
        try:
            history = reader.test_case_history(project_id, plan_id, work_item)
            executed = "EXECUTED" if history.get("executed") else "NOT_EXECUTED"
        except Exception as exc:  # unavailable or not permitted: never assumed empty
            history, executed = {"error": type(exc).__name__}, "EXECUTION_HISTORY_UNKNOWN"
        op["execution_history"] = {**history, "status": executed}
        decided = review_decisions.get(record["local_id"]) == REVIEW_UPDATE_SAME
        if record["adr"]["semantic_change"] and executed != "NOT_EXECUTED" and not decided:
            op.update(action="REVIEW_REQUIRED",
                      reason="REVIEW_REQUIRED_EXECUTED_TC" if executed == "EXECUTED" else "EXECUTION_HISTORY_UNKNOWN",
                      options=["update the same Test Case for future executions (--review "
                               f"{record['local_id']}={REVIEW_UPDATE_SAME})",
                               "create a successor Test Case in a new ADR round and keep this one as historical"])
    publishable = {op["export_key"] for op in plan["operations"]["test_cases"] if op["action"] in {"CREATE", "UPDATE", "UNCHANGED"}}
    plan["operations"]["placements"] = [p for p in plan["operations"]["placements"] if p["export_key"] in publishable]
    plan["operations"]["supersede_proposals"] = package["supersede_proposals"]
    actions = [op["action"] for op in plan["operations"]["test_cases"]]
    plan["summary"].update(
        create_test_cases=actions.count("CREATE"), update_test_cases=actions.count("UPDATE"),
        unchanged=actions.count("UNCHANGED"), review_required=actions.count("REVIEW_REQUIRED"),
        conflicts=actions.count("CONFLICT") + sum(s["action"] == "CONFLICT" for s in plan["operations"]["suites"]),
        supersede_proposals=len(package["supersede_proposals"]), untouched=package["diagnostics"]["untouched"],
        add_suite_placements=len(plan["operations"]["placements"]), delete_operations=0,
        execution_evidence_writes=0, execution_evidence_deletes=0)
    plan["operation"] = "ADR_PUBLICATION_PLAN"
    destination = path.parent / "publication-plan.json"
    write_json(destination, plan)
    return {"plan": str(destination), "summary": plan["summary"], "preview": preview(plan),
            "approval_phrase": ado.approval_phrase(plan), "remote_writes": 0}


def preview(plan: dict[str, Any]) -> str:
    s = plan["summary"]
    lines = ado.publication_preview(plan).splitlines()[:6] + [
        f"ADR round: {plan['source']['adr_run_id']} (effective {plan['source']['effective_digest'][:12]})", "",
        "ADR delta", f"CREATE                    {s['create_test_cases']}", f"UPDATE                    {s['update_test_cases']}",
        f"UNCHANGED                 {s['unchanged']}", f"REVIEW_REQUIRED           {s['review_required']}",
        f"CONFLICT                  {s['conflicts']}", f"SUPERSEDE_PROPOSAL        {s['supersede_proposals']}",
        f"DELETE                    {s['delete_operations']}", f"UNTOUCHED                 {s['untouched']}", "",
        f"Execution evidence writes {s['execution_evidence_writes']}",
        f"Execution evidence deletes {s['execution_evidence_deletes']}"]
    return "\n".join(lines)


def apply_adr(plan_path: Path, remote: Any, *, confirmation: str | None = None, approved: bool = False) -> dict[str, Any]:
    """Write the reviewed ADR plan after re-verifying package, effective state, canonical digest,
    target and remote revisions, and only with explicit approval. REVIEW_REQUIRED and supersede
    proposals are never written."""
    import adr
    plan = read_json(Path(plan_path))
    source = plan["source"]
    run_dir = Path(source["run_dir"])
    path, package, document = _package(run_dir, source["adr_run_id"])
    if file_digest(path) != source["package_digest"]:
        raise ado.PublicationError("PACKAGE_CHANGED", "the ADR delta changed since prepare; prepare again")
    if document["effective_digest"] != source["effective_digest"] or \
            adr.verify_canonical(run_dir)["semantic_fingerprint"] != source["canonical_digest"]:
        raise ado.PublicationError("STATE_CHANGED", "the ADR effective state or canonical suite changed since prepare")
    mapping = azure_export.migrate_integration_state(ado.load_integration_state(run_dir))
    result = ado.apply_publication_plan(plan, remote, mapping, confirmation=confirmation, approved=approved)
    if result["status"] == "APPLIED":
        written = {op["export_key"] for op in plan["operations"]["test_cases"] if op["action"] in {"CREATE", "UPDATE"}}
        for key in written:
            result["mapping"]["test_cases"][key].update(adr_run_id=source["adr_run_id"],
                                                         effective_digest=source["effective_digest"])
        ado.persist_integration_state(run_dir, result.pop("mapping"))
    record = {k: v for k, v in result.items() if k != "mapping"}
    write_json(Path(plan_path).with_name("publication-result.json"), {**record, "target": plan["target"]})
    return record


def local_preview(package: dict[str, Any]) -> dict[str, Any]:
    """What the delta would ask Azure for — computed locally, without any connection."""
    return {"operation": "LOCAL_ADR_DELTA_ONLY", "adr_run_id": package["adr"]["adr_run_id"],
            "create": [r["export_key"] for r in package["test_cases"] if r["adr"]["action"] == "CREATE"],
            "update": [r["export_key"] for r in package["test_cases"] if r["adr"]["action"] == "UPDATE"],
            "supersede_proposals": package["supersede_proposals"],
            "semantic_updates": [r["export_key"] for r in package["test_cases"] if r["adr"]["semantic_change"]],
            "untouched": package["diagnostics"]["untouched"], "delete_operations": 0, "live_azure_calls": 0,
            "digest": stable_digest(package)}
