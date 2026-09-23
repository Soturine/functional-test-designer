"""Guards against ways a model can satisfy the stages while lowering semantic quality."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from support import PackRun, by_key, candidate, procedure

import pipeline
import sources
from common import StageError, stable_digest


def design(pack):
    return pack["stages"]["design"]


def expansion(pack):
    return pack["stages"]["expansion"]


class OverCompressionTests(unittest.TestCase):
    def test_compound_section_cannot_silently_become_one_summary_claim(self) -> None:
        def summarize(pack):
            d = design(pack)
            by_key(d["claims"], "C1")["text"] = "The owner can invite users by email."
            d["claims"] = [c for c in d["claims"] if c["key"] != "C2"]
            d["tests"] = [t for t in d["tests"] if t["key"] != "T2"]
        run = PackRun("saas-accounts", summarize)
        self.addCleanup(run.close)
        run.start()
        with self.assertRaisesRegex(StageError, "FR-01 has 2 structural items in the authority but one claim"):
            run.submit("design")

    def test_structural_items_are_counted_not_interpreted(self) -> None:
        text = "BR-7 - Limits\nA transfer above 1000 needs approval by a manager.\nA transfer above 5000 is refused by the bank.\n"
        entry = sources.extract_identifiers(text, "a.md")[0]
        self.assertEqual(2, entry["structural_items"])


class CoverageHardeningTests(unittest.TestCase):
    def reach(self, name, mutate):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("design")
        return run

    def test_operator_error_is_not_covered_by_an_unrelated_happy_path(self) -> None:
        def happy(pack):
            item = candidate(pack, "OPERATOR_ERROR", "O2")
            item.update(disposition="ALREADY_COVERED", covered_by=["T1"], description="The owner submits the invitation form twice by accident.")
            item["intent"] = {"actor": "Owner in a hurry", "state": "account with seats still free",
                              "trigger": "the owner submits an invitation for an email twice", "failure_domain": "invitation creation twice",
                              "expected": "a pending invitation is created"}
        run = self.reach("saas-accounts", happy)
        with self.assertRaisesRegex(StageError, r"adversarial or failure scenario; a happy-path test \['T1'\] does not exercise it"):
            run.submit("expansion")

    def test_intent_copied_from_the_target_is_rejected(self) -> None:
        def copied(pack):
            t6 = by_key(design(pack)["tests"], "T6")
            candidate(pack, "OPERATOR_ERROR", "O1")["intent"] = {
                "actor": t6["actor"], "state": t6["state"], "trigger": t6["trigger"],
                "failure_domain": t6["failure_domain"], "expected": t6["expected"]}
        run = self.reach("saas-accounts", copied)
        with self.assertRaisesRegex(StageError, "intent repeats the target test word for word"):
            run.submit("expansion")

    def test_independent_failure_surfaces_need_independent_dispositions(self) -> None:
        def shared(pack):
            record = next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "INTEGRATION")
            record["candidates"] += [
                {"key": "I2", "description": "The network drops while inviting.", "surface": "NETWORK", "disposition": "QUESTION_REQUIRED", "question": "Q-EMAIL"},
                {"key": "I3", "description": "The session expires while inviting.", "surface": "SESSION_INTERRUPTION", "disposition": "QUESTION_REQUIRED", "question": "Q-EMAIL"},
            ]
            chaos = next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "CHAOS")
            chaos["surfaces_reviewed"] = [{"items": ["EXTERNAL_DEPENDENCY", "CONCURRENCY", "NETWORK", "SESSION_INTERRUPTION"], "status": "CANDIDATES"},
                                          {"items": ["MIDDLEWARE", "DEVICE_HARDWARE", "CACHE", "DATABASE", "ASYNC_WORKER", "RETRY", "DUPLICATE_EVENT",
                                                     "OUT_OF_ORDER_EVENT", "PARTIAL_COMMIT", "PROCESS_RESTART", "RACE_CONDITION"],
                                           "status": "NOT_APPLICABLE", "reason": "the sources describe no such component"}]
        run = self.reach("saas-accounts", shared)
        with self.assertRaisesRegex(StageError, r"question Q-EMAIL dispositions surfaces \['NETWORK', 'SESSION_INTERRUPTION'\]"):
            run.submit("expansion")

    def test_unrelated_test_assets_cannot_converge_on_one_generic_target(self) -> None:
        def converge(pack):
            assets = expansion(pack)["test_assets"]
            index = next(i for i, a in enumerate(assets) if a["asset"].endswith("::test_serializer_rounds_cents"))
            assets[index] = {"asset": assets[index]["asset"], "disposition": "ALREADY_COVERED_BY", "covered_by": ["T1"], "intent": {
                "actor": "pytest client fixture", "state": "payment fixture captured for 100", "trigger": "the test posts a refund with cents",
                "failure_domain": "refund creation cents rounding format", "expected": "the API returns 201 with the refund id rounded to cents"}}
        run = self.reach("api-refunds", converge)
        with self.assertRaisesRegex(StageError, "describe different behaviors but converge on"):
            run.submit("expansion")


class ProcedureGroundingTests(unittest.TestCase):
    def reach(self, name, mutate=None):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    def test_generic_authentication_boilerplate_is_rejected(self) -> None:
        def boilerplate(pack):
            item = procedure(pack, "T3")
            item["steps"] = [{"action": "Sign in to the application.", "expected_result": "The home page is shown."}] + item["steps"]
        run = self.reach("saas-accounts", boilerplate)
        with self.assertRaisesRegex(StageError, "step 1 only authenticates"):
            run.submit("procedures")

    def test_procedure_must_cite_its_execution_path_or_declare_the_gap(self) -> None:
        def ungrounded(pack):
            procedure(pack, "T5").pop("evidence_refs")
        run = self.reach("saas-accounts", ungrounded)
        with self.assertRaisesRegex(StageError, "procedure for T5 is not grounded in selected evidence"):
            run.submit("procedures")

    def test_unknown_path_keeps_the_test_as_needs_review(self) -> None:
        def gap(pack):
            item = procedure(pack, "T5")
            item.pop("evidence_refs")
            item["unknowns"] = [{"kind": "MISSING_EXECUTION_SURFACE", "detail": "no selected source shows the member page"}]
        run = self.reach("saas-accounts", gap)
        run.submit("procedures")
        pipeline.finalize_run(run.run_dir, ["JSON"])
        case = next(run.output(f"test-cases/TC-{n:03d}.json") for n in range(5, 6))
        self.assertEqual(("NEEDS_REVIEW", ["MISSING_EXECUTION_SURFACE"]), (case["status"], case["readiness_blockers"]))
        self.assertEqual(12, len(run.output("test-cases.json")["test_cases"]))


class ProcedureStageInvariantTests(unittest.TestCase):
    def test_procedures_never_change_the_frozen_suite(self) -> None:
        run = PackRun("logistics-storage")
        self.addCleanup(run.close)
        run.through("expansion")
        frozen = [(t["id"], t["title"], t["expected"], t["failure_domain"], t["basis"]) for t in pipeline._all_tests(run.run_dir)]
        before = stable_digest(json.loads((run.run_dir / "stages" / "design.result.json").read_text(encoding="utf-8")))
        run.submit("procedures")
        pipeline.finalize_run(run.run_dir, ["JSON"])
        index = run.output("test-cases.json")
        cases = {entry["id"]: run.output(entry["file"]) for entry in index["test_cases"]}
        self.assertEqual(len(frozen), len(cases))
        for test_id, title, expected, domain, basis in frozen:
            self.assertEqual((title, domain, basis), (cases[test_id]["title"], cases[test_id]["failure_domain"], cases[test_id]["test_basis"]))
        after = stable_digest(json.loads((run.run_dir / "stages" / "design.result.json").read_text(encoding="utf-8")))
        self.assertEqual(before, after)

    def test_procedures_cannot_carry_identity_fields(self) -> None:
        def rename(pack):
            procedure(pack, "T1")["title"] = "A merged broader test"
            procedure(pack, "T2")["composes"] = ["T3"]
        run = PackRun("logistics-storage", rename)
        self.addCleanup(run.close)
        run.through("expansion")
        with self.assertRaisesRegex(StageError, r"runtime-owned or unknown fields \['title'\]") as caught:
            run.submit("procedures")
        self.assertIn("['composes']", str(caught.exception))

    def test_procedure_stage_reads_no_source_content_and_checks_digests_once(self) -> None:
        run = PackRun("aerospace-inspection")
        self.addCleanup(run.close)
        run.through("expansion")
        with mock.patch.object(sources, "read_text", side_effect=AssertionError("source reread")), \
                mock.patch.object(pipeline, "file_digest", wraps=pipeline.file_digest) as digests:
            run.submit("procedures")
        records = len(json.loads((run.run_dir / "sources.json").read_text(encoding="utf-8"))["records"])
        tests = len(pipeline._all_tests(run.run_dir))
        # sources once plus the stored stage files: constant, never proportional to the Test Cases
        self.assertLessEqual(digests.call_count, records + 8)
        self.assertLess(digests.call_count, tests + records)

    def test_procedure_work_order_reuses_indexed_evidence_in_family_batches(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.through("expansion")
        order = json.loads((run.run_dir / "work-order.json").read_text(encoding="utf-8"))
        first = order["tests"][0]
        self.assertTrue(first["claims"])
        self.assertIn("FR-01", first["authority_excerpts"])
        self.assertEqual({"src/invitations.py", "tests/test_invitations.py"}, {item["path"] for item in order["evidence_index"]})
        self.assertEqual(sum(len(batch["tests"]) for batch in order["batches"]), len(order["tests"]))

    def test_batch_files_merge_into_one_procedure_stage(self) -> None:
        run = PackRun("iot-line-monitoring")
        self.addCleanup(run.close)
        run.through("expansion")
        all_items = run.pack["stages"]["procedures"]["procedures"]
        merged = pipeline.merge_payloads([{"procedures": all_items[:4]}, {"procedures": all_items[4:]}])
        self.assertTrue(pipeline.submit_stage(run.run_dir, "procedures", merged)["recorded"])

    def test_finalize_reports_procedure_performance_diagnostics(self) -> None:
        run = PackRun("api-refunds")
        self.addCleanup(run.close)
        run.through("procedures")
        pipeline.finalize_run(run.run_dir)
        metrics = json.loads((run.run_dir / "run-metrics.json").read_text(encoding="utf-8"))
        for key in ("procedure_generation_seconds", "targeted_source_lookups", "procedures_generated",
                    "average_procedure_generation_seconds", "procedures_requiring_additional_evidence"):
            self.assertIsNotNone(metrics[key], key)
        self.assertEqual(0, metrics["runtime_source_rereads"])
        self.assertGreaterEqual(metrics["targeted_source_lookups"], metrics["distinct_evidence_sources_cited"])

    def test_navigation_evidence_does_not_alter_the_oracle(self) -> None:
        def navigate(pack):
            item = procedure(pack, "T1")
            item["steps"] = [
                {"action": "Open the member management page from the account menu.", "expected_result": "The member list and the invite form are shown."},
                {"action": "Type EMAIL_NEW in the invite field.", "expected_result": "The invite button becomes enabled."},
                {"action": "Press the invite button.", "expected_result": "A pending invitation for EMAIL_NEW is created and listed."},
            ]
            item["evidence_refs"].append({"source": "src/invitations.py", "reference": "invite"})
        run = PackRun("saas-accounts", navigate)
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        case = run.output("test-cases/TC-001.json")
        self.assertEqual(3, len(case["steps"]))
        self.assertIn({"source": "src/invitations.py", "reference": "invite"}, case["source_refs"])
        self.assertEqual("invitation creation", case["failure_domain"])


class TraceabilityTests(unittest.TestCase):
    def test_one_test_keeps_every_authoritative_relationship_visible(self) -> None:
        def relate(pack):
            by_key(design(pack)["tests"], "T4")["related_identifiers"] = ["CU-01"]
        run = PackRun("logistics-storage", relate)
        self.addCleanup(run.close)
        run.finalize(("HTML", "JSON", "MARKDOWN"))
        index = run.output("test-cases.json")
        case = run.output("test-cases/TC-004.json")
        req = {r["source_identifier"]: r["id"] for r in index["requirements"]}
        self.assertEqual(["RN-01", "FA-01.1", "CU-01"], case["source_identifiers"])
        self.assertEqual([req["RN-01"], req["CU-01"]], case["requirement_refs"])
        self.assertEqual(1, len(case["coverage_point_refs"]))
        self.assertEqual(11, len(index["test_cases"]))
        cu = next(e for e in index["identifier_dispositions"] if e["identifier"] == "CU-01")
        self.assertNotIn("TC-004", cu["test_refs"])
        report = (run.artifacts / "output" / "report.html").read_text(encoding="utf-8")
        summary = report[report.index('<span class="tc-id">TC-004</span>'):].split("</summary>", 1)[0]
        for chip in ("RN-01", "FA-01.1", "CU-01"):
            self.assertIn(f">{chip}</span>", summary)
        self.assertIn("RN-01 — Posição Única", report)

    def test_related_identifier_must_exist_in_authority(self) -> None:
        def invent(pack):
            by_key(design(pack)["tests"], "T4")["related_identifiers"] = ["RN-99"]
        run = PackRun("logistics-storage", invent)
        self.addCleanup(run.close)
        run.start()
        with self.assertRaisesRegex(StageError, "relates identifier RN-99 that is absent"):
            run.submit("design")


if __name__ == "__main__":
    unittest.main()
