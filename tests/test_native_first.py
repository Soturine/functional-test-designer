"""Native-first reading: originals are read with the host's tools; extracted text verifies or falls back.



Negative controls for the v2.6.0 reading policy. Each test that guards a pre-v2.6.0 bypass names

it: before the fix a PDF without pypdf (or without a text layer) stopped the run before any reader

saw it, images and office documents were never offered to a reader, reader results needed no

reading declaration, and a cached catalog was reused without regard to how it had been read.

"""



from __future__ import annotations



import copy

import hashlib

import importlib.util

import json

import sys

import tempfile

import unittest

from pathlib import Path

from unittest import mock



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

sys.path.insert(0, str(ROOT / "tests"))



import pipeline  # noqa: E402

import reading  # noqa: E402

import sources  # noqa: E402

from common import StageError, read_json  # noqa: E402

from native_support import drawn_pdf, mixed_pdf, text_pdf  # noqa: E402

from support import load_pack  # noqa: E402



HAS_PYPDF = importlib.util.find_spec("pypdf") is not None

COMPLETE = {"method": "native", "completeness": "COMPLETE", "inspected": ["whole file"]}

NO_PYPDF = mock.patch.dict(sys.modules, {"pypdf": None})

SUFFIX = {"pdf": "pdf", "image": "png", "text": "md", "document": "docx"}





def task(fmt: str = "pdf", snapshot: str = "TEXT_LAYER", **extra) -> dict:

    return {"source_key": "k", "path": f"docs/spec.{SUFFIX[fmt]}", "role": "FUNCTIONAL_AUTHORITY",

            "content_digest": "d", "format": fmt, "snapshot": snapshot, "declaration_required": True, **extra}





def result(declaration=None, status="INSPECTED", **extra) -> dict:

    out = {"source_key": "k", "path": "docs/spec.pdf", "content_digest": "d", "status": status,

           "reader": {"role": reading.READER_ROLE, "model": "test-double"}, **extra}

    if declaration is not None:

        out["reading"] = declaration

    return out





def errors_of(declaration, t=None, status="INSPECTED", **extra) -> list[str]:

    return reading._validate_result(result(declaration, status, **extra), t or task(), {})





class DeclarationContractTests(unittest.TestCase):

    """The declaration cannot prove the reader looked; it refuses omission and contradiction."""



    def test_an_omitted_declaration_no_longer_certifies_a_read(self) -> None:

        # Before v2.6.0 `reading` was optional and this result was accepted as a complete read.

        self.assertTrue(any("needs a reading declaration" in e for e in errors_of(None)))

        self.assertEqual([], errors_of(dict(COMPLETE)))



    def test_empty_malformed_and_unknown_declarations_are_refused(self) -> None:

        for declaration, fragment in (({}, "non-empty object"), ("native", "non-empty object"),

                                      ({**COMPLETE, "method": "guess"}, "reading.method"),

                                      ({**COMPLETE, "completeness": "MOSTLY"}, "completeness"),

                                      ({**COMPLETE, "confidence": 0.99}, "unknown fields"),

                                      ({**COMPLETE, "limitations": "none"}, "limitations must be a list"),

                                      ({**COMPLETE, "inspected": [""]}, "inspected must be a list")):

            with self.subTest(declaration=declaration):

                self.assertTrue(any(fragment in e for e in errors_of(declaration)), errors_of(declaration))



    def test_a_text_layer_reading_is_never_complete(self) -> None:

        errors = errors_of({"method": "extracted_text", "completeness": "COMPLETE", "inspected": ["text layer"],

                            "limitations": ["figures not seen"]})

        self.assertTrue(any("cannot be COMPLETE from extracted text" in e for e in errors), errors)

        errors = errors_of({"method": "extracted_text", "completeness": "PARTIAL", "inspected": ["text layer"]})

        self.assertTrue(any("text layer only" in e for e in errors), errors)

        self.assertEqual([], errors_of({"method": "extracted_text", "completeness": "PARTIAL",

                                        "inspected": ["text layer"], "limitations": ["host has no PDF reader"]}))



    def test_extracted_text_is_impossible_without_runtime_text(self) -> None:

        errors = errors_of({"method": "extracted_text", "completeness": "PARTIAL", "inspected": ["x"],

                            "limitations": ["y"]}, task("image", "NONE"))

        self.assertTrue(any("no text for this file" in e for e in errors), errors)



    def test_partial_needs_limitations_and_inspected_needs_an_account(self) -> None:

        self.assertTrue(any("PARTIAL reading must list" in e

                            for e in errors_of({"method": "native", "completeness": "PARTIAL", "inspected": ["p1"]})))

        self.assertTrue(any("INSPECTED needs reading.inspected" in e

                            for e in errors_of({"method": "native", "completeness": "COMPLETE"})))



    def test_a_declared_page_count_must_match_the_original(self) -> None:

        t = task(page_count=3)

        self.assertTrue(any("the original has 3" in e for e in errors_of({**COMPLETE, "page_count": 2}, t)))

        self.assertEqual([], errors_of({**COMPLETE, "page_count": 3}, t))



    def test_transcriptions_only_replace_missing_text_and_come_from_native_reading(self) -> None:

        self.assertTrue(any("only replaces a missing one" in e

                            for e in errors_of({**COMPLETE, "transcription": "REQ-1 x"}, task("pdf", "TEXT_LAYER"))))

        self.assertTrue(any("only replaces a missing one" in e

                            for e in errors_of({**COMPLETE, "transcription": "REQ-1 x"}, task("pdf", "TRANSCRIPTION"))))

        none = task("image", "NONE")

        self.assertEqual([], errors_of({**COMPLETE, "method": "native_vision", "transcription": "REQ-1 x"}, none))

        self.assertTrue(any("FAILED cannot carry" in e for e in errors_of(

            {**COMPLETE, "transcription": "x"}, none, status="FAILED", error="could not open")))



    def test_authority_without_runtime_text_must_be_transcribed_or_failed(self) -> None:

        required = task("pdf", "NONE", transcription_required=True)

        self.assertTrue(any("put what it says in reading.transcription" in e for e in errors_of(dict(COMPLETE), required)))

        self.assertEqual([], errors_of(None, required, status="FAILED", error="host cannot open scanned PDF"))



    def test_sequential_results_are_attributed_to_the_main_model(self) -> None:

        sequential = reading._validate_result(result(dict(COMPLETE)), task(), {}, "SEQUENTIAL")

        self.assertTrue(any("reader.role must be MAIN_MODEL" in e for e in sequential), sequential)

        main = result(dict(COMPLETE))

        main["reader"] = {"role": "MAIN_MODEL", "model": "m"}

        self.assertEqual([], reading._validate_result(main, task(), {}, "SEQUENTIAL"))

        self.assertEqual([], reading._validate_result(main, task(), {}, "MULTI_AGENT_PER_SOURCE"))



    def test_a_legacy_plan_keeps_its_optional_declaration(self) -> None:

        legacy = {k: v for k, v in task().items() if k not in {"declaration_required", "format", "snapshot"}}

        self.assertEqual([], reading._validate_result(result(None), legacy, {}))



    def test_visual_facts_need_a_native_file_a_locator_a_kind_and_a_real_page(self) -> None:

        t = task(page_count=2)

        good = {"file": "docs/spec.pdf", "locator": "page 2, approval diagram", "kind": "diagram",

                "text": "Approval requires a supervisor", "page": 2}

        ok = result(dict(COMPLETE), status="CATALOGED", catalog={"visual_facts": [good]})

        self.assertEqual([], reading._validate_result(ok, t, {}))

        for broken, fragment in (({**good, "page": 3}, "is not a page"), ({**good, "kind": "vibe"}, "kind must be"),

                                 ({**good, "locator": " "}, "non-empty locator"), ({**good, "text": ""}, "non-empty text")):

            with self.subTest(fragment=fragment):

                bad = result(dict(COMPLETE), status="CATALOGED", catalog={"visual_facts": [broken]})

                self.assertTrue(any(fragment in e for e in reading._validate_result(bad, t, {})))

        text_task = task("text", "FULL_TEXT")

        text_task["path"] = "docs/spec.pdf"

        text_task["format"] = "text"

        bad = result(dict(COMPLETE), status="CATALOGED", catalog={"visual_facts": [good]})

        self.assertTrue(any("a text file" in e for e in reading._validate_result(bad, text_task, {"docs/spec.pdf": 3})))





class Workspace(unittest.TestCase):

    def setUp(self) -> None:

        self.temp = tempfile.TemporaryDirectory()

        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.workspace, self.artifacts = self.root / "ws", self.root / "artifacts"

        self.workspace.mkdir()



    def write(self, relative: str, text: str) -> None:

        path = self.workspace / relative

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(text, encoding="utf-8")



    def start(self, selected: list[dict], run_id: str = "r", **opts) -> tuple[dict, Path, dict]:

        out = pipeline.start_run(workspace=self.workspace, sources_selected=selected, artifact_root=self.artifacts,

                                 run_id=run_id, locale="en", reading=opts or None)

        run_dir = Path(out["run_dir"])

        return out, run_dir, read_json(run_dir / "reading" / "task-plan.json")



    @staticmethod

    def tasks(plan: dict) -> dict[str, dict]:

        return {t["path"]: t for t in plan["tasks"]}



    @staticmethod

    def file_result(t: dict, declaration: dict | None = None, **over) -> dict:

        out = {"source_key": t["source_key"], "path": t["path"], "content_digest": t["content_digest"],

               "status": "INSPECTED", "reader": {"role": reading.READER_ROLE, "model": "test-double"},

               "reading": declaration or dict(COMPLETE)}

        out.update(over)

        if declaration is None and out.get("status") == "FAILED":

            out.pop("reading")

        return out





class SourceRecordTests(Workspace):

    def test_records_separate_format_snapshot_and_extraction_status(self) -> None:

        self.write("docs/spec.md", "REQ-1 The user signs in.\n")

        (self.workspace / "docs" / "flow.png").write_bytes(b"\x89PNG not opened")

        (self.workspace / "docs" / "sheet.xlsx").write_bytes(b"PK\x03\x04 not opened")

        records, _ = sources.build_source_records(self.workspace, {

            "docs/spec.md": "FUNCTIONAL_AUTHORITY", "docs/flow.png": "TECHNICAL_CONTEXT",

            "docs/sheet.xlsx": "TECHNICAL_CONTEXT"})

        by_path = {r["path"]: r for r in records}

        fields = ("format", "snapshot", "status")

        self.assertEqual(("text", "FULL_TEXT", "READ"), tuple(by_path["docs/spec.md"][k] for k in fields))

        self.assertEqual(("image", "NONE", "METADATA_ONLY"), tuple(by_path["docs/flow.png"][k] for k in fields))

        self.assertEqual(("document", "NONE", "UNSUPPORTED"), tuple(by_path["docs/sheet.xlsx"][k] for k in fields))

        self.assertIn("native vision", by_path["docs/flow.png"]["native_reading"])

        self.assertIn("report FAILED", by_path["docs/sheet.xlsx"]["native_reading"])



    @unittest.skipUnless(HAS_PYPDF, "the text-layer profile needs the optional pypdf package")

    def test_a_pdf_text_layer_is_labelled_as_a_layer_with_its_page_count(self) -> None:

        text_pdf(self.workspace / "spec.pdf", ["REQ-1 - Sign in", "The user signs in with a password."])

        records, texts = sources.build_source_records(self.workspace, {"spec.pdf": "FUNCTIONAL_AUTHORITY"})

        self.assertEqual(("TEXT_LAYER", 1), (records[0]["snapshot"], records[0]["page_count"]))

        self.assertIn("REQ-1", texts["spec.pdf"])



    def test_authority_in_a_native_format_is_no_longer_rejected_before_reading(self) -> None:

        # Before v2.6.0: ScopeError "Functional authority must be readable or transcribed before design".

        drawn_pdf(self.workspace / "scan.pdf")

        records, texts = sources.build_source_records(self.workspace, {"scan.pdf": "FUNCTIONAL_AUTHORITY"})

        self.assertEqual("NONE", records[0]["snapshot"])

        self.assertNotIn("scan.pdf", texts)

        with NO_PYPDF:

            records, _ = sources.build_source_records(self.workspace, {"scan.pdf": "FUNCTIONAL_AUTHORITY"})

        self.assertEqual(("NEEDS_TRANSCRIPTION", "NONE"), (records[0]["status"], records[0]["snapshot"]))



    def test_a_corrupted_pdf_stays_visible_as_failed_extraction(self) -> None:

        (self.workspace / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf body")

        self.write("spec.md", "REQ-1 - Sign in\n")

        records, _ = sources.build_source_records(self.workspace, {"broken.pdf": "FUNCTIONAL_AUTHORITY",

                                                                   "spec.md": "FUNCTIONAL_AUTHORITY"})

        broken = {r["path"]: r for r in records}["broken.pdf"]

        if HAS_PYPDF:

            self.assertEqual("FAILED", broken["status"])

        self.assertEqual("NONE", broken["snapshot"])



    def test_authority_no_reader_can_open_still_needs_a_transcription(self) -> None:

        (self.workspace / "notes.bin").write_bytes(b"\x00\x01")

        self.write("other.md", "REQ-1 - Sign in\n")

        records, _ = sources.build_source_records(self.workspace, {"notes.bin": "FUNCTIONAL_AUTHORITY",

                                                                   "other.md": "FUNCTIONAL_AUTHORITY"})

        self.assertEqual("UNSUPPORTED", {r["path"]: r for r in records}["notes.bin"]["status"])

        with self.assertRaises(sources.ScopeError):

            sources.build_source_records(self.workspace, {"notes.bin": "FUNCTIONAL_AUTHORITY"})





class NativeReadingRunTests(Workspace):

    def setUp(self) -> None:

        super().setUp()

        self.write("src/app.py", "def sign_in(user):\n    return user\n")

        self.selected = [{"path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY"},

                         {"path": "src", "role": "IMPLEMENTATION_EVIDENCE"}]



    @staticmethod

    def transcription() -> str:

        return "REQ-7 - Aprovação de pedido\nO supervisor aprova o pedido antes do envio.\n"



    def test_a_pdf_without_pypdf_starts_and_reaches_a_native_reader(self) -> None:

        # The PBD D3 failure, reproduced: a natively readable PDF must not need pypdf.

        text_pdf(self.workspace / "docs" / "spec.pdf", ["REQ-7 - Order approval", "A supervisor approves."])

        with NO_PYPDF:

            out, _, plan = self.start(self.selected)

        t = self.tasks(plan)["docs/spec.pdf"]

        self.assertEqual(("reading", "PLANNED", "NONE", True),

                         (out["next_stage"], t["state"], t["snapshot"], t["transcription_required"]))



    def test_a_scanned_authority_is_transcribed_by_its_native_reading_and_indexed_verbatim(self) -> None:

        drawn_pdf(self.workspace / "docs" / "spec.pdf", pages=2)

        _, run_dir, plan = self.start(self.selected)

        tasks = self.tasks(plan)

        if HAS_PYPDF:

            self.assertEqual(2, tasks["docs/spec.pdf"]["page_count"])

        native = {"method": "native_vision", "completeness": "COMPLETE", "inspected": ["page 1", "page 2"],

                  "transcription": self.transcription()}

        pipeline.submit_reading(run_dir, [self.file_result(tasks["docs/spec.pdf"], native, status="CATALOGED",

                                                           catalog={"headings": ["Aprovação"]}),

                                          self.file_result(tasks["src/app.py"])])

        pipeline.reconcile_reading(run_dir)

        state = read_json(run_dir / "sources.json")

        record = next(r for r in state["records"] if r["path"] == "docs/spec.pdf")

        self.assertEqual(("TRANSCRIBED", "NATIVE_READING", "TRANSCRIPTION"),

                         (record["status"], record["transcription_origin"], record["snapshot"]))

        self.assertEqual(hashlib.sha256(self.transcription().encode()).hexdigest(), record["transcription_digest"])

        self.assertEqual(["REQ-7"], [e["identifier"] for e in state["authority_index"]])

        self.assertEqual("Aprovação de pedido", state["authority_index"][0]["title"])

        authority = run_dir / "authority-text" / (reading.source_key("docs/spec.pdf") + ".txt")

        self.assertEqual(self.transcription(), authority.read_text(encoding="utf-8"))

        reconciled = read_json(run_dir / "stages" / "reading.reconciliation.json")

        self.assertEqual(["docs/spec.pdf"], [t["path"] for t in reconciled["native_transcriptions"]])

        self.assertEqual("native-first/1", reconciled["reading_policy"])



    def test_an_unread_authority_never_reaches_design_and_the_refusal_writes_nothing(self) -> None:

        drawn_pdf(self.workspace / "docs" / "spec.pdf")

        _, run_dir, plan = self.start(self.selected)

        tasks = self.tasks(plan)

        pipeline.submit_reading(run_dir, [self.file_result(tasks["docs/spec.pdf"], None, status="FAILED",

                                                           error="the host cannot open this scan"),

                                          self.file_result(tasks["src/app.py"])])

        before = {p.relative_to(run_dir).as_posix(): p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}

        with self.assertRaises(StageError) as caught:

            pipeline.reconcile_reading(run_dir)

        self.assertIn("functional authority with no readable text", " ".join(caught.exception.errors))

        after = {p.relative_to(run_dir).as_posix(): p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}

        self.assertEqual(before, after)

        with self.assertRaises(pipeline.IntegrityError):

            pipeline.submit_stage(run_dir, "design", {})



    def test_a_rejected_submission_leaves_the_ledger_untouched(self) -> None:

        drawn_pdf(self.workspace / "docs" / "spec.pdf")

        _, run_dir, plan = self.start(self.selected)

        tasks = self.tasks(plan)

        before = (run_dir / "reading" / "task-plan.json").read_bytes()

        forged = self.file_result(tasks["docs/spec.pdf"], dict(COMPLETE))  # claims a read, transcribes nothing

        with self.assertRaises(StageError):

            pipeline.submit_reading(run_dir, [forged, self.file_result(tasks["src/app.py"])])

        self.assertEqual(before, (run_dir / "reading" / "task-plan.json").read_bytes())

        self.assertFalse((run_dir / "reading" / "results").exists())



    def test_images_and_documents_are_offered_to_the_reader_not_dropped(self) -> None:

        # Before v2.6.0 an authority image or document was UNSUPPORTED and silently never read.

        self.write("docs/spec.md", "REQ-1 - Sign in\nThe user signs in.\n")

        (self.workspace / "docs" / "flow.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        (self.workspace / "docs" / "rules.docx").write_bytes(b"PK\x03\x04")

        (self.workspace / "docs" / "font.woff").write_bytes(b"wOFF")

        _, _, plan = self.start([{"path": "docs", "role": "FUNCTIONAL_AUTHORITY"}])

        states = {p: t["state"] for p, t in self.tasks(plan).items()}

        self.assertEqual({"docs/spec.md": "PLANNED", "docs/flow.png": "PLANNED", "docs/rules.docx": "PLANNED",

                          "docs/font.woff": "UNSUPPORTED"}, states)



    def test_a_selector_default_declaration_never_covers_a_native_file(self) -> None:

        self.write("docs/spec.md", "REQ-1 - Sign in\nThe user signs in.\n")

        (self.workspace / "docs" / "flow.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        _, run_dir, plan = self.start([{"path": "docs", "role": "TECHNICAL_CONTEXT"},

                                       {"path": "src", "role": "FUNCTIONAL_AUTHORITY"}])

        sid = next(s["selector_id"] for s in plan["selectors"] if s["path"] == "docs")

        files = [{"source_key": t["source_key"], "content_digest": t["content_digest"], "status": "INSPECTED"}

                 for t in plan["tasks"] if t["selector_id"] == sid]

        selector = {"selector_id": sid, "reader": {"role": reading.READER_ROLE, "model": "m"},

                    "reading": dict(COMPLETE), "files": files}

        with self.assertRaises(StageError) as caught:

            pipeline.submit_reading(run_dir, [selector])

        self.assertEqual(1, len(caught.exception.errors), caught.exception.errors)

        self.assertIn("docs/flow.png needs a reading declaration", caught.exception.errors[0])



    def test_sequential_runs_read_native_files_as_the_main_model(self) -> None:

        drawn_pdf(self.workspace / "docs" / "spec.pdf")

        out, run_dir, plan = self.start(self.selected, strategy="SEQUENTIAL")

        tasks = self.tasks(plan)

        self.assertEqual(("reading", "PLANNED", "MAIN_MODEL"),

                         (out["next_stage"], tasks["docs/spec.pdf"]["state"], tasks["src/app.py"]["state"]))

        order = read_json(run_dir / "work-order.json")

        self.assertEqual("MAIN_MODEL", order["reader_result_contract"]["reader"]["role"])

        native = {"method": "native_vision", "completeness": "COMPLETE", "inspected": ["page 1"],

                  "transcription": self.transcription()}

        lightweight = self.file_result(tasks["docs/spec.pdf"], native)

        with self.assertRaises(StageError):

            pipeline.submit_reading(run_dir, [lightweight])

        lightweight["reader"] = {"role": "MAIN_MODEL", "model": "main"}

        pipeline.submit_reading(run_dir, [lightweight])

        self.assertEqual("design", pipeline.reconcile_reading(run_dir)["next_stage"])



    @unittest.skipUnless(HAS_PYPDF, "the mixed text-layer profile needs pypdf")

    def test_a_visual_fact_of_authority_must_be_accounted_for_by_design(self) -> None:

        mixed_pdf(self.workspace / "docs" / "spec.pdf", ["REQ-1 - Sign in", "The user signs in with a password."])

        _, run_dir, plan = self.start(self.selected)

        tasks = self.tasks(plan)

        fact = {"file": "docs/spec.pdf", "locator": "page 2, lockout diagram", "kind": "diagram", "page": 2,

                "text": "After 3 failed sign-ins the account is locked"}

        pipeline.submit_reading(run_dir, [

            self.file_result(tasks["docs/spec.pdf"], {"method": "native", "completeness": "COMPLETE",

                                                      "inspected": ["page 1", "page 2"], "page_count": 2},

                             status="CATALOGED", catalog={"visual_facts": [fact]}),

            self.file_result(tasks["src/app.py"])])

        pipeline.reconcile_reading(run_dir)

        order = read_json(run_dir / "work-order.json")

        self.assertEqual("VF-001", order["authority_visual_facts"][0]["id"])

        design = {

            "domain_model": {"actors": ["user"], "entities": ["account"], "operations": ["sign in"]},

            "requirements": [{"key": "REQ-1", "source_identifier": "REQ-1",

                              "source_statement": "The user signs in with a password."}],

            "claims": [{"key": "C1", "requirement": "REQ-1", "text": "The user signs in with a valid password."}],

            "tests": [{"key": "T1", "claims": ["C1"], "title": "User signs in with a valid password",

                       "objective": "Verify that a user with a valid password reaches the home page.",

                       "family": "Sign in", "actor": "user", "state": "registered account",

                       "trigger": "the user submits a valid password", "expected": "The home page is shown.",

                       "failure_domain": "authentication", "primary_type": "FUNCTIONAL", "priority": "HIGH",

                       "priority_reason": "Entry point."}],

        }

        with self.assertRaises(StageError) as caught:

            pipeline.submit_stage(run_dir, "design", design)

        self.assertIn("visual fact VF-001", " ".join(caught.exception.errors))

        wrong = copy.deepcopy(design)

        wrong["requirements"].append({"key": "LOCK", "source_statement": fact["text"],

                                      "source_refs": [{"source": "src/app.py", "reference": "sign_in"}]})

        wrong["visual_fact_dispositions"] = [{"fact": "VF-001", "disposition": "REQUIREMENT", "requirements": ["LOCK"]}]

        with self.assertRaises(StageError) as caught:

            pipeline.submit_stage(run_dir, "design", wrong)

        self.assertIn("must cite docs/spec.pdf", " ".join(caught.exception.errors))

        right = copy.deepcopy(wrong)

        right["requirements"][1]["source_refs"] = [{"source": "docs/spec.pdf", "reference": "page 2, lockout diagram"}]

        right["claims"].append({"key": "C2", "requirement": "LOCK", "text": "Three failed sign-ins lock the account."})

        right["tests"].append({**design["tests"][0], "key": "T2", "claims": ["C2"],

                               "title": "Third failed sign-in locks the account",

                               "objective": "Verify that the account is locked after three failed sign-ins.",

                               "trigger": "the user submits a wrong password a third time",

                               "expected": "The account status shows locked.", "failure_domain": "lockout"})

        pipeline.submit_stage(run_dir, "design", right)

        recorded = read_json(run_dir / "stages" / "design.result.json")

        self.assertEqual("REQUIREMENT", recorded["visual_fact_dispositions"]["VF-001"]["disposition"])





@unittest.skipUnless(HAS_PYPDF, "a PDF whose text layer and visual page differ needs the text-layer profile")
class VisualIdentifierLedgerTests(Workspace):
    """An official identifier defined only inside a figure, table or scan of functional authority joins
    the normative ledger (v2.6.0). Before, it was accounted for only through its visual-fact disposition
    and never appeared in identifier_dispositions. Found by the v2.6.0 dogfood (LN-03)."""

    def setUp(self) -> None:
        super().setUp()
        mixed_pdf(self.workspace / "docs" / "spec.pdf", ["REQ-1 - Sign in", "The user signs in with a password."])
        _, self.run_dir, plan = self.start([{"path": "docs", "role": "FUNCTIONAL_AUTHORITY"}])
        tasks = self.tasks(plan)
        fact = {"file": "docs/spec.pdf", "locator": "page 2, lockout diagram", "kind": "diagram", "page": 2,
                "text": "SEC-9 - Account lockout: after 3 failed sign-ins the account is locked; REQ-1 starts the flow"}
        pipeline.submit_reading(self.run_dir, [
            self.file_result(tasks["docs/spec.pdf"], {"method": "native", "completeness": "COMPLETE",
                                                      "inspected": ["page 1", "page 2"], "page_count": 2},
                             status="CATALOGED", catalog={"visual_facts": [fact]})])
        pipeline.reconcile_reading(self.run_dir)

    def test_the_visual_identifier_is_indexed_with_its_locator_and_text_ids_are_not_duplicated(self) -> None:

        index = read_json(self.run_dir / "sources.json")["authority_index"]

        self.assertEqual(["REQ-1", "SEC-9"], [e["identifier"] for e in index])

        visual = index[1]

        self.assertEqual(("Account lockout", "docs/spec.pdf", None, "page 2, lockout diagram", "VF-001"),

                         (visual["title"], visual["source"], visual["line"], visual["locator"], visual["visual_fact"]))

        reconciled = read_json(self.run_dir / "stages" / "reading.reconciliation.json")

        self.assertEqual(["SEC-9"], [e["identifier"] for e in reconciled["visual_identifiers"]])



    def design(self, with_lockout: bool) -> dict:

        test = {"key": "T1", "claims": ["C1"], "title": "User signs in with a valid password",

                "objective": "Verify that a user with a valid password reaches the home page.", "family": "Sign in",

                "actor": "user", "state": "registered account", "trigger": "the user submits a valid password",

                "expected": "The home page is shown.", "failure_domain": "authentication", "primary_type": "FUNCTIONAL",

                "priority": "HIGH", "priority_reason": "Entry point."}

        payload = {"domain_model": {"actors": ["user"], "entities": ["account"], "operations": ["sign in"]},

                   "requirements": [{"key": "REQ-1", "source_identifier": "REQ-1", "source_statement": "The user signs in with a password."}],

                   "claims": [{"key": "C1", "requirement": "REQ-1", "text": "The user signs in with a valid password."}],

                   "tests": [test],

                   "visual_fact_dispositions": [{"fact": "VF-001", "disposition": "NOT_NORMATIVE",

                                                 "reason": "deliberately left out to prove the ledger still demands it"}]}

        if with_lockout:

            payload["requirements"].append({"key": "SEC-9", "source_identifier": "SEC-9",

                                            "source_statement": "After 3 failed sign-ins the account is locked."})

            payload["claims"].append({"key": "C2", "requirement": "SEC-9", "text": "Three failed sign-ins lock the account."})

            payload["tests"].append({**test, "key": "T2", "claims": ["C2"], "title": "Third failed sign-in locks the account",

                                     "objective": "Verify that the account is locked after three failed sign-ins.",

                                     "trigger": "the user submits a wrong password a third time",

                                     "expected": "The account status shows locked.", "failure_domain": "lockout",

                                     "primary_type": "NEGATIVE"})

            payload["visual_fact_dispositions"] = [{"fact": "VF-001", "disposition": "REQUIREMENT", "requirements": ["SEC-9"]}]

        return payload



    def test_design_cannot_leave_the_visual_identifier_unaccounted(self) -> None:

        with self.assertRaises(StageError) as caught:

            pipeline.submit_stage(self.run_dir, "design", self.design(False))

        self.assertIn("SEC-9", " ".join(caught.exception.errors))

        pipeline.submit_stage(self.run_dir, "design", self.design(True))

        ledger = {e["identifier"]: e for e in read_json(self.run_dir / "stages" / "design.result.json")["identifier_ledger"]}

        self.assertEqual("page 2, lockout diagram", ledger["SEC-9"]["locator"])

        self.assertNotIn("line", ledger["SEC-9"])

        self.assertEqual(1, ledger["REQ-1"]["line"])





class CacheCompatibilityTests(Workspace):

    def setUp(self) -> None:

        super().setUp()

        drawn_pdf(self.workspace / "docs" / "spec.pdf")

        self.write("docs/notes.md", "# Notes\nREQ-2 - Export\nThe user exports a report.\n")

        self.selected = [{"path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY"},

                         {"path": "docs/notes.md", "role": "TECHNICAL_CONTEXT"}]

        self.text = "REQ-7 - Order approval\nA supervisor approves the order.\n"



    def native(self) -> dict:

        return {"method": "native_vision", "completeness": "COMPLETE", "inspected": ["page 1"], "transcription": self.text}



    def first_run(self) -> None:

        _, run_dir, plan = self.start(self.selected, run_id="r1")

        tasks = self.tasks(plan)

        pipeline.submit_reading(run_dir, [self.file_result(tasks["docs/spec.pdf"], self.native()),

                                          self.file_result(tasks["docs/notes.md"])])

        pipeline.reconcile_reading(run_dir)



    def test_a_native_transcription_is_reused_and_reapplied_without_rereading(self) -> None:

        self.first_run()

        out, run_dir, plan = self.start(self.selected, run_id="r2")

        self.assertEqual("design", out["next_stage"])

        self.assertEqual({"REUSED"}, {t["state"] for t in plan["tasks"]})

        state = read_json(run_dir / "sources.json")

        self.assertEqual(["REQ-7"], [e["identifier"] for e in state["authority_index"]])



    def test_a_changed_role_or_revision_is_never_served_from_cache(self) -> None:

        self.first_run()

        swapped = [{"path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY"}, {"path": "docs/notes.md", "role": "TEST_ASSET"}]

        _, _, plan = self.start(swapped, run_id="r2")

        self.assertEqual("PLANNED", self.tasks(plan)["docs/notes.md"]["state"])

        drawn_pdf(self.workspace / "docs" / "spec.pdf", pages=2)

        _, _, plan = self.start(self.selected, run_id="r3")

        self.assertEqual("PLANNED", self.tasks(plan)["docs/spec.pdf"]["state"])



    def test_pre_policy_and_forged_catalogs_are_not_trusted(self) -> None:

        self.first_run()

        cache = self.artifacts / ".ftd" / "catalog-cache"

        for path in cache.glob("*.json"):

            entry = read_json(path)

            entry.pop("reading_policy")  # as written by v2.5.0

            path.write_text(json.dumps(entry), encoding="utf-8")

        _, run_dir, plan = self.start(self.selected, run_id="r2")

        tasks = self.tasks(plan)

        # The PDF's old catalog never had to see its pages: read it again. The markdown file's

        # snapshot is the whole original: reuse it, labelled as unassessed, never native-complete.

        self.assertEqual(("PLANNED", "REUSED"), (tasks["docs/spec.pdf"]["state"], tasks["docs/notes.md"]["state"]))

        self.assertTrue(tasks["docs/notes.md"]["legacy_unassessed"])

        pipeline.submit_reading(run_dir, [self.file_result(tasks["docs/spec.pdf"], self.native())])

        pipeline.reconcile_reading(run_dir)

        catalog = {e["path"]: e for e in read_json(run_dir / "reading" / "source-catalog.json")["sources"]}

        self.assertEqual(("COMPLETE", "LEGACY_UNASSESSED"),

                         (catalog["docs/spec.pdf"]["reading_status"], catalog["docs/notes.md"]["reading_status"]))

        for path in cache.glob("*.json"):

            entry = read_json(path)

            entry["reading_policy"] = reading.READING_POLICY

            entry["result"]["reading"] = {"method": "native"}  # forged: no completeness, no transcription

            path.write_text(json.dumps(entry), encoding="utf-8")

        _, _, plan = self.start(self.selected, run_id="r3")

        self.assertEqual({"PLANNED"}, {t["state"] for t in plan["tasks"]})







class UserTranscriptionCacheTests(Workspace):
    """A catalog read alongside a user-supplied transcription is reused only with that same
    transcription. Found by a v2.6.0 targeted fault injection: no test failed when the
    transcription-digest check was removed."""

    def run_with(self, run_id: str, text: str) -> dict:
        transcript = self.root / f"{run_id}.txt"
        transcript.write_text(text, encoding="utf-8")
        out = pipeline.start_run(workspace=self.workspace, artifact_root=self.artifacts, run_id=run_id, locale="en",
                                 sources_selected=[{"path": "scan.pdf", "role": "FUNCTIONAL_AUTHORITY"}],
                                 transcriptions={"scan.pdf": transcript})
        run_dir = Path(out["run_dir"])
        plan = read_json(run_dir / "reading" / "task-plan.json")
        task = plan["tasks"][0]
        if task["state"] == "PLANNED":
            pipeline.submit_reading(run_dir, [self.file_result(task, {"method": "native_vision", "completeness": "COMPLETE",
                                                                      "inspected": ["page 1"]})])
            pipeline.reconcile_reading(run_dir)
        return task

    def test_a_changed_user_transcription_is_read_again(self) -> None:
        drawn_pdf(self.workspace / "scan.pdf")
        first = "REQ-7 - Order approval\nA supervisor approves the order.\n"
        self.assertEqual("PLANNED", self.run_with("r1", first)["state"])
        self.assertEqual("REUSED", self.run_with("r2", first)["state"])
        self.assertEqual("PLANNED", self.run_with("r3", first + "REQ-8 - Order rejection\nA supervisor rejects it.\n")["state"])


class EndToEndNativeAuthorityTests(unittest.TestCase):

    """A real pack, its authority replaced by a PDF with no text layer, through the whole pipeline."""



    def setUp(self) -> None:

        self.temp = tempfile.TemporaryDirectory()

        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)

        pack = load_pack("saas-accounts")

        self.authority_text = pack["sources"]["docs/requirements.md"]["text"]

        self.stages = json.loads(json.dumps(pack["stages"]).replace("docs/requirements.md", "docs/requirements.pdf"))

        self.workspace, self.artifacts = root / "ws", root / "artifacts"

        for relative, source in pack["sources"].items():

            if relative == "docs/requirements.md":

                drawn_pdf(self.workspace / "docs" / "requirements.pdf", pages=2)

                continue

            (self.workspace / relative).parent.mkdir(parents=True, exist_ok=True)

            (self.workspace / relative).write_text(source["text"], encoding="utf-8")

        self.selected = [{"path": "docs/requirements.pdf", "role": "FUNCTIONAL_AUTHORITY"},

                         {"path": "src/invitations.py", "role": "IMPLEMENTATION_EVIDENCE"},

                         {"path": "tests/test_invitations.py", "role": "TEST_ASSET"}]

        self.locale = pack["locale"]



    def run_pipeline(self, completeness: str = "COMPLETE") -> dict:

        out = pipeline.start_run(workspace=self.workspace, sources_selected=self.selected, artifact_root=self.artifacts,

                                 run_id="native", locale=self.locale)

        run_dir = Path(out["run_dir"])

        plan = read_json(run_dir / "reading" / "task-plan.json")

        results = []

        for t in plan["tasks"]:

            declaration = dict(COMPLETE)

            if t["path"].endswith(".pdf"):

                declaration = {"method": "native_vision", "completeness": completeness,

                               "inspected": ["page 1", "page 2"], "transcription": self.authority_text, "page_count": 2}

                if completeness == "PARTIAL":

                    declaration["limitations"] = ["page 2 footnote is illegible <script>alert(1)</script>"]

            results.append({"source_key": t["source_key"], "path": t["path"], "content_digest": t["content_digest"],

                            "status": "INSPECTED", "reader": {"role": reading.READER_ROLE, "model": "test-double"},

                            "reading": declaration})

        pipeline.submit_reading(run_dir, results)

        pipeline.reconcile_reading(run_dir)

        for stage in ("design", "expansion", "procedures"):

            pipeline.submit_stage(run_dir, stage, self.stages[stage])

        pipeline.finalize_run(run_dir)

        pipeline.verify_manifest(run_dir / "run-manifest.json")

        return read_json(run_dir / "canonical-suite.json")



    def test_a_scanned_authority_yields_the_coverage_of_its_text(self) -> None:

        canonical = self.run_pipeline()

        source = next(s for s in canonical["index"]["sources"] if s["path"] == "docs/requirements.pdf")

        self.assertEqual(("TRANSCRIBED", "COMPLETE", "native_vision"),

                         (source["status"], source["reading"]["status"], source["reading"]["method"]))

        identifiers = {e["identifier"] for e in canonical["index"]["identifier_dispositions"]}

        self.assertTrue({"FR-01", "FR-02", "BR-01"} <= identifiers, identifiers)

        self.assertNotIn("partially_read_authority_sources", canonical["index"]["gap_metrics"])

        self.assertEqual("native-first/1", canonical["diagnostics"]["source_reading"]["reading_policy"])

        html = (self.artifacts / "output" / "report.html").read_text(encoding="utf-8")

        self.assertIn("Source reading", html)

        self.assertIn("native_vision", html)



    def test_a_partially_read_authority_is_a_visible_gap_not_a_complete_claim(self) -> None:

        canonical = self.run_pipeline("PARTIAL")

        self.assertEqual(1, canonical["index"]["gap_metrics"]["partially_read_authority_sources"])

        self.assertTrue(any(w.startswith("AUTHORITY_PARTIALLY_READ: docs/requirements.pdf")

                            for w in canonical["diagnostics"]["warnings"]))

        from validation import gap_summary

        self.assertNotEqual("0 gaps", gap_summary(canonical["index"]["gap_metrics"]))

        html = (self.artifacts / "output" / "report.html").read_text(encoding="utf-8")

        self.assertIn("illegible &lt;script&gt;alert(1)&lt;/script&gt;", html)

        self.assertNotIn("<script>alert(1)", html)





if __name__ == "__main__":

    unittest.main()

