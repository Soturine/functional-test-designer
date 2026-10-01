#!/usr/bin/env python3
"""Local files for a MANUAL Azure DevOps Test Case import (CSV), built from the `/ftd-azure`
package. Nothing here authenticates or connects: the user imports the files in Azure DevOps.

Azure's Test Case import creates a new work item for a row group with a blank ID and updates
the work item whose ID a row group carries (replacing its steps). The files are therefore split
by intent: blank-ID CREATE files only when the user says the target is new and empty (or allows
creation explicitly), and an UPDATE file whose rows carry the Azure ID matched by stable FTD
identity (`ftd-key:` tag, then the FTD_METADATA_V1 export key) — never by title.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from integrations.azure_devops import map_test_case, work_item_fields

# Azure's nine required import columns, then the mapped fields FTD also fills.
COLUMNS = ("ID", "Work Item Type", "Title", "Test Step", "Step Action", "Step Expected", "Area Path",
           "Assigned To", "State", "Priority", "Tags", "Description")
DEFAULT_STATE = "Design"  # Azure's default state for a new Test Case (Proposed category)
ACTIONS = ("CREATE", "UPDATE", "UNCHANGED", "CONFLICT", "UNMATCHED")
CREATE_DIR = "manual-import-create"
UPDATE_FILE = "manual-import-update.csv"
SECONDARY_FILE = "secondary-suite-placements.csv"
OUTPUTS = (UPDATE_FILE, SECONDARY_FILE, "suite-order.md", "manual-import-plan.json", "manual-import-summary.md")


class ManualImportError(ValueError):
    pass


def import_options(*, area_path: str | None, assigned_to: str | None = None, state: str | None = None) -> dict[str, str]:
    """Area Path is required (Azure checks it exists); Assigned To is never invented (blank stays
    blank); State defaults to Azure's Design. Single-line values only."""
    values = {"area_path": (area_path or "").strip(), "assigned_to": (assigned_to or "").strip(),
              "state": (state or DEFAULT_STATE).strip()}
    if not values["area_path"]:
        raise ManualImportError("--area-path is required: the Azure Area Path the Test Cases belong to, "
                                "e.g. <project>\\<area>")
    if not values["state"]:
        raise ManualImportError("--state must not be empty")
    for name, value in values.items():
        if any(ch in value for ch in "\r\n\t"):
            raise ManualImportError(f"--{name.replace('_', '-')} must be a single line")
    return values


def _payload(case: dict[str, Any]) -> dict[str, Any]:
    return map_test_case({**case, "id": case["export_key"], "tags": case.get("execution_tags", [])})


def case_rows(case: dict[str, Any], azure_id: str | None, options: dict[str, str]) -> list[dict[str, Any]]:
    """One row per step, each repeating the Test Case fields; steps keep their order and text."""
    payload = _payload(case)
    fields = work_item_fields(payload, case["export_key"])
    common = {"ID": azure_id or "", "Work Item Type": "Test Case", "Title": fields["System.Title"],
              "Area Path": options["area_path"], "Assigned To": options["assigned_to"], "State": options["state"],
              "Priority": fields["Microsoft.VSTS.Common.Priority"], "Tags": fields["System.Tags"],
              "Description": fields["System.Description"]}
    steps = payload["steps"] or [{"action": "", "expected_result": None}]
    return [{**common, "Test Step": number, "Step Action": step["action"], "Step Expected": step.get("expected_result") or ""}
            for number, step in enumerate(steps, 1)]


def suite_homes(package: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Each case's PRIMARY suite (the first in display order: requirement, use case, transversal,
    execution view) and the additional suites it is placed in by reference."""
    primary: dict[str, str] = {}
    additional: dict[str, list[str]] = {}
    for suite in package["suites"]:
        for key in suite["test_case_refs"]:
            if key not in primary:
                primary[key] = suite["suite_name"]
            elif suite["suite_name"] != primary[key] and suite["suite_name"] not in additional.get(key, []):
                additional.setdefault(key, []).append(suite["suite_name"])
    return primary, additional


def build_plan(package: dict[str, Any], options: dict[str, str], *, fresh_target: bool = False) -> dict[str, Any]:
    if not fresh_target:
        raise ManualImportError(
            "say what the Azure target holds: --fresh-target for a new, empty target (every case is created), "
            "or --existing-azure-export <file> to update a previously imported set without duplicates")
    primary, additional = suite_homes(package)
    entries = []
    for case in package["test_cases"]:
        key = case["export_key"]
        entries.append({"export_key": key, "ftd_id": case["local_id"],
                        "title": work_item_fields(_payload(case), key)["System.Title"], "status": case["status"],
                        "action": "CREATE", "azure_id": None, "primary_suite": primary.get(key),
                        "additional_suites": additional.get(key, [])})
    return {
        "schema_version": "1", "operation": "AZURE_MANUAL_IMPORT_PLAN", "source_run": package["source_run"],
        "mode": "CREATE", "target_assumption": "EMPTY", "existing_ids": "NONE",
        "duplicate_safety": "safe only for an empty/new target: every row group has a blank ID and creates a Test Case",
        "options": options, "summary": _summary(entries), "cases": entries,
    }


def _summary(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {"total_test_cases": len(entries), **{a.lower(): sum(e["action"] == a for e in entries) for a in ACTIONS}}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")[:60] or "suite"


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def _clear(destination: Path) -> None:
    """Remove only the files a previous generation wrote, so a stale CREATE file can never be
    imported by mistake; anything else in the folder (e.g. the user's Azure export) is kept."""
    for name in OUTPUTS:
        (destination / name).unlink(missing_ok=True)
    for path in (destination / CREATE_DIR).glob("[0-9][0-9]*-*.csv"):
        path.unlink()


def write_manual_import(package: dict[str, Any], destination: Path, plan: dict[str, Any]) -> dict[str, Any]:
    import json
    destination = Path(destination)
    _clear(destination)
    options = plan["options"]
    by_key = {case["export_key"]: case for case in package["test_cases"]}
    entry_of = {entry["export_key"]: entry for entry in plan["cases"]}
    files: list[str] = []
    update_rows: list[dict[str, Any]] = []
    for position, suite in enumerate(package["suites"], 1):
        rows = []
        for key in suite["test_case_refs"]:
            entry = entry_of.get(key)
            if not entry or entry["primary_suite"] != suite["suite_name"]:
                continue  # created or updated once, in its primary suite only
            if entry["action"] == "CREATE":
                rows += case_rows(by_key[key], None, options)
            elif entry["action"] == "UPDATE":
                update_rows += case_rows(by_key[key], entry["azure_id"], options)
        if rows:
            path = destination / CREATE_DIR / f"{position:02d}-{_slug(suite.get('identifier') or suite['suite_name'])}.csv"
            _write_csv(path, COLUMNS, rows)
            files.append(path.relative_to(destination).as_posix())
            for entry in plan["cases"]:
                if entry["action"] == "CREATE" and entry["primary_suite"] == suite["suite_name"]:
                    entry["file"] = files[-1]
    if update_rows:
        _write_csv(destination / UPDATE_FILE, COLUMNS, update_rows)
        files.append(UPDATE_FILE)
    secondary = [{"FTD ID": e["ftd_id"], "FTD Key": e["export_key"], "Azure ID": e["azure_id"] or "", "Title": e["title"],
                  "Primary Suite": e["primary_suite"], "Additional Suite": suite}
                 for e in plan["cases"] if e["action"] in {"CREATE", "UPDATE", "UNCHANGED"}
                 for suite in e["additional_suites"]]
    if secondary:
        _write_csv(destination / SECONDARY_FILE, ("FTD ID", "FTD Key", "Azure ID", "Title", "Primary Suite", "Additional Suite"),
                   secondary)
        files.append(SECONDARY_FILE)
    (destination / "suite-order.md").write_text(suite_order_markdown(package["suites"]), encoding="utf-8")
    plan["files"] = [*files, "suite-order.md", "manual-import-summary.md"]
    (destination / "manual-import-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "manual-import-summary.md").write_text(summary_markdown(plan), encoding="utf-8")
    return {"manual_import_dir": str(destination), "files": plan["files"], **plan["summary"], "mode": plan["mode"]}


def summary_markdown(plan: dict[str, Any]) -> str:
    s = plan["summary"]
    lines = [
        "# Azure manual import", "",
        f"- MODE: {plan['mode']}", f"- TARGET ASSUMPTION: {plan['target_assumption']}",
        f"- EXISTING IDS: {plan['existing_ids']}", f"- DUPLICATE SAFETY: {plan['duplicate_safety']}", "",
        "| | Test Cases |", "| --- | --- |", f"| Total FTD Test Cases | {s['total_test_cases']} |",
        *(f"| {action} | {s[action.lower()]} |" for action in ACTIONS), "",
        "Blank ID = new Test Case. Existing ID = update of that Test Case (Azure replaces its steps).", "",
        "## Files", "",
        *(f"- `{name}`" for name in plan.get("files", [])), "",
        "Import each file under `manual-import-create/` into the Suite its name shows (see `suite-order.md`); "
        "every Test Case is created once, in its primary Suite. Place it in further Suites with "
        "**Add existing test cases**, as listed in `secondary-suite-placements.csv` — never by importing it again.",
        "",
    ]
    held = [e for e in plan["cases"] if e["action"] in {"CONFLICT", "UNMATCHED"}]
    if held:
        lines += ["## Not imported", "", "| FTD ID | Action | Reason |", "| --- | --- | --- |",
                  *(f"| {e['ftd_id']} | {e['action']} | {e.get('reason', '')} |" for e in held), ""]
    return "\n".join(lines)


def suite_order_markdown(suites: list[dict[str, Any]]) -> str:
    """The Suites to create by hand, in the order the Azure tree should read, plus the reverse
    order for a Test Plan that places each new sibling Suite above the existing ones."""
    names = [suite["suite_name"] for suite in suites]
    lines = [
        "# Azure Test Suite order",
        "",
        "Create these static Suites under the Test Plan (or your chosen root Suite) with exactly these "
        "names. The names carry no numeric prefixes; the order comes from how they are created.",
        "",
        "## Desired display order",
        "",
        *(f"{n}. {name}" for n, name in enumerate(names, 1)),
        "",
        "## Manual creation order",
        "",
        "If Azure DevOps places each newly created sibling Suite above the existing ones, create them "
        "in this reverse order so the tree reads top to bottom as above. If new Suites are appended at "
        "the bottom instead, create them in the display order. Check after creating the first two.",
        "",
        *(f"{n}. {name}" for n, name in enumerate(reversed(names), 1)),
        "",
    ]
    return "\n".join(lines)
