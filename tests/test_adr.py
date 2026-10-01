"""FTD ADR: incremental maintenance of a validated suite from a change corpus. Synthetic data only;
nothing here reruns a benchmark, calls a model or contacts Azure."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adr_support as fx  # noqa: E402
import adr  # noqa: E402
import pipeline  # noqa: E402
import workflow  # noqa: E402
from common import StageError, stable_digest  # noqa: E402


def no_network():
    return mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
        mock.patch("socket.socket", side_effect=AssertionError("network"))


class AdrTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.run = fx.AdrRun()
        self.addCleanup(self.run.close)
        fx.write_corpus(self.run.corpus)
        self.run_dir = self.run.run_dir
        self.canonical = pipeline.read_canonical(self.run_dir / "canonical-suite.json")

    def start(self, **kwargs):
        return adr.start_adr(self.run_dir, self.run.corpus, **kwargs)

    def rejected(self, payload, stage="analysis", **start) -> str:
        adr_id = self.start(**start)["adr_run_id"]
        if stage == "procedures":
            adr.submit_analysis(self.run_dir, adr_id, fx.analysis())
            submit = adr.submit_procedures
        else:
            submit = adr.submit_analysis
        with self.assertRaises(StageError) as caught:
            submit(self.run_dir, adr_id, payload)
        return "\n".join(caught.exception.errors)

    def effective(self):
        return adr.load_effective(self.run_dir, adr.current_adr(self.run_dir))


class RunResolutionTests(AdrTestCase):
    def test_without_run_the_current_validated_run_is_used_and_an_explicit_run_wins(self) -> None:
        self.assertEqual(self.run_dir, adr.resolve_canonical(None, self.run.artifacts))
        other = fx.AdrRun("api-refunds")
        self.addCleanup(other.close)
        self.assertEqual(other.run_dir, adr.resolve_canonical(str(other.run_dir), self.run.artifacts))
        result = workflow.dispatch("ftd-adr", scope=str(self.run.corpus), output_dir=str(self.run.artifacts))
        self.assertEqual("adr-001", result["adr_run_id"])

    def test_a_stale_pointer_or_a_tampered_canonical_suite_is_refused(self) -> None:
        pointer = self.run.artifacts / ".ftd" / "current-run.json"
        data = json.loads(pointer.read_text(encoding="utf-8"))
        pointer.write_text(json.dumps({**data, "canonical_digest": "0" * 64}), encoding="utf-8")
        with self.assertRaises(pipeline.IntegrityError):
            adr.resolve_canonical(None, self.run.artifacts)
        pointer.write_text(json.dumps(data), encoding="utf-8")
        suite = self.run_dir / "canonical-suite.json"
        suite.write_text(suite.read_text(encoding="utf-8").replace("Invitation expires", "Invitation lapses", 1), encoding="utf-8")
        with self.assertRaises((adr.AdrError, pipeline.IntegrityError)):
            adr.resolve_canonical(str(self.run_dir), self.run.artifacts)

    def test_no_run_is_guessed_from_folders(self) -> None:
        (self.run.artifacts / ".ftd" / "current-run.json").unlink()
        self.assertTrue(any((self.run.artifacts / ".ftd" / "runs").iterdir()))
        with self.assertRaisesRegex(pipeline.IntegrityError, "no --run given"):
            adr.resolve_canonical(None, self.run.artifacts)

    def test_an_unvalidated_explicit_run_is_refused(self) -> None:
        draft = fx.PackRun("api-refunds")
        self.addCleanup(draft.close)
        draft.through("design")
        with self.assertRaisesRegex(adr.AdrError, "not a VALIDATED"):
            adr.resolve_canonical(str(draft.run_dir), draft.artifacts)


class IncrementalReadingTests(AdrTestCase):
    def test_new_files_are_read_and_unsupported_ones_reported(self) -> None:
        started = self.start()
        self.assertEqual({"NEW_READ": 2, "UNSUPPORTED": 1}, {k: v for k, v in started["sources"].items() if v})
        work_order = json.loads(Path(started["work_order"]).read_text(encoding="utf-8"))
        texts = {s["path"]: s["text"] for s in work_order["adr_sources"]}
        self.assertEqual(fx.ADR_TEXT, texts[fx.ADR_FILE])
        self.assertIsNone(texts["diagram.png"])
        self.assertEqual(12, len(work_order["test_cases"]))

    def test_unchanged_files_are_reused_and_only_changed_or_new_ones_read(self) -> None:
        self.run.round()
        again = self.start()
        self.assertEqual({"UNCHANGED_REUSED": 2, "UNSUPPORTED": 1}, {k: v for k, v in again["sources"].items() if v})
        work_order = json.loads(Path(again["work_order"]).read_text(encoding="utf-8"))
        self.assertTrue(all(s["text"] is None for s in work_order["adr_sources"]))
        self.assertEqual({"ADR-007", "ADR-DEC-001"}, {d["id"] for d in work_order["reused_decisions"]})
        (self.run.corpus / fx.NOTE_FILE).write_text(fx.NOTE_TEXT + "\nNothing else was decided.\n", encoding="utf-8")
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        inventory = {e["path"]: e["disposition"] for e in adr.inventory(self.run.corpus, self.effective()["sources"])}
        self.assertEqual({fx.ADR_FILE: "UNCHANGED_REUSED", fx.NOTE_FILE: "CHANGED_READ", fx.ROUND2_FILE: "NEW_READ",
                          "diagram.png": "UNSUPPORTED"}, inventory)

    def test_a_removed_file_never_revokes_its_decisions(self) -> None:
        self.run.round()
        (self.run.corpus / fx.ADR_FILE).unlink()
        started = self.start()
        self.assertEqual(1, started["sources"]["SOURCE_REMOVED_FROM_SELECTION"])
        adr.submit_analysis(self.run_dir, started["adr_run_id"], {})
        adr.submit_procedures(self.run_dir, started["adr_run_id"], {"procedures": []})
        adr.finalize_adr(self.run_dir, started["adr_run_id"])
        document = self.effective()
        self.assertIn("ADR-007", {d["id"] for d in document["decisions"]})
        self.assertEqual(started["adr_run_id"], document["sources"][fx.ADR_FILE]["removed_from_selection_in"])
        self.assertEqual("TC-013", document["cases"][-1]["id"])

    def test_the_parent_run_is_never_modified_and_no_source_is_reread(self) -> None:
        before = adr.parent_snapshot(self.run_dir)
        workspace = {p: p.read_bytes() for p in self.run.pack.workspace.rglob("*") if p.is_file()}
        original_read = Path.read_text

        def guarded(path, *args, **kwargs):
            if self.run.pack.workspace in Path(path).resolve().parents:
                raise AssertionError(f"original project source reread: {path}")
            return original_read(path, *args, **kwargs)
        with mock.patch.object(Path, "read_text", guarded):
            result = self.run.round()
        self.assertEqual(before, adr.parent_snapshot(self.run_dir))
        self.assertEqual(workspace, {p: p.read_bytes() for p in self.run.pack.workspace.rglob("*") if p.is_file()})
        self.assertEqual(0, result["metrics"]["runtime_full_parent_source_rereads"])
        self.assertEqual(self.canonical["semantic_fingerprint"],
                         json.loads((self.run.artifacts / ".ftd" / "current-run.json").read_text(encoding="utf-8"))["canonical_digest"])

    def test_a_lookup_is_bounded_recorded_and_read_from_the_parent_evidence(self) -> None:
        adr_id = self.start()["adr_run_id"]
        found = adr.lookup(self.run_dir, adr_id, "docs/requirements.md", query="expires after 7 days")
        self.assertIn("7 days", found["excerpt"])
        with self.assertRaisesRegex(adr.AdrError, "bounded"):
            adr.lookup(self.run_dir, adr_id, "docs/requirements.md", line_start=1, line_end=500)
        with self.assertRaisesRegex(adr.AdrError, "not a readable source"):
            adr.lookup(self.run_dir, adr_id, "../outside.md", query="x")
        adr.submit_analysis(self.run_dir, adr_id, fx.analysis())
        adr.submit_procedures(self.run_dir, adr_id, fx.procedures())
        self.assertEqual(1, adr.finalize_adr(self.run_dir, adr_id)["metrics"]["targeted_parent_lookups"])


class AuthorityTests(AdrTestCase):
    def test_an_approved_decision_supersedes_the_old_rule_without_naming_it(self) -> None:
        self.assertNotIn("REQ-001", fx.ADR_TEXT + fx.NOTE_TEXT)
        self.assertNotIn("TC-002", fx.ADR_TEXT + fx.NOTE_TEXT)
        self.run.round()
        decision = next(d for d in self.effective()["decisions"] if d["id"] == "ADR-007")
        self.assertEqual(("APPROVED", "SUPERSEDES"), (decision["status"], decision["relationship"]))
        self.assertEqual("The invitation expires after 7 days.", decision["previous_authority"]["statement"])
        self.assertEqual({fx.ADR_FILE}, {p["source"] for p in decision["provenance"]})

    def test_approval_is_never_assumed(self) -> None:
        payload = fx.analysis()
        payload["statements"][0]["authority_evidence"] = "approved by everyone"
        self.assertIn("approval is never assumed", self.rejected(payload))
        payload = fx.analysis()
        payload["statements"][0]["excerpt"] = "an invitation now expires after 3 days"
        self.assertIn("verbatim quote", self.rejected(payload))
        payload = fx.analysis()
        payload["decisions"][0]["official_id"] = "ADR-099"
        self.assertIn("never pretend an id", self.rejected(payload))

    def test_a_draft_never_silently_supersedes(self) -> None:
        payload = fx.analysis()
        payload["statements"][0].update(status="DRAFT", authority_evidence=None)
        payload["statements"][1].update(status="DRAFT", authority_evidence=None)
        errors = self.rejected(payload)
        self.assertIn("never supersedes the existing authority silently", errors)
        self.assertIn("needs an APPROVED decision", errors)
        reviewed = fx.analysis()
        for statement in reviewed["statements"][:2]:
            statement.update(status="DRAFT", authority_evidence=None)
        reviewed["decisions"][0]["claims"] = []
        reviewed["test_cases"] = [{"test": "TC-002", "action": "REVIEW_ONLY", "impact": "DIRECT", "decisions": ["D1"],
                                   "reason": "A draft proposes a shorter window that is not approved yet."},
                                  reviewed["test_cases"][3]]
        reviewed["questions"].append({"key": "Q2", "question": "Is the three-day window approved?",
                                      "reason": "Only a draft proposes it.", "impact": "REQUIREMENT_AMBIGUITY",
                                      "decisions": ["D1"], "tests": ["TC-002"]})
        reviewed["findings"][0]["tests"] = ["TC-002"]
        reviewed["dimension_reviews"] = []
        adr_id = self.start()["adr_run_id"]
        result = adr.submit_analysis(self.run_dir, adr_id, reviewed)
        self.assertEqual([], result["procedures_required"])

    def test_supporting_material_is_context_unless_an_approved_decision_adopts_it(self) -> None:
        payload = fx.analysis()
        payload["statements"][0].update(status="REFERENCE", authority_evidence=None, kind="REFERENCE_INFORMATION")
        payload["statements"][1].update(status="REFERENCE", authority_evidence=None)
        self.assertIn("needs an APPROVED decision", self.rejected(payload))

    def test_a_clarification_affects_without_changing_the_definition(self) -> None:
        payload = fx.analysis()
        payload["decisions"][0].update(relationship="CLARIFIES", reason="the window is restated without a change",
                                       claims=[], previous_authority={})
        payload["test_cases"] = [{"test": "TC-002", "action": "AFFECTED_NO_CHANGE", "impact": "DIRECT",
                                  "decisions": ["D1"], "reason": "The rule is restated, not changed."},
                                 payload["test_cases"][3]]
        payload["findings"][0]["tests"] = ["TC-002"]
        payload["dimension_reviews"] = []
        result = self.run.round(payload, {"procedures": []})
        self.assertEqual((0, 0, 1), (result["metrics"]["updated_cases"], result["metrics"]["created_cases"],
                                     result["metrics"]["affected_no_change_cases"]))
        tc002 = next(c for c in self.effective()["cases"] if c["id"] == "TC-002")
        self.assertEqual(stable_digest(next(c for c in self.canonical["cases"] if c["id"] == "TC-002")), stable_digest(tc002))

    def test_an_adr_answers_an_existing_question_without_erasing_it(self) -> None:
        self.run.round()
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        self.run.round(fx.round2_analysis(), fx.round2_procedures())
        document = self.effective()
        self.assertIn("Q-003", {q["id"] for q in document["questions"]})
        self.assertEqual("RESOLVED_BY_ADR", document["question_dispositions"]["Q-003"][-1]["disposition"])
        self.assertEqual("ADR-DEC-002", document["question_dispositions"]["Q-003"][-1]["decision"])

    def test_conflicting_statements_are_never_voted(self) -> None:
        payload = fx.analysis()
        payload["statements"].append({"key": "S5", "source": fx.NOTE_FILE, "reference": "line 3",
                                      "excerpt": "Maybe we should remind the owner", "kind": "DRAFT_IDEA",
                                      "status": "APPROVED", "authority_evidence": "Team sync notes",
                                      "meaning": "A competing approved idea.", "confidence": "LOW",
                                      "disposition": "CONTEXT", "reason": "competes with the decision text"})
        payload["decisions"][0]["conflicting_statements"] = ["S5"]
        self.assertIn("never vote or pick one", self.rejected(payload))
        payload["statements"][-1].update(status="PROPOSED", authority_evidence=None)
        payload["decisions"][0]["authority_resolution"] = "The approved ADR overrides the meeting idea."
        adr_id = self.start()["adr_run_id"]
        self.assertEqual("ANALYZED", adr.submit_analysis(self.run_dir, adr_id, payload)["status"])

    def test_every_file_and_statement_is_dispositioned_and_explained(self) -> None:
        payload = fx.analysis()
        payload["sources"].pop()
        self.assertIn("was read but not reviewed", self.rejected(payload))
        payload = fx.analysis()
        payload["statements"][2]["reason"] = ""
        self.assertIn("requires a reason", self.rejected(payload))
        payload = fx.analysis()
        payload["questions"][0]["statements"] = []
        self.assertIn("statement S4 is dispositioned QUESTION but no question names it", self.rejected(payload))
        payload = fx.analysis()
        payload["decisions"][1]["relationship"] = "NO_TEST_IMPACT"
        self.assertIn("NO_TEST_IMPACT requires a reason", self.rejected(payload))


class TestCaseDeltaTests(AdrTestCase):
    def test_ids_keys_and_unaffected_definitions_across_three_rounds(self) -> None:
        canonical = {c["id"]: stable_digest(c) for c in self.canonical["cases"]}
        self.run.round()
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        self.run.round(fx.round2_analysis(), fx.round2_procedures())
        (self.run.corpus / fx.ROUND3_FILE).write_text(fx.ROUND3_TEXT, encoding="utf-8")
        last = self.run.round(fx.round3_analysis(), fx.round3_procedures())
        document = self.effective()
        states = document["case_states"]
        self.assertEqual(["adr-001", "adr-002", "adr-003"], document["lineage"])
        self.assertEqual([f"TC-{n:03d}" for n in range(1, 16)], [c["id"] for c in document["cases"]])
        self.assertEqual(("adr:TC-013", "adr:TC-014", "adr:TC-015"),
                         (states["TC-013"]["export_key"], states["TC-014"]["export_key"], states["TC-015"]["export_key"]))
        for cid in canonical:
            self.assertEqual(f"canonical:{cid}", states[cid]["export_key"])
        self.assertEqual(("SUPERSEDED", "TC-015", "TC-005"), (states["TC-005"]["state"], states["TC-005"]["superseded_by"],
                                                             states["TC-015"]["supersedes"]))
        changed = {"TC-002"}  # TC-005 is superseded, never rewritten
        for case in document["cases"]:
            if case["id"] in canonical and case["id"] not in changed:
                self.assertEqual(canonical[case["id"]], stable_digest(case), case["id"])
        tc013 = [h for h in document["case_history"]["TC-013"]]
        self.assertEqual(["CREATE", "UPDATE"], [h["action"] for h in tc013])
        self.assertEqual(["Q-001", "Q-002", "Q-003"], [q["id"] for q in document["questions"]])
        self.assertEqual(["FND-001", "FND-002"], [f["id"] for f in document["findings"]])
        self.assertEqual(0, last["metrics"]["unaffected_cases_changed"])

    def test_an_updated_case_keeps_its_identity_and_full_definition(self) -> None:
        self.run.round()
        tc002 = next(c for c in self.effective()["cases"] if c["id"] == "TC-002")
        self.assertEqual("Invitation expires after three days", tc002["title"])
        for field in ("preconditions", "test_data", "steps", "cleanup", "automation_suitability", "automation_layer",
                      "automation_tool_hint", "automation_readiness", "readiness_blockers", "requirement_refs",
                      "coverage_point_refs", "scenario_refs", "source_refs"):
            self.assertIn(field, tc002)
        self.assertEqual("NEEDS_FIXTURE", tc002["automation_readiness"])
        self.assertTrue(all(step["expected_result"] for step in tc002["steps"]))
        changes = json.loads((self.run.artifacts / "output" / "adr" / "adr-001" / "procedure-changes.json")
                             .read_text(encoding="utf-8"))["changes"]["TC-002"]
        self.assertIn("steps", changes["changed"])
        self.assertIn("cleanup", changes["unchanged"])
        self.assertEqual([{"step": 2, "change": "CHANGED", "parts": ["expected_result"]}],
                         [s for s in changes["steps"] if s["step"] == 2])
        self.assertIn("7 days", json.dumps(changes["fields"]["steps"]["before"]))

    def test_the_same_material_twice_gives_the_same_ids_and_no_duplicates(self) -> None:
        first = self.run.round()
        results = []
        for _ in range(2):
            other = fx.AdrRun()
            self.addCleanup(other.close)
            fx.write_corpus(other.corpus)
            results.append(other.round())
            document = adr.load_effective(other.run_dir, "adr-001")
            results[-1]["ids"] = ([c["id"] for c in document["cases"]], [q["id"] for q in document["questions"]],
                                  [d["id"] for d in document["decisions"]],
                                  sorted(s["export_key"] for s in document["case_states"].values()))
        self.assertEqual(results[0]["ids"], results[1]["ids"])
        self.assertEqual(first["metrics"], results[0]["metrics"])
        rerun = self.run.round({}, {"procedures": []})
        self.assertEqual((0, 0, 0), (rerun["metrics"]["adr_files_read"], rerun["metrics"]["created_cases"],
                                     rerun["metrics"]["azure_delta_test_cases"]))
        self.assertEqual(14, len(self.effective()["case_states"]) + 1)

    def test_unaffected_cases_can_never_be_linked_or_changed(self) -> None:
        payload = fx.analysis()
        payload["questions"][0]["tests"] = ["TC-007"]
        self.assertIn("not an affected Test Case of this round", self.rejected(payload))


class ProcedureTests(AdrTestCase):
    def test_every_update_and_create_needs_a_complete_procedure_through_the_canonical_gate(self) -> None:
        procedures = fx.procedures()
        procedures["procedures"].pop()
        self.assertIn("have no procedure", self.rejected(procedures, stage="procedures"))
        procedures = fx.procedures()
        procedures["procedures"][0]["steps"][1]["expected_result"] = ""
        self.assertIn("requires an observable expected_result", self.rejected(procedures, stage="procedures"))
        procedures = fx.procedures()
        procedures["procedures"][0]["steps"][1]["action"] = "Perform the operation described."
        self.assertIn("abstract", self.rejected(procedures, stage="procedures"))

    def test_a_weak_design_is_rejected_before_any_procedure(self) -> None:
        payload = fx.analysis()
        payload["test_cases"][1]["design"]["expected"] = "It works as expected."
        self.assertIn("names nothing observable", self.rejected(payload))
        payload = fx.analysis()
        payload["test_cases"][0]["design"]["expected"] = ("The invitation is shown as expired and the owner receives "
                                                          "a notification.")
        self.assertIn("one failure domain per Test Case", self.rejected(payload))

    def test_execution_details_are_never_invented(self) -> None:
        procedures = fx.procedures()
        procedures["procedures"][1]["steps"][0]["action"] = "Open /invitations/legacy for EMAIL_LEGACY."
        procedures["procedures"][1]["steps"][1]["expected_result"] = 'The page shows "Legacy window active".'
        errors = self.rejected(procedures, stage="procedures")
        self.assertIn("/invitations/legacy", errors)
        self.assertIn("never invent", errors)

    def test_a_missing_execution_surface_keeps_the_case_as_needs_review(self) -> None:
        procedures = fx.procedures()
        create = procedures["procedures"][1]
        create.pop("evidence_refs")
        create["unknowns"] = [{"kind": "MISSING_EXECUTION_SURFACE", "question": "Q1",
                               "detail": "the ADR does not say where an earlier invitation's status is shown"}]
        self.run.round(fx.analysis(), procedures)
        tc013 = next(c for c in self.effective()["cases"] if c["id"] == "TC-013")
        self.assertEqual(("NEEDS_REVIEW", "NEEDS_ENVIRONMENT"), (tc013["status"], tc013["automation_readiness"]))
        self.assertIn("MISSING_EXECUTION_SURFACE", tc013["readiness_blockers"])
        self.assertIn("Q-003", tc013["question_refs"])

    def test_a_request_contract_is_preserved_for_the_executor(self) -> None:
        procedures = fx.procedures()
        procedures["procedures"][1].update(
            automation={"suitability": "HIGH", "layer": "API", "tool_hint": "API_TEST"},
            request_contract={"method": "GET", "endpoint": "invitation status of EMAIL_LEGACY",
                              "measurements": ["status shown"], "parameters": ["EMAIL_LEGACY"]})
        self.run.round(fx.analysis(), procedures)
        tc013 = next(c for c in self.effective()["cases"] if c["id"] == "TC-013")
        self.assertEqual(["status shown"], tc013["request_contract"]["measurements"])


class OutputTests(AdrTestCase):
    def test_the_report_shows_lineage_decisions_before_after_and_honest_counts(self) -> None:
        result = self.run.round()
        folder = self.run.artifacts / "output" / "adr" / "adr-001"
        report = (folder / "adr-report.html").read_text(encoding="utf-8")
        for text in ("ADR review — adr-001", "saas-accounts", "ADR-007", "SUPERSEDES", "The invitation expires after 7 days.",
                     "TC-002", "TC-013", "Q-003", "FND-002", "Directly affected", "Unaffected", "AFFECTED_NO_CHANGE"):
            self.assertIn(text, report)
        self.assertNotIn("<script", report)
        self.assertNotIn("http", report.replace("http-equiv", ""))
        metrics = result["metrics"]
        self.assertEqual((2, 2, 9, 0), (metrics["directly_affected_cases"], metrics["indirectly_affected_cases"],
                                        metrics["unaffected_cases"], metrics["unaffected_cases_changed"]))
        manifest = json.loads((folder / "adr-manifest.json").read_text(encoding="utf-8"))
        from common import file_digest
        for name, digest in manifest["files"].items():
            self.assertEqual(digest, file_digest(folder / name), name)
        self.assertIn("ADR review", (folder / "adr-summary.md").read_text(encoding="utf-8"))

    def test_the_report_follows_the_parent_locale(self) -> None:
        other = fx.AdrRun("erp-sales-orders")
        self.addCleanup(other.close)
        other.corpus.mkdir(parents=True)
        (other.corpus / "diagram.png").write_bytes(b"\x89PNG binary")
        other.round({}, {"procedures": []})
        report = (other.artifacts / "output" / "adr" / "adr-001" / "adr-report.html").read_text(encoding="utf-8")
        self.assertIn('lang="es"', report)
        self.assertIn("Revisión de ADR", report)

    def test_tampering_with_a_finalized_round_is_detected(self) -> None:
        self.run.round()
        effective = self.run_dir / "adr" / "adr-001" / "effective-suite.json"
        effective.write_text(effective.read_text(encoding="utf-8").replace("three days", "two days", 1), encoding="utf-8")
        with self.assertRaisesRegex(adr.AdrError, "changed after it was finalized"):
            self.start()


class LifecycleSafetyTests(AdrTestCase):
    def test_a_rejected_submission_records_nothing_and_finalized_rounds_are_immutable(self) -> None:
        adr_id = self.start()["adr_run_id"]
        folder = self.run_dir / "adr" / adr_id
        before = sorted(p.name for p in folder.iterdir())
        with self.assertRaises(StageError):
            adr.submit_analysis(self.run_dir, adr_id, {"decisions": [{"key": "D1"}]})
        self.assertEqual(before, sorted(p.name for p in folder.iterdir()))
        self.assertEqual("STARTED", adr.status(self.run_dir, adr_id)["status"])
        adr.submit_analysis(self.run_dir, adr_id, fx.analysis())
        adr.submit_procedures(self.run_dir, adr_id, fx.procedures())
        adr.finalize_adr(self.run_dir, adr_id)
        with self.assertRaisesRegex(adr.AdrError, "immutable"):
            adr.submit_analysis(self.run_dir, adr_id, fx.analysis())
        self.assertEqual("adr-002", self.start()["adr_run_id"])

    def test_a_failure_during_finalize_leaves_every_pointer_and_earlier_state_intact(self) -> None:
        self.run.round()
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        adr_id = self.start()["adr_run_id"]
        adr.submit_analysis(self.run_dir, adr_id, fx.round2_analysis())
        adr.submit_procedures(self.run_dir, adr_id, fx.round2_procedures())
        current_run = (self.run.artifacts / ".ftd" / "current-run.json").read_bytes()
        import adr_render
        with mock.patch.object(adr_render, "publish", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                adr.finalize_adr(self.run_dir, adr_id)
        self.assertEqual("adr-001", adr.current_adr(self.run_dir))
        self.assertEqual("PROCEDURES_READY", adr.status(self.run_dir, adr_id)["status"])
        self.assertEqual(current_run, (self.run.artifacts / ".ftd" / "current-run.json").read_bytes())
        adr.load_effective(self.run_dir, "adr-001")
        with mock.patch.object(adr, "mark_current_adr", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                adr.finalize_adr(self.run_dir, adr_id)
        self.assertEqual(("FINALIZED", "adr-001"), (adr.status(self.run_dir, adr_id)["status"], adr.current_adr(self.run_dir)))
        self.assertEqual(adr_id, adr.finalize_adr(self.run_dir, adr_id)["current_adr"])

    def test_an_interrupted_start_never_becomes_a_round(self) -> None:
        with mock.patch.object(adr, "work_order", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                self.start()
        self.assertFalse((self.run_dir / "adr" / "adr-001").exists())
        self.assertEqual("adr-001", self.start()["adr_run_id"])

    def test_broken_adr_state_fails_closed(self) -> None:
        self.run.round()
        pointer = self.run.artifacts / ".ftd" / "current-adr.json"
        data = json.loads(pointer.read_text(encoding="utf-8"))
        data["lineages"]["saas-accounts"]["effective_digest"] = "0" * 64
        pointer.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(adr.AdrError, "does not match"):
            self.start()
        pointer.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(adr.AdrError, "corrupt"):
            self.start()
        self.assertEqual("adr-002", adr.start_adr(self.run_dir, self.run.corpus, base_adr="adr-001")["adr_run_id"])

    def test_adr_never_contacts_azure_even_with_credentials_available(self) -> None:
        network, socket = no_network()
        with network, socket, mock.patch.dict("os.environ", {"AZURE_DEVOPS_EXT_PAT": "x" * 40}):
            result = self.run.round()
        self.assertEqual((0, 0), (result["live_azure_calls"], result["azure_writes"]))


class CanonicalIsolationTests(unittest.TestCase):
    def test_the_canonical_pipeline_has_no_adr_branches(self) -> None:
        root = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("pipeline.py", "design.py", "expansion.py", "procedures.py", "validation.py", "render.py",
                     "challenge.py", "reading.py", "sources.py"):
            text = (root / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertNotIn("import adr", text)
                self.assertNotIn("current-adr", text)

    def test_a_v242_style_run_without_adr_files_works(self) -> None:
        run = fx.AdrRun()
        self.addCleanup(run.close)
        self.assertFalse((run.run_dir / "adr").exists())
        self.assertFalse((run.artifacts / ".ftd" / "current-adr.json").exists())
        fx.write_corpus(run.corpus)
        self.assertEqual("FINALIZED", run.round()["status"])


if __name__ == "__main__":
    unittest.main()
