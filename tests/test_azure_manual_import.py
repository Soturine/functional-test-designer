"""Manual Azure DevOps import: natural Suite order, the Suite creation guide and local CSV files.
Nothing here contacts Azure."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export as az  # noqa: E402
import challenge as ch  # noqa: E402
import workflow  # noqa: E402
from integrations import azure_manual_import as mi  # noqa: E402
from integrations.azure_devops import read_ftd_metadata  # noqa: E402
from support import PackRun  # noqa: E402

AREA = "Project\\Area"
OPTIONS = {"area_path": AREA, "fresh_target": True}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def ftd_key(row: dict) -> str:
    return next(t for t in row["Tags"].split("; ") if t.startswith("ftd-key:"))[len("ftd-key:"):]


def finalized_run(test: unittest.TestCase) -> PackRun:
    """A synthetic pack run plus one chaos case related to a canonical case (so it has several suites)."""
    run = PackRun("saas-accounts")
    test.addCleanup(run.close)
    run.finalize()
    related = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")["cases"][0]["id"]
    ch.start_challenge(run.run_dir, "field", seeds=[])
    ch.submit_challenge(run.run_dir, "field", {"cases": [{
        "key": "H1", "title": "Two owners invite the last seat at once", "discovery": "MODEL_DERIVED",
        "rationale": "Racing invitations could exceed the seat limit.", "execution_tags": ["EXPLORATORY"],
        "related_test_cases": [related]}], "seed_dispositions": []})
    ch.finalize_challenge(run.run_dir, "field")
    return run


def convert(run: PackRun, **manual) -> dict:
    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
            mock.patch("socket.socket", side_effect=AssertionError("network")):
        return az.convert_run(run.run_dir, manual_import={**OPTIONS, **manual})


def suite(name: str, kind: str, identifier: str | None = None, refs: list[str] | None = None) -> dict:
    return {"suite_name": name, "group": identifier or name, "kind": kind, "identifier": identifier,
            "test_case_refs": refs or [f"canonical:{name}-case"]}


class SuiteOrderTests(unittest.TestCase):
    def test_identifiers_order_naturally_for_any_scheme(self) -> None:
        ordered = sorted(["RF10", "RF2", "RF1", "REQ-10", "REQ-2", "UC003", "UC10"], key=az.natural_key)
        self.assertEqual(["REQ-2", "REQ-10", "RF1", "RF2", "RF10", "UC003", "UC10"], ordered)

    def test_requirements_then_use_cases_then_transversal_then_execution_views(self) -> None:
        suites = [
            suite("Load and concurrency", "EXECUTION_VIEW"), suite("End-to-end", "EXECUTION_VIEW"),
            suite("Transversal rules", "TRANSVERSAL"), suite("UC10 — Close", "USE_CASE", "UC10"),
            suite("UC2 — Open", "USE_CASE", "UC2"), suite("RF10 — Export", "FUNCTIONAL", "RF10"),
            suite("RF2 — Edit", "FUNCTIONAL", "RF2"), suite("RF1 — Create", "FUNCTIONAL", "RF1"),
            {**suite("Unassigned", "UNASSIGNED"), "group": None},
        ]
        ordered = az._display_ordered(suites)
        self.assertEqual(["RF1 — Create", "RF2 — Edit", "RF10 — Export", "UC2 — Open", "UC10 — Close",
                          "Transversal rules", "Load and concurrency", "End-to-end", "Unassigned"],
                         [s["suite_name"] for s in ordered])
        self.assertEqual({id(s) for s in suites}, {id(s) for s in ordered})  # same suites, members untouched

    def test_member_order_inside_a_suite_is_kept(self) -> None:
        refs = ["canonical:TC-009", "canonical:TC-002", "chaos:x:CH-001"]
        self.assertEqual(refs, az._display_ordered([suite("RF1", "FUNCTIONAL", "RF1", refs)])[0]["test_case_refs"])

    def test_the_guide_lists_the_display_order_and_its_reverse_with_clean_names(self) -> None:
        text = mi.suite_order_markdown([suite("RF1 — Create", "FUNCTIONAL", "RF1"), suite("RF2 — Edit", "FUNCTIONAL", "RF2"),
                                        suite("End-to-end", "EXECUTION_VIEW")])
        display, creation = text.split("## Manual creation order")
        self.assertIn("1. RF1 — Create\n2. RF2 — Edit\n3. End-to-end", display)
        self.assertIn("1. End-to-end\n2. RF2 — Edit\n3. RF1 — Create", creation)
        self.assertNotIn("01 -", text)


class FreshTargetCreateTests(unittest.TestCase):
    """--fresh-target: blank-ID CSV rows, each Test Case created exactly once, in its primary Suite."""

    def test_without_a_target_assumption_nothing_is_generated(self) -> None:
        run = finalized_run(self)
        with self.assertRaisesRegex(mi.ManualImportError, "--fresh-target .*--existing-azure-export"):
            convert(run, fresh_target=False)
        with self.assertRaisesRegex(mi.ManualImportError, "--area-path is required"):
            convert(run, area_path="  ")
        self.assertFalse((run.artifacts / "output" / "azure" / "manual-import").exists())

    def test_every_case_is_created_once_with_a_blank_id_in_its_primary_suite(self) -> None:
        run = finalized_run(self)
        folder = Path(convert(run)["manual_import"]["manual_import_dir"])
        package = json.loads((run.artifacts / "output" / "azure" / "azure-export-package.json").read_text(encoding="utf-8"))
        files = sorted((folder / mi.CREATE_DIR).glob("*.csv"))
        self.assertTrue(files)
        self.assertFalse((folder / mi.UPDATE_FILE).exists())
        created: dict[str, str] = {}
        for path in files:
            rows = read_csv(path)
            self.assertEqual(list(mi.COLUMNS), list(rows[0]))
            order: list[str] = []
            for row in rows:
                self.assertEqual(("", "Test Case", AREA, "", "Design"),
                                 (row["ID"], row["Work Item Type"], row["Area Path"], row["Assigned To"], row["State"]))
                key = ftd_key(row)
                if not order or order[-1] != key:
                    self.assertNotIn(key, created, "a Test Case is created in exactly one file, its rows contiguous")
                    order.append(key)
                    created[key] = path.name
            for key in order:
                self.assertEqual([str(n) for n in range(1, sum(ftd_key(r) == key for r in rows) + 1)],
                                 [r["Test Step"] for r in rows if ftd_key(r) == key])
            # the rows follow one suite's own member order
            self.assertTrue(any([k for k in s["test_case_refs"] if k in order] == order for s in package["suites"]))
        self.assertEqual({c["export_key"] for c in package["test_cases"]}, set(created))
        plan = json.loads((folder / "manual-import-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(("CREATE", "EMPTY", "NONE"), (plan["mode"], plan["target_assumption"], plan["existing_ids"]))
        self.assertIn("safe only for an empty/new target", plan["duplicate_safety"])
        self.assertEqual(len(created), plan["summary"]["create"])
        summary = (folder / "manual-import-summary.md").read_text(encoding="utf-8")
        for line in ("MODE: CREATE", "TARGET ASSUMPTION: EMPTY", "EXISTING IDS: NONE",
                     f"| Total FTD Test Cases | {len(created)} |", "| UNMATCHED | 0 |", "Blank ID = new Test Case."):
            self.assertIn(line, summary)
        self.assertIn("## Manual creation order", (folder / "suite-order.md").read_text(encoding="utf-8"))

    def test_a_case_in_several_suites_is_created_once_and_listed_for_secondary_placement(self) -> None:
        run = finalized_run(self)
        folder = Path(convert(run)["manual_import"]["manual_import_dir"])
        secondary = read_csv(folder / mi.SECONDARY_FILE)
        self.assertTrue(secondary)
        files = list((folder / mi.CREATE_DIR).glob("*.csv"))
        for placement in secondary:
            holding = [p.name for p in files if any(ftd_key(r) == placement["FTD Key"] for r in read_csv(p))]
            self.assertEqual(1, len(holding))
            self.assertNotEqual(placement["Primary Suite"], placement["Additional Suite"])
            self.assertEqual("", placement["Azure ID"])
            self.assertIn(placement["FTD ID"], placement["Title"])

    def test_titles_tags_and_description_carry_the_review_state_and_metadata(self) -> None:
        run = finalized_run(self)
        folder = Path(convert(run, assigned_to="tester@example.com", state="Ready")["manual_import"]["manual_import_dir"])
        rows = [r for path in (folder / mi.CREATE_DIR).glob("*.csv") for r in read_csv(path)]
        chaos = next(r for r in rows if ftd_key(r) == "chaos:field:CH-001")
        self.assertTrue(chaos["Title"].startswith("[EXPLORATORY] CH-001 — "))
        self.assertIn("FTD_STATUS:EXPLORATORY", chaos["Tags"].split("; "))
        self.assertIn("<h3>FTD execution status</h3>", chaos["Description"])
        self.assertEqual("chaos:field:CH-001", read_ftd_metadata(chaos["Description"])["export_key"])
        self.assertEqual({("tester@example.com", "Ready")}, {(r["Assigned To"], r["State"]) for r in rows})
        exploratory = next(r for r in rows if "FTD_STATUS:EXPLORATORY" in r["Tags"] and ftd_key(r).startswith("canonical:"))
        self.assertTrue(exploratory["Title"].startswith("[EXPLORATORY] TC-"))
        ready = next(r for r in rows if "FTD_STATUS:READY" in r["Tags"].split("; "))
        self.assertRegex(ready["Title"], r"^TC-\d{3} — ")

    def test_multi_line_steps_survive_csv_quoting(self) -> None:
        case = {"export_key": "canonical:TC-001", "local_id": "TC-001", "title": 'A, quoted "title"', "priority": "HIGH",
                "status": "READY", "steps": [{"action": "Line one\nLine two, with comma", "expected_result": 'Shown "OK"'}]}
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "x.csv"
        mi._write_csv(path, mi.COLUMNS, mi.case_rows(case, None, mi.import_options(area_path=AREA)))
        back = read_csv(path)[0]
        self.assertEqual(("Line one\nLine two, with comma", 'Shown "OK"', 'TC-001 — A, quoted "title"'),
                         (back["Step Action"], back["Step Expected"], back["Title"]))

    def test_a_new_generation_removes_its_stale_files_and_keeps_the_users_files(self) -> None:
        run = finalized_run(self)
        folder = Path(convert(run)["manual_import"]["manual_import_dir"])
        stale = folder / mi.CREATE_DIR / "99-old-suite.csv"
        stale.write_text("ID\n", encoding="utf-8")
        mine = folder / "azure-current.csv"
        mine.write_text("ID\n", encoding="utf-8")
        convert(run)
        self.assertFalse(stale.exists())
        self.assertTrue(mine.exists())

    def test_the_command_line_requires_an_explicit_target_assumption(self) -> None:
        run = finalized_run(self)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = workflow.main(["azure", "--run", str(run.run_dir), "--manual-import", "--area-path", AREA])
        self.assertEqual(1, code)
        self.assertIn("--fresh-target", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, workflow.main(["azure", "--run", str(run.run_dir), "--manual-import", "--fresh-target",
                                               "--area-path", AREA]))
        self.assertTrue((run.artifacts / "output" / "azure" / "manual-import" / "manual-import-plan.json").is_file())


def azure_export_of(created_rows: list[dict], *, start: int = 1000, older_format: bool = False,
                    columns: tuple = mi.COLUMNS) -> tuple[str, dict[str, str]]:
    """What Azure would export after importing `created_rows`: each Test Case got an ID. With
    `older_format`, continuation rows leave the ID blank."""
    ids: dict[str, str] = {}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in created_rows:
        key = ftd_key(row)
        first = key not in ids
        ids.setdefault(key, str(start + len(ids)))
        writer.writerow({**row, "ID": ids[key] if first or not older_format else ""})
    return out.getvalue(), ids


class ExistingTargetUpdateTests(unittest.TestCase):
    """--existing-azure-export: stable FTD identity decides UPDATE/UNCHANGED/CONFLICT/UNMATCHED; a
    case is never matched by title and never silently created."""

    def setUp(self) -> None:
        self.run = finalized_run(self)
        self.folder = Path(convert(self.run)["manual_import"]["manual_import_dir"])
        self.created = [r for p in sorted((self.folder / mi.CREATE_DIR).glob("*.csv")) for r in read_csv(p)]
        self.export = self.folder / "azure-current.csv"

    def reconcile(self, text: str, **manual) -> dict:
        self.export.write_text(text, encoding="utf-8")
        convert(self.run, fresh_target=False, existing_azure_export=str(self.export), **manual)
        return json.loads((self.folder / "manual-import-plan.json").read_text(encoding="utf-8"))

    def test_an_unchanged_import_is_unchanged_and_writes_no_create_or_update_rows(self) -> None:
        text, ids = azure_export_of(self.created)
        plan = self.reconcile(text)
        self.assertEqual(len(ids), plan["summary"]["unchanged"])
        self.assertEqual(0, plan["summary"]["create"] + plan["summary"]["update"])
        self.assertFalse(list((self.folder / mi.CREATE_DIR).glob("*.csv")))
        self.assertFalse((self.folder / mi.UPDATE_FILE).exists())
        self.assertEqual(("UPDATE", "EXISTING"), (plan["mode"], plan["target_assumption"]))
        self.assertTrue(self.export.exists())  # the user's export is never removed
        placements = read_csv(self.folder / mi.SECONDARY_FILE)
        self.assertTrue(all(p["Azure ID"] == ids[p["FTD Key"]] for p in placements))

    def test_a_changed_case_updates_with_its_existing_id_and_never_a_blank_one(self) -> None:
        changed = [{**r, "Description": "edited in Azure"} if ftd_key(r) == "chaos:field:CH-001" else r for r in self.created]
        text, ids = azure_export_of(changed, older_format=True)
        plan = self.reconcile(text)
        self.assertEqual(1, plan["summary"]["update"])
        rows = read_csv(self.folder / mi.UPDATE_FILE)
        self.assertEqual({ids["chaos:field:CH-001"]}, {r["ID"] for r in rows})
        self.assertTrue(all(r["ID"] for r in rows))
        self.assertTrue(rows[0]["Title"].startswith("[EXPLORATORY] CH-001"))
        self.assertFalse(list((self.folder / mi.CREATE_DIR).glob("*.csv")))

    def test_a_second_generation_from_the_same_export_is_identical_and_creates_nothing(self) -> None:
        text, _ = azure_export_of(self.created)
        first = self.reconcile(text)
        second = self.reconcile(text)
        self.assertEqual(first["cases"], second["cases"])
        self.assertEqual(0, second["summary"]["create"])

    def test_a_title_look_alike_without_ftd_identity_is_never_matched_or_created(self) -> None:
        target = self.created[0]
        others = [r for r in self.created if ftd_key(r) != ftd_key(target)]
        text, _ = azure_export_of(others)
        look_alike = {**target, "ID": "77", "Tags": "imported-by-hand", "Description": "written by hand"}
        writer_out = io.StringIO()
        csv.DictWriter(writer_out, fieldnames=mi.COLUMNS, lineterminator="\r\n").writerow(look_alike)
        plan = self.reconcile(text + writer_out.getvalue())
        entry = next(e for e in plan["cases"] if e["export_key"] == ftd_key(target))
        self.assertEqual(("UNMATCHED", None), (entry["action"], entry["azure_id"]))
        self.assertIn("['77'] share the title but carry no FTD identity", entry["reason"])
        self.assertFalse(list((self.folder / mi.CREATE_DIR).glob("*.csv")))
        self.assertIn("| UNMATCHED | 1 |", (self.folder / "manual-import-summary.md").read_text(encoding="utf-8"))

    def test_a_duplicated_ftd_key_in_azure_is_a_conflict_with_no_importable_row(self) -> None:
        target = ftd_key(self.created[0])
        text, _ = azure_export_of(self.created)
        twin, _ = azure_export_of([r for r in self.created if ftd_key(r) == target], start=9000)
        plan = self.reconcile(text + twin.split("\r\n", 1)[1])
        entry = next(e for e in plan["cases"] if e["export_key"] == target)
        self.assertEqual("CONFLICT", entry["action"])
        self.assertIn("DUPLICATE_FTD_KEY", entry["reason"])
        self.assertEqual(2, len(entry["candidates"]))
        for path in [self.folder / mi.UPDATE_FILE, *(self.folder / mi.CREATE_DIR).glob("*.csv")]:
            if path.exists():
                self.assertFalse([r for r in read_csv(path) if ftd_key(r) == target])

    def test_unmatched_cases_are_created_only_when_explicitly_allowed(self) -> None:
        missing = "chaos:field:CH-001"
        text, _ = azure_export_of([r for r in self.created if ftd_key(r) != missing])
        self.assertEqual("UNMATCHED", next(e for e in self.reconcile(text)["cases"] if e["export_key"] == missing)["action"])
        self.assertFalse(list((self.folder / mi.CREATE_DIR).glob("*.csv")))
        plan = self.reconcile(text, allow_create=True)
        self.assertEqual("UPDATE+CREATE", plan["mode"])
        self.assertEqual("CREATE", next(e for e in plan["cases"] if e["export_key"] == missing)["action"])
        create_rows = [r for p in (self.folder / mi.CREATE_DIR).glob("*.csv") for r in read_csv(p)]
        self.assertEqual({missing}, {ftd_key(r) for r in create_rows})
        self.assertEqual({""}, {r["ID"] for r in create_rows})
        self.assertEqual(len(plan["cases"]) - 1, plan["summary"]["unchanged"])

    def test_identity_is_recovered_from_the_metadata_block_when_tags_lack_the_key(self) -> None:
        without_key = [{**r, "Tags": "; ".join(t for t in r["Tags"].split("; ") if not t.startswith("ftd-key:"))}
                       for r in self.created]
        text, _ = azure_export_of(self.created)
        rows = list(csv.DictReader(io.StringIO(text)))
        for row, stripped in zip(rows, without_key):
            row["Tags"] = stripped["Tags"]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=mi.COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
        plan = self.reconcile(out.getvalue())
        self.assertEqual(0, plan["summary"]["unmatched"] + plan["summary"]["conflict"])
        self.assertTrue(all(e["azure_id"] for e in plan["cases"]))

    def test_an_export_without_tags_or_description_is_refused_instead_of_matching_titles(self) -> None:
        text, _ = azure_export_of(self.created, columns=mi.COLUMNS[:9])
        self.export.write_text(text, encoding="utf-8")
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(mi.ManualImportError, "Column options"):
            convert(self.run, fresh_target=False, existing_azure_export=str(self.export))
        self.assertEqual(before, {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()})

    def test_an_xlsx_export_is_read_without_extra_dependencies(self) -> None:
        import zipfile
        from xml.sax.saxutils import escape
        text, ids = azure_export_of(self.created)
        table = list(csv.reader(io.StringIO(text)))
        cells = "".join(
            "<row>" + "".join(f'<c t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>' for v in line) + "</row>"
            for line in table)
        path = self.folder / "azure-current.xlsx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml",
                             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                             f"<sheetData>{cells}</sheetData></worksheet>")
        items = mi.read_azure_export(path)
        self.assertEqual(sorted(ids.values()), sorted(i["id"] for i in items))
        self.assertEqual({k for i in items for k in i["keys"]}, set(ids))

    def test_contradictory_or_incomplete_modes_are_refused(self) -> None:
        text, _ = azure_export_of(self.created)
        self.export.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(mi.ManualImportError, "exclude each other"):
            convert(self.run, existing_azure_export=str(self.export))
        with self.assertRaisesRegex(mi.ManualImportError, "--allow-create only applies"):
            convert(self.run, allow_create=True)


if __name__ == "__main__":
    unittest.main()
