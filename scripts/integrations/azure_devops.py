#!/usr/bin/env python3
"""Preview-first, idempotent Azure DevOps Test Plans adapter contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol


class AzureTransport(Protocol):
    def create_test_case(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_test_case(self, external_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def map_test_case(case: dict[str, Any]) -> dict[str, Any]:
    """Map portable Test Plan concepts plus the execution context an executor needs to run
    the case without the canonical suite at hand: its fixture definitions (test_data), its
    end state and cleanup, and whether state is restored by the case itself or by a harness
    reset (state_contract). The canonical suite remains authoritative."""
    return {
        "local_id": case["id"],
        "title": case["title"],
        "priority": case["priority"],
        "preconditions": list(case.get("preconditions") or []),
        "test_data": [dict(row) for row in case.get("test_data") or []],
        "steps": [
            {"action": step["action"], "expected_result": step.get("expected_result")}
            for step in case.get("steps", [])
        ],
        "postconditions": list(case.get("postconditions") or []),
        "cleanup": list(case.get("cleanup") or []),
        "tags": list(case.get("tags", [])),
        "trace_refs": {
            "requirements": list(case.get("requirement_refs", [])),
            "coverage_points": list(case.get("coverage_point_refs", [])),
            "related_test_cases": list(case.get("related_test_cases") or []),
        },
        "status": case["status"],
        "source_kind": case.get("source_kind", "CANONICAL"),
        "automation": {
            "suitability": case.get("automation_suitability"),
            "readiness": case.get("automation_readiness"),
            "readiness_blockers": list(case.get("readiness_blockers") or []),
            "layer": case.get("automation_layer"),
            "tool_hint": case.get("automation_tool_hint"),
        },
        "execution": {
            "state_contract": case.get("state_contract") or ("SELF_CLEANING" if case.get("cleanup") else "REQUIRES_FIXTURE_RESET"),
            "required_resources": list(case.get("required_resources") or []),
            "environment_requirements": list(case.get("environment_requirements") or []),
            "variants": [dict(v) for v in case.get("execution_variants") or []],
            "request_contract": dict(case["request_contract"]) if case.get("request_contract") else None,
        },
    }


RISK_SUITE_TAGS = (
    "negative", "operator-error", "adversarial", "resilience", "fault-injection",
    "recovery", "concurrency", "e2e", "cross-cutting", "security", "data-integrity",
)


def build_group_suite_mapping(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Azure Test Plan/Suite placement for arbitrary named groups.

    Each group is `{"suite": name, "suite_type": optional, "export_keys": [...]}`.
    One export key may belong to several groups without being cloned — this is the
    generic Azure-side placement mechanism `ftd-azure` uses for requirement-by-
    requirement organization, and the same one `build_suite_mapping` below uses for
    risk-tag static suites. Callers (e.g. azure_export.py) decide what a "group" means
    in their own domain; this function only owns the Azure suite-membership shape.
    """
    memberships: dict[str, list[dict[str, Any]]] = {}
    suite_members: dict[str, list[str]] = {}
    for group in groups:
        suite = group["suite"]
        for key in group.get("export_keys", []):
            memberships.setdefault(key, []).append(
                {"suite": suite, "suite_type": group.get("suite_type", "REQUIREMENT_BASED")}
            )
            suite_members.setdefault(suite, []).append(key)
    # Members keep the order the caller gave (e.g. operational flow); suites keep theirs too.
    return {
        "memberships": [{"local_id": key, "suites": suites} for key, suites in memberships.items()],
        "suite_members": {name: list(dict.fromkeys(keys)) for name, keys in suite_members.items()},
        "canonical_test_cases": len(memberships), "cloned_test_cases": 0,
    }


def build_suite_mapping(
    cases: list[dict[str, Any]],
    *,
    requirement_suite: str,
    risk_suites: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Place one canonical Test Case in several organizational views without cloning it.

    Azure DevOps suites are folders over the same work item. A requirement-backed
    case belongs to its requirement suite and may also appear in a risk-oriented
    static suite; the semantic Test Case is never duplicated to achieve that.
    """
    risk_suites = risk_suites or {tag: f"Operational {tag}" for tag in RISK_SUITE_TAGS}
    unsupported = sorted(set(risk_suites) - set(RISK_SUITE_TAGS))
    if unsupported:
        raise ValueError("Unsupported risk suite tags: " + ", ".join(unsupported))
    suites: dict[str, list[str]] = {}
    memberships: list[dict[str, Any]] = []
    for case in cases:
        local_id = str(case["id"])
        tags = [str(value).strip().casefold() for value in case.get("tags", [])]
        targets = []
        if case.get("requirement_refs"):
            targets.append({"suite": requirement_suite, "suite_type": "REQUIREMENT_BASED"})
        for tag in RISK_SUITE_TAGS:
            if tag in tags and tag in risk_suites:
                targets.append({
                    "suite": risk_suites[tag], "suite_type": "STATIC", "tag": tag,
                })
        if not targets:
            targets.append({"suite": requirement_suite, "suite_type": "REQUIREMENT_BASED"})
        for target in targets:
            suites.setdefault(target["suite"], []).append(local_id)
        memberships.append({
            "local_id": local_id,
            "requirement_refs": list(case.get("requirement_refs", [])),
            "suites": targets,
        })
    return {
        "requirement_suite": requirement_suite,
        "memberships": memberships,
        "suite_members": {name: sorted(dict.fromkeys(ids)) for name, ids in sorted(suites.items())},
        "canonical_test_cases": len({item["local_id"] for item in memberships}),
        "suite_placements": sum(len(item["suites"]) for item in memberships),
        "cloned_test_cases": 0,
    }


def build_preview(
    cases: list[dict[str, Any]], mapping: dict[str, Any], *,
    project: str, plan: str, suite: str, include_needs_review: bool = False,
    external_versions: dict[str, str] | None = None,
    suite_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external_versions = external_versions or {}
    result: dict[str, Any] = {
        "target": {"project": project, "plan": plan, "suite": suite},
        "create": [], "update": [], "unchanged": [], "skipped": [], "conflicts": [],
    }
    if suite_mapping is not None:
        result["suite_mapping"] = suite_mapping
    entries = mapping.get("test_cases", {})
    for case in cases:
        payload = map_test_case(case)
        content_hash = _hash(payload)
        if case["status"] == "BLOCKED" or (case["status"] == "NEEDS_REVIEW" and not include_needs_review):
            result["skipped"].append({"local_id": case["id"], "status": case["status"]})
            continue
        prior = entries.get(case["id"])
        candidate = {"local_id": case["id"], "content_hash": content_hash, "payload": payload}
        if not prior:
            result["create"].append(candidate)
        elif prior.get("content_hash") == content_hash:
            result["unchanged"].append({"local_id": case["id"], "external_id": prior["external_id"]})
        elif external_versions.get(prior["external_id"], prior.get("last_synchronized_version")) != prior.get("last_synchronized_version"):
            result["conflicts"].append({"local_id": case["id"], "external_id": prior["external_id"]})
        else:
            result["update"].append({**candidate, "external_id": prior["external_id"]})
    return result


def apply_preview(preview: dict[str, Any], transport: AzureTransport, *, approved: bool = False) -> list[dict[str, Any]]:
    if not approved:
        return []
    if preview["conflicts"]:
        raise ValueError("Resolve preview conflicts before external writes")
    results = [transport.create_test_case(item["payload"]) for item in preview["create"]]
    results.extend(transport.update_test_case(item["external_id"], item["payload"]) for item in preview["update"])
    return results


def write_fallback_export(root: Path, preview: dict[str, Any]) -> list[Path]:
    destination = root / "exports" / "azure-devops"
    destination.mkdir(parents=True, exist_ok=True)
    documents = {
        "import-plan.json": {"target": preview["target"], "operation": "preview-only"},
        "test-case-payloads.json": {"create": preview["create"], "update": preview["update"]},
        "mapping-preview.json": preview,
    }
    paths = []
    for name, document in documents.items():
        path = destination / name
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _integration_state_path(run_dir: Path) -> Path:
    return Path(run_dir) / "integration-state" / "azure-devops.json"


def persist_integration_state(run_dir: Path, state: dict[str, Any]) -> Path:
    """Persist non-secret idempotency metadata under the private run directory."""
    path = _integration_state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def load_integration_state(run_dir: Path) -> dict[str, Any]:
    """The read side of `persist_integration_state`; empty state when nothing was synced yet."""
    path = _integration_state_path(run_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"test_cases": {}}


# --- guarded remote publication (v1: non-destructive) --------------------------------------
#
# `/ftd-azure` stays local. Only `/ftd-azure-publish` talks to Azure DevOps, in two phases:
# PREPARE reads the explicitly chosen target and writes a local publication plan (zero remote
# writes); APPLY revalidates that exact target and, only after explicit approval, creates or
# updates FTD-managed Test Cases, creates child static suites and adds suite placements. There
# is no delete, no removal, no plan creation and no overwrite of unmanaged or changed items.

PRIORITY_NUMBER = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
MANAGED_TAG = "ftd-managed"
READ_METHODS = ("organization", "list_projects", "list_test_plans", "list_suites", "list_suite_test_cases",
                "get_work_items", "list_plan_test_cases")
WRITE_METHODS = ("create_test_case", "update_test_case", "create_suite", "add_test_cases_to_suite")


class AzureRemote(Protocol):
    """Read side of a remote Azure DevOps organization. Ids are Azure's immutable ids."""
    def organization(self) -> dict[str, Any]: ...  # {"url", "name"}
    def list_projects(self) -> list[dict[str, Any]]: ...  # [{"id", "name"}]
    def list_test_plans(self, project_id: str) -> list[dict[str, Any]]: ...  # [{"id", "name", "root_suite_id"}]
    def list_suites(self, project_id: str, plan_id: int) -> list[dict[str, Any]]: ...  # [{"id", "name", "parent_id"}]
    def list_suite_test_cases(self, project_id: str, plan_id: int, suite_id: int) -> list[int]: ...
    def get_work_items(self, project_id: str, ids: list[int]) -> dict[int, dict[str, Any]]: ...  # {id: {"id", "rev", "title", "tags"}}
    def list_plan_test_cases(self, project_id: str, plan_id: int) -> list[dict[str, Any]]: ...  # [{"id", "title"}]


class AzureRemoteWriter(AzureRemote, Protocol):
    """The only write operations publication v1 may perform. There is deliberately no delete."""
    def create_test_case(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any]: ...  # {"id", "rev"}
    def update_test_case(self, project_id: str, work_item_id: int, fields: dict[str, Any], expected_rev: int) -> dict[str, Any]: ...
    def create_suite(self, project_id: str, plan_id: int, parent_suite_id: int, name: str) -> dict[str, Any]: ...  # {"id"}
    def add_test_cases_to_suite(self, project_id: str, plan_id: int, suite_id: int, work_item_ids: list[int]) -> None: ...


class ReadOnlyRemote:
    """Exposes only the read methods of a remote, so a preparation cannot write even by mistake."""

    def __init__(self, remote: Any):
        self._remote = remote

    def __getattr__(self, name: str) -> Any:
        if name not in READ_METHODS:
            raise PermissionError(f"{name} is not available while preparing a publication (read-only)")
        return getattr(self._remote, name)


class PublicationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _pick(items: list[dict[str, Any]], wanted: Any, kind: str) -> dict[str, Any]:
    """An explicit target: an exact id, or an exact name that exactly one item has. Never the
    first item, never the last used, never a near name."""
    if wanted in (None, ""):
        raise PublicationError("TARGET_REQUIRED", f"name the {kind} explicitly; available: {sorted(i['name'] for i in items)}")
    wanted_text = str(wanted)
    by_id = [i for i in items if str(i["id"]) == wanted_text]
    if len(by_id) == 1:
        return by_id[0]
    by_name = [i for i in items if i["name"] == wanted_text]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise PublicationError("AMBIGUOUS_TARGET", f"{len(by_name)} {kind}s are named {wanted_text!r}; select one by id: "
                               f"{sorted(str(i['id']) for i in by_name)}")
    near = sorted(i["name"] for i in items if i["name"].casefold() == wanted_text.casefold())
    hint = f" (names differing only in case: {near})" if near else ""
    raise PublicationError("TARGET_NOT_FOUND", f"no {kind} has id or exact name {wanted_text!r}{hint}")


def resolve_target(remote: Any, target: dict[str, Any]) -> dict[str, Any]:
    organization = remote.organization()
    wanted = str(target.get("organization") or "").rstrip("/")
    if not wanted:
        raise PublicationError("TARGET_REQUIRED", "name the Azure DevOps organization explicitly")
    if wanted not in {str(organization.get("url", "")).rstrip("/"), str(organization.get("name", ""))}:
        raise PublicationError("TARGET_MISMATCH", f"connected to {organization.get('url')}, not {wanted}")
    project = _pick(remote.list_projects(), target.get("project"), "project")
    plan = _pick(remote.list_test_plans(project["id"]), target.get("plan"), "test plan")
    root = None
    if target.get("root_suite") not in (None, ""):
        root = _pick(remote.list_suites(project["id"], plan["id"]), target["root_suite"], "suite")
    return {"organization": {"url": str(organization.get("url", "")).rstrip("/"), "name": organization.get("name")},
            "project": {"id": project["id"], "name": project["name"]},
            "plan": {"id": plan["id"], "name": plan["name"], "root_suite_id": plan.get("root_suite_id")},
            "root_suite": {"id": root["id"], "name": root["name"]} if root else None}


def work_item_fields(payload: dict[str, Any], export_key: str) -> dict[str, Any]:
    """Azure Test Case fields from a mapped payload. Identity is the local mapping, never the
    title; the export key is added as a non-secret provenance tag."""
    import html as _html

    def section(title: str, items: list[str]) -> str:
        return f"<h3>{_html.escape(title)}</h3><ul>" + "".join(f"<li>{_html.escape(str(i))}</li>" for i in items) + "</ul>" if items else ""

    data = [f"{row.get('name')}: {row.get('description')}" for row in payload.get("test_data", [])]
    execution = payload.get("execution", {})
    contract = execution.get("request_contract") or {}
    description = "".join([
        section("Preconditions", payload.get("preconditions", [])), section("Test data", data),
        section("Postconditions", payload.get("postconditions", [])), section("Cleanup", payload.get("cleanup", [])),
        section("State contract", [execution.get("state_contract")] if execution.get("state_contract") else []),
        section("Request contract", [f"{k}: {v}" for k, v in contract.items() if v]),
        section("Execution variants", [f"{v.get('kind')}: {v.get('description')}" for v in execution.get("variants", [])]),
        section("Required resources", execution.get("required_resources", [])),
        section("Environment", execution.get("environment_requirements", [])),
    ])
    steps = "".join(
        f'<step id="{n}" type="ValidateStep"><parameterizedString isformatted="true">{_html.escape(s["action"])}'
        f'</parameterizedString><parameterizedString isformatted="true">{_html.escape(s.get("expected_result") or "")}'
        f"</parameterizedString><description/></step>"
        for n, s in enumerate(payload.get("steps", []), 2))
    tags = [MANAGED_TAG, f"ftd-key:{export_key}", *payload.get("tags", [])]
    return {"System.Title": payload["title"],
            "Microsoft.VSTS.Common.Priority": PRIORITY_NUMBER.get(str(payload.get("priority")), 3),
            "Microsoft.VSTS.TCM.Steps": f'<steps id="0" last="{len(payload.get("steps", [])) + 1}">{steps}</steps>',
            "System.Description": description, "System.Tags": "; ".join(dict.fromkeys(tags))}


def build_publication_plan(
    package: dict[str, Any], mapping: dict[str, Any], remote: Any, target: dict[str, Any], source: dict[str, Any],
    *, include_needs_review: bool = True,
) -> dict[str, Any]:
    """PREPARE: read the explicit target and decide every operation. Performs only reads."""
    remote = ReadOnlyRemote(remote)
    resolved = resolve_target(remote, target)
    project_id, plan_id = resolved["project"]["id"], resolved["plan"]["id"]
    entries = mapping.get("test_cases", {})
    cases = package["test_cases"]
    mapped_ids = [int(entries[c["export_key"]]["external_id"]) for c in cases
                  if c["export_key"] in entries and entries[c["export_key"]].get("project_id") == project_id]
    remote_items = remote.get_work_items(project_id, mapped_ids) if mapped_ids else {}
    unmanaged_titles: dict[str, list[int]] = {}
    for item in remote.list_plan_test_cases(project_id, plan_id):
        if int(item["id"]) not in mapped_ids:
            unmanaged_titles.setdefault(item["title"], []).append(int(item["id"]))
    operations = []
    for case in cases:
        key = case["export_key"]
        payload = map_test_case({**case, "id": key, "tags": case.get("execution_tags", [])})
        content_hash = _hash(payload)
        entry = {"export_key": key, "content_hash": content_hash, "payload": payload}
        prior = entries.get(key)
        if case["status"] == "BLOCKED" or (case["status"] == "NEEDS_REVIEW" and not include_needs_review):
            operations.append({**entry, "action": "SKIPPED", "reason": case["status"]})
        elif prior and prior.get("project_id") not in (None, project_id):
            operations.append({**entry, "action": "CONFLICT", "reason": "MAPPED_TO_ANOTHER_PROJECT",
                               "work_item_id": prior.get("external_id")})
        elif prior:
            work_item_id = int(prior["external_id"])
            current = remote_items.get(work_item_id)
            if current is None:
                operations.append({**entry, "action": "CONFLICT", "reason": "MAPPED_WORK_ITEM_MISSING", "work_item_id": work_item_id})
            elif int(current["rev"]) != int(prior.get("last_synchronized_version", -1)):
                operations.append({**entry, "action": "CONFLICT", "reason": "REMOTE_CHANGED_SINCE_LAST_SYNC",
                                   "work_item_id": work_item_id, "remote_rev": current["rev"]})
            elif prior.get("content_hash") == content_hash:
                operations.append({**entry, "action": "UNCHANGED", "work_item_id": work_item_id})
            else:
                operations.append({**entry, "action": "UPDATE", "work_item_id": work_item_id, "expected_rev": int(current["rev"])})
        elif payload["title"] in unmanaged_titles:
            operations.append({**entry, "action": "CONFLICT", "reason": "POSSIBLE_UNMANAGED_MATCH",
                               "candidates": unmanaged_titles[payload["title"]]})
        else:
            operations.append({**entry, "action": "CREATE"})
    parent_id = resolved["root_suite"]["id"] if resolved["root_suite"] else resolved["plan"]["root_suite_id"]
    existing = [s for s in remote.list_suites(project_id, plan_id) if s.get("parent_id") == parent_id]
    suites, placements = [], []
    publishable = {op["export_key"] for op in operations if op["action"] in {"CREATE", "UPDATE", "UNCHANGED"}}
    for suite in package.get("suites", []):
        same = [s for s in existing if s["name"] == suite["suite_name"]]
        if len(same) > 1:
            suites.append({"name": suite["suite_name"], "action": "CONFLICT", "reason": "AMBIGUOUS_SUITE",
                           "candidates": [s["id"] for s in same]})
            continue
        present = set(remote.list_suite_test_cases(project_id, plan_id, same[0]["id"])) if same else set()
        suites.append({"name": suite["suite_name"], "action": "REUSE" if same else "CREATE",
                       "suite_id": same[0]["id"] if same else None, "suite_type": suite.get("suite_type")})
        for order, key in enumerate(suite["test_case_refs"], 1):
            op = next((o for o in operations if o["export_key"] == key), None)
            if key in publishable and not (op and op.get("work_item_id") and int(op["work_item_id"]) in present):
                placements.append({"suite": suite["suite_name"], "export_key": key, "order": order})
    summary = {
        "create_test_cases": sum(o["action"] == "CREATE" for o in operations),
        "update_test_cases": sum(o["action"] == "UPDATE" for o in operations),
        "unchanged": sum(o["action"] == "UNCHANGED" for o in operations),
        "conflicts": sum(o["action"] == "CONFLICT" for o in operations) + sum(s["action"] == "CONFLICT" for s in suites),
        "skipped": sum(o["action"] == "SKIPPED" for o in operations),
        "create_suites": sum(s["action"] == "CREATE" for s in suites),
        "reuse_suites": sum(s["action"] == "REUSE" for s in suites),
        "add_suite_placements": len(placements), "delete_operations": 0,
    }
    return {
        "schema_version": "1", "operation": "PUBLICATION_PLAN", "source": source, "target": resolved,
        "generated_at": _now(), "remote_versions": {str(k): v["rev"] for k, v in remote_items.items()},
        "operations": {"test_cases": operations, "suites": suites, "placements": placements}, "summary": summary,
    }


def publication_preview(plan: dict[str, Any]) -> str:
    """What will be written, and where. The destination must be obvious before any approval."""
    t, s = plan["target"], plan["summary"]
    root = f"{t['root_suite']['name']} ({t['root_suite']['id']})" if t.get("root_suite") else "none (plan root)"
    lines = [
        f"Organization: {t['organization'].get('name') or ''} ({t['organization']['url']})",
        f"Project: {t['project']['name']} ({t['project']['id']})",
        f"Test Plan: {t['plan']['name']} ({t['plan']['id']})",
        f"Root Suite: {root}",
        f"Source: {plan['source'].get('run_id')} + {str(plan['source'].get('package_digest'))[:12]}",
        f"Canonical digest: {plan['source'].get('canonical_digest')}",
        "",
        f"CREATE test cases       {s['create_test_cases']}",
        f"UPDATE test cases       {s['update_test_cases']}",
        f"UNCHANGED               {s['unchanged']}",
        f"CONFLICT                {s['conflicts']}",
        f"SKIPPED                 {s['skipped']}",
        f"CREATE suites           {s['create_suites']}",
        f"REUSE suites            {s['reuse_suites']}",
        f"ADD suite placements    {s['add_suite_placements']}",
        f"DELETE operations       {s['delete_operations']}",
    ]
    return "\n".join(lines)


def approval_phrase(plan: dict[str, Any]) -> str:
    return f"PUBLISH {plan['target']['project']['name']} / {plan['target']['plan']['name']}"


def apply_publication_plan(
    plan: dict[str, Any], remote: Any, mapping: dict[str, Any], *,
    confirmation: str | None = None, approved: bool = False,
) -> dict[str, Any]:
    """APPLY: revalidate the exact target and remote versions, then write only after explicit
    approval. Any mismatch or new conflict stops before the first write."""
    result = {"status": "NOT_APPLIED", "writes": 0, "preview": publication_preview(plan)}
    target = plan["target"]
    current = resolve_target(ReadOnlyRemote(remote), {
        "organization": target["organization"]["url"], "project": target["project"]["id"],
        "plan": target["plan"]["id"], "root_suite": (target.get("root_suite") or {}).get("id")})
    if (current["project"]["id"], current["plan"]["id"]) != (target["project"]["id"], target["plan"]["id"]):
        raise PublicationError("TARGET_MISMATCH", "the remote target differs from the one this plan was prepared for")
    if plan["summary"]["conflicts"]:
        return {**result, "status": "CONFLICTS", "reason": "resolve the plan's conflicts and prepare again"}
    project_id, plan_id = target["project"]["id"], target["plan"]["id"]
    updates = [op for op in plan["operations"]["test_cases"] if op["action"] == "UPDATE"]
    now_items = remote.get_work_items(project_id, [int(op["work_item_id"]) for op in updates]) if updates else {}
    changed = [op["export_key"] for op in updates
               if int(now_items.get(int(op["work_item_id"]), {}).get("rev", -1)) != int(op["expected_rev"])]
    if changed:
        return {**result, "status": "CONFLICTS", "reason": f"remote Test Cases changed since prepare: {changed}"}
    if not (approved or confirmation == approval_phrase(plan)):
        return {**result, "status": "APPROVAL_REQUIRED",
                "reason": f"type {approval_phrase(plan)!r} to confirm, or pass the explicit approval flag"}
    entries = mapping.setdefault("test_cases", {})
    work_item_of: dict[str, int] = {}
    writes = 0
    for op in plan["operations"]["test_cases"]:
        key = op["export_key"]
        if op["action"] == "CREATE":
            created = remote.create_test_case(project_id, work_item_fields(op["payload"], key))
            writes += 1
            work_item_of[key] = int(created["id"])
            entries[key] = {"external_id": str(created["id"]), "project_id": project_id,
                            "last_synchronized_version": created["rev"], "content_hash": op["content_hash"]}
        elif op["action"] == "UPDATE":
            updated = remote.update_test_case(project_id, int(op["work_item_id"]), work_item_fields(op["payload"], key),
                                              int(op["expected_rev"]))
            writes += 1
            work_item_of[key] = int(op["work_item_id"])
            entries[key] = {"external_id": str(op["work_item_id"]), "project_id": project_id,
                            "last_synchronized_version": updated["rev"], "content_hash": op["content_hash"]}
        elif op["action"] == "UNCHANGED":
            work_item_of[key] = int(op["work_item_id"])
    parent_id = (target.get("root_suite") or {}).get("id") or target["plan"].get("root_suite_id")
    suite_of: dict[str, int] = {}
    for suite in plan["operations"]["suites"]:
        if suite["action"] == "CREATE":
            suite_of[suite["name"]] = int(remote.create_suite(project_id, plan_id, parent_id, suite["name"])["id"])
            writes += 1
        elif suite["action"] == "REUSE":
            suite_of[suite["name"]] = int(suite["suite_id"])
    for name, suite_id in suite_of.items():
        ids = [work_item_of[p["export_key"]] for p in sorted(plan["operations"]["placements"], key=lambda p: p["order"])
               if p["suite"] == name and p["export_key"] in work_item_of]
        if ids:
            remote.add_test_cases_to_suite(project_id, plan_id, suite_id, ids)
            writes += 1
    return {**result, "status": "APPLIED", "writes": writes, "mapping": mapping}


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --- credentials and the REST remote (runtime only; never persisted) ------------------------

class CredentialProvider(Protocol):
    def authorization_header(self) -> str: ...


class EnvironmentCredential:
    """A short-lived credential the user put in an environment variable they name explicitly."""

    def __init__(self, variable: str):
        self.variable = variable

    def authorization_header(self) -> str:
        import base64
        import os
        value = os.environ.get(self.variable, "")
        if not value:
            raise PublicationError("CREDENTIAL_MISSING", f"environment variable {self.variable} is empty")
        return "Basic " + base64.b64encode(f":{value}".encode()).decode()

    def __repr__(self) -> str:
        return f"EnvironmentCredential({self.variable!r})"


AZURE_DEVOPS_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"  # Azure DevOps application id (public)


def _find_azure_cli() -> str:
    """Locate the installed Azure CLI executable/shim for this platform.

    On Windows the CLI is installed as `az.cmd` (a batch shim), not `az.exe`. A bare
    `subprocess.run(["az", ...])` fails there with `[WinError 2] The system cannot find the
    file specified`, because `CreateProcess` does not apply `PATHEXT` resolution the way a
    shell does. `shutil.which` performs that same resolution (checking `PATHEXT` on Windows)
    without a shell and without building a command string, so every platform resolves the
    real executable path through it before it is placed in a structured argument list.
    """
    import shutil
    executable = shutil.which("az")
    if not executable:
        raise PublicationError(
            "AZURE_CLI_UNAVAILABLE",
            "the Azure CLI ('az') was not found on PATH. Install it "
            "(https://learn.microsoft.com/cli/azure/install-azure-cli) or use --auth interactive "
            "or --auth env:<VARIABLE> instead."
        )
    return executable


class AzureCliCredential:
    """The user's existing Azure CLI session (`az login`).

    The executable is resolved once per token fetch with `shutil.which` — never a shell,
    never a concatenated command string — and the resulting access token is cached in memory
    for a short, conservative window so repeated REST calls do not each spawn a new `az`
    process. Nothing is written to disk or logged.
    """

    RESOURCE = AZURE_DEVOPS_RESOURCE
    _CACHE_SECONDS = 300  # conservative; az itself also caches/refreshes independently

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_until: float = 0.0

    def authorization_header(self) -> str:
        import time
        now = time.monotonic()
        if self._token is None or now >= self._token_until:
            self._token = self._fetch_token()
            self._token_until = now + self._CACHE_SECONDS
        return "Bearer " + self._token

    def _fetch_token(self) -> str:
        import subprocess
        executable = _find_azure_cli()
        try:
            result = subprocess.run(
                [executable, "account", "get-access-token", "--resource", self.RESOURCE,
                 "--query", "accessToken", "-o", "tsv"],
                capture_output=True, text=True, check=False,
            )
        except OSError as exc:
            raise PublicationError("AZURE_CLI_UNAVAILABLE", f"could not run the Azure CLI ({executable}): {exc}") from exc
        token = result.stdout.strip()
        if result.returncode != 0 or not token:
            detail = (result.stderr or result.stdout or "").strip()
            raise PublicationError(
                "AZURE_CLI_NOT_AUTHENTICATED",
                "the Azure CLI has no usable session for Azure DevOps. Run `az login` (Azure "
                "DevOps-only accounts without an Azure subscription: `az login "
                "--allow-no-subscriptions`)." + (f" Detail: {detail[:300]}" if detail else "")
            )
        return token

    def __repr__(self) -> str:
        return "AzureCliCredential()"


class InteractiveCredential:
    """Microsoft Entra interactive sign-in through the optional azure-identity package.

    One `InteractiveBrowserCredential` is created lazily and kept for the lifetime of this
    object; azure-identity's own token cache then serves later `get_token` calls, refreshing
    silently only when a token nears expiry. `RestAzureRemote` asks for a fresh Authorization
    header on every REST call, so without this reuse each of those calls built a brand new
    credential and forced a fresh interactive browser sign-in — the browser opens at most
    once per publisher session instead. The token itself is never written anywhere.
    """

    def __init__(self) -> None:
        self._credential: Any = None  # the real InteractiveBrowserCredential, built once

    def _browser_credential(self) -> Any:
        if self._credential is None:
            try:
                from azure.identity import InteractiveBrowserCredential  # type: ignore
            except ImportError as exc:
                raise PublicationError("CREDENTIAL_UNAVAILABLE", "install azure-identity for interactive sign-in") from exc
            self._credential = InteractiveBrowserCredential()
        return self._credential

    def authorization_header(self) -> str:
        credential = self._browser_credential()
        try:
            token = credential.get_token(f"{AZURE_DEVOPS_RESOURCE}/.default")
        except Exception as exc:  # azure.core.exceptions.ClientAuthenticationError and friends
            raise PublicationError("INTERACTIVE_AUTH_FAILED", f"interactive sign-in failed or was cancelled: {exc}") from exc
        return "Bearer " + token.token

    def __repr__(self) -> str:
        return "InteractiveCredential()"


class RestAzureRemote:
    """Azure DevOps REST calls for publication v1. The credential header is computed per
    request and never stored; there is no delete method and no generic request method."""

    API = "api-version=7.1"

    def __init__(self, organization_url: str, credential: CredentialProvider, opener: Any = None):
        self.url = organization_url.rstrip("/")
        self._credential = credential
        self._opener = opener

    def _call(self, method: str, path: str, body: Any = None, content_type: str = "application/json") -> Any:
        import urllib.request
        if method not in {"GET", "POST", "PATCH"}:
            raise PublicationError("FORBIDDEN_OPERATION", f"{method} is not allowed by publication v1")
        separator = "&" if "?" in path else "?"
        request = urllib.request.Request(f"{self.url}/{path}{separator}{self.API}", method=method,
                                         data=None if body is None else json.dumps(body).encode("utf-8"))
        request.add_header("Authorization", self._credential.authorization_header())
        request.add_header("Content-Type", content_type)
        opener = self._opener or urllib.request.urlopen
        with opener(request) as response:
            raw = response.read()
        return json.loads(raw) if raw else None

    def organization(self) -> dict[str, Any]:
        return {"url": self.url, "name": self.url.rsplit("/", 1)[-1]}

    def list_projects(self) -> list[dict[str, Any]]:
        return [{"id": p["id"], "name": p["name"]} for p in self._call("GET", "_apis/projects")["value"]]

    def list_test_plans(self, project_id: str) -> list[dict[str, Any]]:
        return [{"id": p["id"], "name": p["name"], "root_suite_id": (p.get("rootSuite") or {}).get("id")}
                for p in self._call("GET", f"{project_id}/_apis/testplan/plans")["value"]]

    def list_suites(self, project_id: str, plan_id: int) -> list[dict[str, Any]]:
        return [{"id": s["id"], "name": s["name"], "parent_id": (s.get("parentSuite") or {}).get("id")}
                for s in self._call("GET", f"{project_id}/_apis/testplan/Plans/{plan_id}/suites")["value"]]

    def list_suite_test_cases(self, project_id: str, plan_id: int, suite_id: int) -> list[int]:
        items = self._call("GET", f"{project_id}/_apis/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase")["value"]
        return [int(i["workItem"]["id"]) for i in items]

    def list_plan_test_cases(self, project_id: str, plan_id: int) -> list[dict[str, Any]]:
        found = []
        for suite in self.list_suites(project_id, plan_id):
            items = self._call("GET", f"{project_id}/_apis/testplan/Plans/{plan_id}/Suites/{suite['id']}/TestCase")["value"]
            found += [{"id": int(i["workItem"]["id"]), "title": i["workItem"].get("name", "")} for i in items]
        return found

    def get_work_items(self, project_id: str, ids: list[int]) -> dict[int, dict[str, Any]]:
        if not ids:
            return {}
        items = self._call("GET", f"{project_id}/_apis/wit/workitems?ids={','.join(map(str, ids))}&errorPolicy=omit")["value"]
        return {int(i["id"]): {"id": int(i["id"]), "rev": int(i["rev"]), "title": i["fields"].get("System.Title"),
                               "tags": i["fields"].get("System.Tags", "")} for i in items if i}

    def create_test_case(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        patch = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items()]
        item = self._call("POST", f"{project_id}/_apis/wit/workitems/$Test%20Case", patch, "application/json-patch+json")
        return {"id": int(item["id"]), "rev": int(item["rev"])}

    def update_test_case(self, project_id: str, work_item_id: int, fields: dict[str, Any], expected_rev: int) -> dict[str, Any]:
        patch = [{"op": "test", "path": "/rev", "value": expected_rev},
                 *({"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items())]
        item = self._call("PATCH", f"{project_id}/_apis/wit/workitems/{work_item_id}", patch, "application/json-patch+json")
        return {"id": int(item["id"]), "rev": int(item["rev"])}

    def create_suite(self, project_id: str, plan_id: int, parent_suite_id: int, name: str) -> dict[str, Any]:
        body = {"suiteType": "staticTestSuite", "name": name, "parentSuite": {"id": parent_suite_id}}
        return {"id": int(self._call("POST", f"{project_id}/_apis/testplan/Plans/{plan_id}/suites", body)["id"])}

    def add_test_cases_to_suite(self, project_id: str, plan_id: int, suite_id: int, work_item_ids: list[int]) -> None:
        body = [{"workItem": {"id": work_item_id}} for work_item_id in work_item_ids]
        self._call("POST", f"{project_id}/_apis/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase", body)

    def __repr__(self) -> str:
        return f"RestAzureRemote({self.url!r})"
