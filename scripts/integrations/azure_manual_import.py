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


def build_plan(
    package: dict[str, Any], options: dict[str, str], *, fresh_target: bool = False,
    existing: list[dict[str, Any]] | None = None, existing_source: str | None = None, allow_create: bool = False,
) -> dict[str, Any]:
    """CREATE for a declared empty target; otherwise reconcile every case with the existing Azure
    Test Cases by stable FTD identity. A case without exactly one stable match is never created
    silently: it is CONFLICT, or UNMATCHED unless creation is explicitly allowed."""
    if fresh_target and existing is not None:
        raise ManualImportError("--fresh-target and --existing-azure-export exclude each other")
    if allow_create and existing is None:
        raise ManualImportError("--allow-create only applies with --existing-azure-export")
    if not fresh_target and existing is None:
        raise ManualImportError(
            "say what the Azure target holds: --fresh-target for a new, empty target (every case is created), "
            "or --existing-azure-export <file> to update a previously imported set without duplicates")
    primary, additional = suite_homes(package)
    by_key: dict[str, list[dict[str, Any]]] = {}
    by_title: dict[str, list[str]] = {}
    for item in existing or []:
        for key in item["keys"]:
            by_key.setdefault(key, []).append(item)
        if not item["keys"]:
            by_title.setdefault(item["title"], []).append(item["id"])
    entries = []
    for case in package["test_cases"]:
        key = case["export_key"]
        rows = case_rows(case, None, options)
        entry = {"export_key": key, "ftd_id": case["local_id"], "title": rows[0]["Title"], "status": case["status"],
                 "action": "CREATE", "azure_id": None, "primary_suite": primary.get(key),
                 "additional_suites": additional.get(key, [])}
        matches = by_key.get(key, [])
        if existing is None:
            pass
        elif len(matches) > 1:
            entry.update(action="CONFLICT", reason="DUPLICATE_FTD_KEY: several Azure Test Cases carry this FTD key",
                         candidates=sorted(m["id"] for m in matches))
        elif matches and len(matches[0]["keys"]) > 1:
            entry.update(action="CONFLICT", reason="AMBIGUOUS_FTD_IDENTITY: the Azure Test Case carries several FTD keys",
                         candidates=[matches[0]["id"]])
        elif matches:
            entry.update(action="UNCHANGED" if _same_content(matches[0], rows) else "UPDATE", azure_id=matches[0]["id"])
        else:
            look_alikes = by_title.get(entry["title"], []) + by_title.get(case["title"], [])
            reason = "NO_STABLE_MATCH" + (f": Azure Test Cases {sorted(set(look_alikes))} share the title but carry no "
                                          "FTD identity" if look_alikes else "")
            entry.update(action="CREATE" if allow_create else "UNMATCHED", reason=reason)
        entries.append(entry)
    known = {c["export_key"] for c in package["test_cases"]}
    if existing is None:
        header = {"mode": "CREATE", "target_assumption": "EMPTY", "existing_ids": "NONE",
                  "duplicate_safety": "safe only for an empty/new target: every row group has a blank ID and creates a Test Case"}
    else:
        matched = sum(e["action"] in {"UPDATE", "UNCHANGED"} for e in entries)
        header = {
            "mode": "UPDATE+CREATE" if allow_create else "UPDATE", "target_assumption": "EXISTING",
            "existing_ids": f"{matched} matched by ftd-key / FTD_METADATA_V1 in {existing_source or 'the Azure export'}",
            "duplicate_safety": "update rows carry the existing Azure ID; " + (
                "cases without a stable match are created with a blank ID because --allow-create was given"
                if allow_create else "cases without a stable match are UNMATCHED and never created"),
            "not_in_package": sorted({k for item in existing for k in item["keys"] if k not in known}),
        }
    return {"schema_version": "1", "operation": "AZURE_MANUAL_IMPORT_PLAN", "source_run": package["source_run"],
            **header, "options": options, "summary": _summary(entries), "cases": entries}


def _same_content(item: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    """UNCHANGED only when the export shows every compared field and each one already matches."""
    if item["tags"] is None or item["description"] is None:
        return False
    return (item["title"] == rows[0]["Title"] and set(item["tags"]) == set(rows[0]["Tags"].split("; "))
            and item["description"] == rows[0]["Description"]
            and item["steps"] == [(r["Step Action"], r["Step Expected"]) for r in rows if r["Step Action"] or r["Step Expected"]])


# --- reading the user's Azure export (CSV or XLSX, obtained from Azure DevOps by hand) -------

def read_azure_export(path: Path, normalize_key: Any = None) -> list[dict[str, Any]]:
    """Existing Test Cases from an Azure export: one record per work item ID with its FTD keys
    (`ftd-key:` tags first, else the FTD_METADATA_V1 export key). Title is kept for reporting
    look-alikes only; it is never identity."""
    from integrations.azure_devops import read_ftd_metadata
    path = Path(path)
    if not path.is_file():
        raise ManualImportError(f"the Azure export {path} does not exist")
    rows = _xlsx_rows(path) if path.suffix.casefold() == ".xlsx" else _csv_rows(path)
    columns = {name.strip().casefold() for row in rows[:1] for name in row}
    if "id" not in columns:
        raise ManualImportError(f"{path.name} has no ID column; export the Test Cases from Azure DevOps Test Plans")
    if not columns & {"tags", "description"}:
        raise ManualImportError(
            f"{path.name} has neither a Tags nor a Description column, so no FTD identity can be read. In Azure "
            "Test Plans use Column options to add Tags (and Description), export again and retry. FTD never "
            "matches Test Cases by title.")
    normalize_key = normalize_key or (lambda key: key)
    items: dict[str, dict[str, Any]] = {}
    current = None
    for raw in rows:
        row = {name.strip().casefold(): (value or "") for name, value in raw.items() if name}
        work_item = row.get("id", "").strip().removesuffix(".0")
        if work_item:
            current = items.setdefault(work_item, {"id": work_item, "title": row.get("title", "").strip(),
                                                   "tags": None, "description": None, "steps": [], "keys": []})
        if current is None:
            continue
        if "tags" in row and row["tags"].strip():
            current["tags"] = [t.strip() for t in row["tags"].split(";") if t.strip()]
        elif "tags" in row and current["tags"] is None:
            current["tags"] = []
        if "description" in row and row["description"].strip():
            current["description"] = row["description"]
        if row.get("step action", "").strip() or row.get("step expected", "").strip():
            current["steps"].append((row.get("step action", ""), row.get("step expected", "")))
    for item in items.values():
        keys = [t[len("ftd-key:"):] for t in item["tags"] or [] if t.casefold().startswith("ftd-key:")]
        if not keys and item["description"]:
            try:
                metadata = read_ftd_metadata(item["description"])
            except ValueError:
                metadata = None
            if metadata and metadata.get("export_key"):
                keys = [metadata["export_key"]]
        item["keys"] = sorted({normalize_key(k.strip()) for k in keys if k.strip()})
    return list(items.values())


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    """The first worksheet of an XLSX as header-keyed rows, read with the standard library only."""
    import posixpath
    import zipfile
    from xml.etree import ElementTree
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ManualImportError(f"{path.name} is not a valid XLSX file") from exc
    with archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = ["".join(t.text or "" for t in si.iter(f"{main}t"))
                      for si in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).iter(f"{main}si")]
        sheet = "xl/worksheets/sheet1.xml"
        if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
            first = next(ElementTree.fromstring(archive.read("xl/workbook.xml")).iter(f"{main}sheet"), None)
            targets = {r.get("Id"): r.get("Target") for r in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
            target = targets.get(first.get(f"{rel}id")) if first is not None else None
            if target:
                sheet = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        table = []
        for row in ElementTree.fromstring(archive.read(sheet)).iter(f"{main}row"):
            values: dict[int, str] = {}
            for cell in row.iter(f"{main}c"):
                letters = re.match(r"[A-Z]+", cell.get("r", "")).group(0) if cell.get("r") else None
                column = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(letters))) - 1 if letters else len(values)
                kind, value = cell.get("t"), cell.find(f"{main}v")
                if kind == "s" and value is not None:
                    values[column] = shared[int(value.text)]
                elif kind == "inlineStr":
                    values[column] = "".join(t.text or "" for t in cell.iter(f"{main}t"))
                else:
                    values[column] = value.text if value is not None and value.text else ""
            table.append([values.get(i, "") for i in range(max(values) + 1)] if values else [])
    if not table:
        return []
    header = table[0]
    return [dict(zip(header, line + [""] * (len(header) - len(line)))) for line in table[1:]]


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
        f"`{UPDATE_FILE}` rows carry existing Azure IDs: importing it updates those Test Cases (Azure replaces "
        "their steps) and creates none.",
        "",
    ]
    held = [e for e in plan["cases"] if e["action"] in {"CONFLICT", "UNMATCHED"}]
    if held:
        lines += ["## Not imported", "", "| FTD ID | Action | Reason |", "| --- | --- | --- |",
                  *(f"| {e['ftd_id']} | {e['action']} | {e.get('reason', '')} |" for e in held), ""]
    if plan.get("not_in_package"):
        lines += ["## In Azure but not in this package (left untouched)", "",
                  *(f"- `{key}`" for key in plan["not_in_package"]), ""]
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
