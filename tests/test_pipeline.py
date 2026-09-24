"""Official pipeline integrity, publication, honest gaps, baseline mode and generality."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from support import ROOT, PackRun, load_pack

import benchmark
import pipeline
import validation
import workflow
from common import StageError, file_digest


class IntegrityTests(unittest.TestCase):
    def finished(self, name="saas-accounts", formats=("HTML", "JSON", "MARKDOWN")):
        run = PackRun(name)
        self.addCleanup(run.close)
        result = run.finalize(formats)
        return run, result

    def test_canonical_and_publication_integrity_is_valid(self) -> None:  # 23
        run, result = self.finished()
        manifest = pipeline.verify_manifest(run.run_dir)
        self.assertEqual(list(pipeline.STAGES), [item["stage"] for item in manifest["stages"]])
        self.assertEqual([], validation.validate(run.artifacts / "output"))
        self.assertEqual(["HTML", "JSON", "MARKDOWN"], result["render"]["rendered_public_formats"])
        gates = run.output("test-cases.json")["quality_gates"]
        self.assertEqual(list(validation.GATE_NAMES), [gate["gate"] for gate in gates])

    def test_tampering_with_a_recorded_stage_is_detected(self) -> None:  # 23
        run, _ = self.finished()
        stored = run.run_dir / "stages" / "design.result.json"
        document = json.loads(stored.read_text(encoding="utf-8"))
        document["tests"][0]["expected"] = "anything"
        stored.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "design.result.json does not match"):
            pipeline.verify_manifest(run.run_dir)

    def test_tampering_with_published_output_is_detected(self) -> None:  # 23
        run, _ = self.finished()
        target = run.artifacts / "output" / "test-cases" / "TC-001.json"
        target.write_text(target.read_text(encoding="utf-8").replace("Owner", "Anyone"), encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "published artifact digest mismatch"):
            pipeline.verify_manifest(run.run_dir)

    def test_tampered_canonical_state_cannot_be_rendered(self) -> None:  # 23, 24
        run, _ = self.finished()
        canonical = run.run_dir / "canonical-suite.json"
        document = json.loads(canonical.read_text(encoding="utf-8"))
        document["cases"][0]["title"] = "Silently changed"
        canonical.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "canonical state digest mismatch"):
            pipeline.render_run(run.run_dir)

    def test_direct_final_output_bypass_is_impossible(self) -> None:  # 24
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        with self.assertRaisesRegex(pipeline.IntegrityError, "stage procedures is not the next stage"):
            pipeline.submit_stage(run.run_dir, "procedures", run.pack["stages"]["procedures"])
        with self.assertRaisesRegex(pipeline.IntegrityError, "finalize requires every model stage"):
            pipeline.finalize_run(run.run_dir)
        with self.assertRaisesRegex(pipeline.IntegrityError, "only a validated run can be rendered"):
            pipeline.render_run(run.run_dir)
        with self.assertRaisesRegex(ValueError, "no longer accepts a pre-authored semantic request"):
            workflow.dispatch("ftd-gen", workspace=run.workspace, sources=[], artifact_root=run.artifacts,
                              run_id="x", scenario_profiles={}, evidence_packs={})

    def test_skipping_a_manifest_stage_is_detected(self) -> None:  # 24
        run, _ = self.finished()
        path = run.run_dir / "run-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["stages"][3]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "incomplete or reordered"):
            pipeline.verify_manifest(run.run_dir)

    def test_changed_source_invalidates_the_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.through("design")
        source = run.workspace / "docs" / "requirements.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nBR-03 - New Rule\nA new rule.\n", encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "selected source changed"):
            run.submit("expansion")
        restarted = run.start()
        self.assertFalse(restarted["resumed"])
        self.assertEqual("design", json.loads((run.run_dir / "run-state.json").read_text())["next_stage"])

    def test_restarting_an_unchanged_run_resumes(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.through("design")
        self.assertTrue(run.start()["resumed"])

    def test_rejected_stage_is_not_recorded_and_can_be_resubmitted(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        good = run.pack["stages"]["design"]
        with self.assertRaises(StageError):
            pipeline.submit_stage(run.run_dir, "design", {**good, "tests": good["tests"][:-1]})
        self.assertEqual(2, len(json.loads((run.run_dir / "run-manifest.json").read_text())["stages"]))
        self.assertTrue(pipeline.submit_stage(run.run_dir, "design", good)["recorded"])
        state = json.loads((run.run_dir / "run-state.json").read_text())
        self.assertEqual({"design": 1}, state["rejections"])

    def test_render_reads_no_project_source(self) -> None:
        run, result = self.finished(formats=("HTML",))
        self.assertEqual(0, result["render"]["source_reads_during_render"])
        report = (run.artifacts / "output" / "report.html").read_text(encoding="utf-8")
        self.assertNotIn('href="test-cases/', report)


class HonestyTests(unittest.TestCase):
    def test_zero_gaps_only_when_every_dimension_is_zero(self) -> None:  # 21
        metrics = {key: 0 for key in (
            "unmapped_extracted_claims", "unaccounted_normative_units", "uncovered_use_case_flows",
            "unresolved_business_test_assets", "unresolved_questions", "blocked_normative_tests",
        )}
        self.assertEqual("0 gaps", validation.gap_summary(metrics))
        metrics["unaccounted_normative_units"] = 2
        self.assertNotIn("0 gaps", validation.gap_summary(metrics))
        self.assertIn("unaccounted normative units: 2", validation.gap_summary(metrics))

    def test_baseline_is_not_applied_without_a_loaded_baseline(self) -> None:  # 20
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        result = run.finalize(("HTML", "JSON", "MARKDOWN"))
        self.assertEqual({"status": "NOT_APPLIED"}, run.output("test-cases.json")["baseline_comparison"])
        self.assertEqual("NOT_APPLIED", result["metrics"]["baseline_comparison"])
        self.assertEqual("NOT_APPLIED", benchmark.baseline_status(None))
        report = (run.artifacts / "output" / "report.html").read_text(encoding="utf-8")
        self.assertIn("NOT_APPLIED", report)

    def test_applied_baseline_reports_regressions(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.through("procedures")
        baseline = {"corpus": "saas", "normative_intents": [
            {"key": "H1", "identifiers": ["BR-01"], "text": "invitation beyond the seat limit is rejected"},
            {"key": "H2", "identifiers": ["BR-02"], "text": "owner can transfer ownership to another member"},
            {"key": "H3", "identifiers": ["FR-01"], "text": "invitations can be resent"},
        ], "reconciliations": [{"kind": "NORMATIVE_INTENT", "key": "H3", "status": "REMOVED_WITH_REASON", "reason": "removed from authority v2"}]}
        pipeline.finalize_run(run.run_dir, ["JSON"], baseline)
        comparison = run.output("test-cases.json")["baseline_comparison"]
        self.assertEqual("APPLIED", comparison["status"])
        self.assertEqual((1, 1, 1), (comparison["PRESERVED"], comparison["REMOVED_WITH_REASON"], comparison["UNEXPLAINED_REGRESSION"]))

    def test_findings_and_manual_reconciliation_are_explicit(self) -> None:
        report = benchmark.reconcile_findings(
            [{"key": "F1", "statement": "pending invitations count against seats"}, {"key": "F2", "statement": "tokens never expire"}],
            [{"statement": "The implementation counts pending invitations against the seat limit"}], [],
        )
        self.assertEqual(["STILL_PRESENT", "UNEXPLAINED_MISSING"], [item["status"] for item in report["findings"]])
        with self.assertRaisesRegex(ValueError, "fewer than two"):
            benchmark.reconcile_manual_suite([{"id": "M1"}], [{"item": "M1", "disposition": "SPLIT_INTO_MULTIPLE", "targets": ["TC-001"]}],
                                             test_case_ids={"TC-001"}, question_ids=set())


class GeneralityTests(unittest.TestCase):
    """Multi-domain packs guard against benchmark overfitting."""

    def test_every_domain_pack_passes_the_official_pipeline(self) -> None:
        names = sorted(path.stem for path in (ROOT / "benchmarks" / "domains").glob("*.json"))
        self.assertGreaterEqual(len(names), 6)
        locales = set()
        for name in names:
            with self.subTest(pack=name):
                run = PackRun(name)
                try:
                    result = run.finalize(("JSON",))
                    index = run.output("test-cases.json")
                    locales.add(index["output_locale"])
                    self.assertTrue(all(item["disposition"] for item in index["identifier_dispositions"]))
                    self.assertGreater(result["metrics"]["test_cases"], 0)
                finally:
                    run.close()
        self.assertEqual({"en", "pt-BR", "es"}, locales)

    def test_production_code_has_no_synthetic_benchmark_markers(self) -> None:
        forbidden = re.compile(
            r"(?:saas-accounts|logistics-storage|erp-sales-orders|iot-line-monitoring|"
            r"aerospace-inspection|api-refunds|SYNTH_REQ_ALPHA|SYNTH_FLOW_BETA)",
            re.IGNORECASE,
        )
        for path in sorted((ROOT / "scripts").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            hits = sorted({match.group(0) for match in forbidden.finditer(text)})
            with self.subTest(module=path.name):
                self.assertEqual([], hits)

    def test_domain_packs_do_not_share_domain_models(self) -> None:
        entities = [set(load_pack(path.stem)["stages"]["design"]["domain_model"]["entities"])
                    for path in (ROOT / "benchmarks" / "domains").glob("*.json")]
        for index, left in enumerate(entities):
            for right in entities[index + 1:]:
                self.assertFalse(left & right)


class WorkflowTests(unittest.TestCase):
    def test_natural_language_and_alias_reach_the_same_pipeline(self) -> None:
        self.assertEqual("ftd-gen", workflow.resolve_intent("Gere os test cases destas fontes", resolved_intent="ftd-gen"))
        self.assertEqual("ftd-gen", workflow.resolve_intent("/ftd-gen docs"))
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        started = workflow.dispatch_request(
            "Generate test cases from these files", resolved_intent="ftd-gen",
            workspace=run.workspace, artifact_root=run.artifacts,
            run_id="nl", sources=[{"path": "docs", "role": "FUNCTIONAL_AUTHORITY"}],
        )
        self.assertEqual("en", started["output_locale"])
        self.assertTrue(Path(started["work_order"]).is_file())

    def test_check_is_read_only(self) -> None:
        cases = [{"id": "TC-001", "status": "NEEDS_REVIEW", "preconditions": ["Preconditions for: x"], "test_data": [],
                  "steps": [{"step": 1, "action": "Open, select, confirm and then save the order.", "expected_result": "It works as expected."}]}]
        before = json.dumps(cases)
        result = workflow.check_suite(cases, focus="procedure")
        self.assertEqual(before, json.dumps(cases))
        codes = set(result["findings"][0]["reason_codes"])
        self.assertTrue({"GENERIC_PRECONDITION", "PATH_COMPRESSION", "ABSTRACT_OBSERVATION"} <= codes)
        self.assertEqual(0, result["source_reads"])


class FrozenRunTests(unittest.TestCase):
    """A validated run is byte-immutable; a newer run may only declare that it supersedes it."""

    @staticmethod
    def snapshot(run_dir: Path) -> dict[str, str]:
        return {p.relative_to(run_dir).as_posix(): file_digest(p) for p in sorted(run_dir.rglob("*")) if p.is_file()}

    def second_run(self, run: PackRun, run_id: str, **extra) -> Path:
        result = pipeline.start_run(
            workspace=run.workspace, artifact_root=run.artifacts, run_id=run_id,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            locale=run.pack.get("locale"), request_text=run.pack.get("request", ""), reading={"strategy": "SEQUENTIAL"},
            **extra)
        run_dir = Path(result["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            pipeline.submit_stage(run_dir, stage, run.pack["stages"][stage])
        return run_dir

    def test_finalizing_another_run_leaves_a_validated_run_byte_identical(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        before = self.snapshot(run.run_dir)
        other = self.second_run(run, "independent")
        result = pipeline.finalize_run(other, ["JSON"])
        self.assertEqual(before, self.snapshot(run.run_dir))
        self.assertEqual("VALIDATED", json.loads((run.run_dir / "run-state.json").read_text(encoding="utf-8"))["status"])
        self.assertIsNone(result["supersedes"])  # independent runs never supersede each other
        pipeline.verify_manifest(run.run_dir / "run-manifest.json", require_publication=False)

    def test_an_explicit_revision_records_what_it_supersedes_without_touching_it(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        before = self.snapshot(run.run_dir)
        revision = self.second_run(run, "revision", supersedes=run.run_dir.name)
        result = pipeline.finalize_run(revision, ["JSON"])
        self.assertEqual(run.run_dir.name, result["supersedes"])
        self.assertEqual(run.run_dir.name, json.loads((revision / "run.json").read_text(encoding="utf-8"))["supersedes"])
        self.assertEqual(before, self.snapshot(run.run_dir))

    def test_supersedes_must_name_another_existing_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        with self.assertRaises(pipeline.IntegrityError):
            self.second_run(run, "revision", supersedes="does-not-exist")



class PublicationOrganizationTests(unittest.TestCase):
    """The published organization references the canonical cases; it never repeats them."""

    def test_organization_and_execution_plan_are_published_without_cloning(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        index = run.output("test-cases.json")
        organization = run.output("organization.json")
        ids = {entry["id"] for entry in index["test_cases"]}
        self.assertEqual(ids, set(organization["memberships"]))
        self.assertEqual(0, organization["diagnostics"]["cloned_cases"])
        members = [m["case"] for g in organization["groups"] for m in g["members"] if m["origin"] == "CANONICAL"]
        self.assertLessEqual(set(members), ids)
        for group in organization["groups"]:
            self.assertNotIn("steps", json.dumps(group["members"]))
        plan = (run.artifacts / "output" / "execution-plan.md").read_text(encoding="utf-8")
        for case_id in ids:
            self.assertIn(f"[{case_id}]", plan)
        self.assertIn('class="view-tabs"', (run.artifacts / "output" / "report.html").read_text(encoding="utf-8"))
        pipeline.verify_manifest(run.run_dir)


if __name__ == "__main__":
    unittest.main()
