"""Default multi-agent source reading: the deterministic half a Python runtime owns.

Real reader sub-agents are a host concern (SKILL.md); this proves the task plan, the
reader-result contract, all-or-nothing submission, reconciliation before Design,
digest/role/contract-bound reuse, collision-safe keys and honest source accounting."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import pipeline  # noqa: E402
import reading  # noqa: E402
from common import StageError, file_digest  # noqa: E402
from support import PackRun  # noqa: E402


def start(run: PackRun, run_id: str | None = None, strategy: dict | None = None, roles: dict | None = None) -> dict:
    result = pipeline.start_run(
        workspace=run.workspace,
        sources_selected=[{"path": path, "role": (roles or {}).get(path, item["role"])}
                          for path, item in run.pack["sources"].items()],
        artifact_root=run.artifacts, run_id=run_id or run.pack["name"], locale=run.pack.get("locale"),
        request_text=run.pack.get("request", ""), reading=strategy,
    )
    run.run_dir = Path(result["run_dir"])
    return result


def task_plan(run: PackRun) -> dict:
    return json.loads((run.run_dir / "reading" / "task-plan.json").read_text(encoding="utf-8"))


def reader_result(task: dict, **overrides) -> dict:
    result = {
        "source_key": task["source_key"], "path": task["path"], "content_digest": task["content_digest"],
        "status": "CATALOGED", "reader": {"role": reading.READER_ROLE, "model": "test-double"},
        "catalog": {"headings": [f"Heading of {task['path']}"],
                    "excerpts": [{"line_start": 1, "line_end": 1, "text": "first line"}]},
    }
    result.update(overrides)
    return result


def read_everything(run: PackRun) -> dict:
    tasks = reading.pending(task_plan(run))
    pipeline.submit_reading(run.run_dir, [reader_result(task) for task in tasks])
    return pipeline.reconcile_reading(run.run_dir)


class ReadingTaskPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)

    def test_default_strategy_plans_one_reader_task_per_eligible_source(self) -> None:
        result = start(self.run)
        self.assertEqual("MULTI_AGENT_PER_SOURCE", result["reading"]["strategy"])
        self.assertEqual("reading", result["next_stage"])
        tasks = task_plan(self.run)["tasks"]
        self.assertEqual(set(self.run.pack["sources"]), {task["path"] for task in tasks})
        self.assertEqual(len(self.run.pack["sources"]), len(tasks))
        self.assertTrue(all(task["state"] == "PLANNED" for task in tasks))
        self.assertEqual(reading.READER_ROLE, task_plan(self.run)["reader_role"])

    def test_reading_work_order_lists_tasks_and_the_reader_contract(self) -> None:
        result = start(self.run)
        order = json.loads(Path(result["work_order"]).read_text(encoding="utf-8"))
        self.assertEqual("reading", order["next_stage"])
        self.assertEqual(len(self.run.pack["sources"]), len(order["reading_tasks"]))
        contract = order["reader_result_contract"]
        self.assertIn("claims", contract["forbidden_catalog_sections"])
        self.assertEqual(reading.READER_ROLE, contract["reader"]["role"])
        # No vendor model names are baked into the public contract.
        self.assertNotIn("haiku", json.dumps(contract).lower())

    def test_design_is_refused_until_reading_is_reconciled(self) -> None:
        start(self.run)
        with self.assertRaises(pipeline.IntegrityError):
            pipeline.submit_stage(self.run.run_dir, "design", self.run.pack["stages"]["design"])

    def test_sequential_opt_out_uses_the_main_model_and_no_worker(self) -> None:
        result = start(self.run, strategy={"strategy": "SEQUENTIAL", "worker_model": "haiku"})
        self.assertEqual("SEQUENTIAL", result["reading"]["strategy"])
        self.assertIsNone(result["reading"]["worker_model"])
        self.assertEqual("design", result["next_stage"])
        self.assertTrue(all(t["state"] == "MAIN_MODEL" for t in task_plan(self.run)["tasks"]))

    def test_explicit_worker_model_and_concurrency_are_recorded_not_claimed(self) -> None:
        result = start(self.run, strategy={"strategy": "MULTI_AGENT_PER_SOURCE", "worker_model": "haiku",
                                           "concurrency": 4})
        self.assertEqual("haiku", result["reading"]["worker_model"])
        self.assertEqual(4, result["reading"]["concurrency"])
        self.assertEqual(0, result["reading_states"]["CATALOGED"])  # requested, not yet run

    def test_unreadable_sources_stay_visible_with_honest_states(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = reading.plan([
                {"path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY", "status": "NEEDS_TRANSCRIPTION", "content_digest": "x"},
                {"path": "assets/logo.png", "role": "TECHNICAL_CONTEXT", "status": "METADATA_ONLY", "content_digest": "y"},
            ], Path(temp), Path(temp) / "run")
        states = {task["path"]: task["state"] for task in plan["tasks"]}
        self.assertEqual({"docs/spec.pdf": "FAILED_TO_READ", "assets/logo.png": "UNSUPPORTED"}, states)


class ReaderContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        start(self.run)
        self.tasks = reading.pending(task_plan(self.run))

    def assert_rejected(self, result: dict, fragment: str) -> None:
        with self.assertRaises(StageError) as caught:
            pipeline.submit_reading(self.run.run_dir, [result])
        self.assertIn(fragment, " ".join(caught.exception.errors))

    def test_readers_cannot_emit_main_model_decisions(self) -> None:
        self.assert_rejected(reader_result(self.tasks[0], catalog={"claims": ["x"], "headings": ["h"]}),
                             "main-model decisions")

    def test_a_result_for_another_revision_is_rejected(self) -> None:
        self.assert_rejected(reader_result(self.tasks[0], content_digest="0" * 64), "digest mismatch")

    def test_readers_never_change_the_source_role(self) -> None:
        self.assert_rejected(reader_result(self.tasks[0], role="FUNCTIONAL_AUTHORITY"
                                           if self.tasks[0]["role"] != "FUNCTIONAL_AUTHORITY" else "TECHNICAL_CONTEXT"),
                             "role")

    def test_cataloged_requires_a_non_empty_factual_catalog(self) -> None:
        self.assert_rejected(reader_result(self.tasks[0], catalog={}), "non-empty")

    def test_excerpt_lines_must_exist_in_the_snapshot(self) -> None:
        self.assert_rejected(reader_result(self.tasks[0], catalog={"excerpts": [{"line_start": 1, "line_end": 99999}]}),
                             "outside the source")

    def test_submission_is_all_or_nothing(self) -> None:
        good, bad = reader_result(self.tasks[0]), reader_result(self.tasks[1], catalog={})
        with self.assertRaises(StageError):
            pipeline.submit_reading(self.run.run_dir, [good, bad])
        self.assertTrue(all(t["state"] == "PLANNED" for t in task_plan(self.run)["tasks"]))

    def test_reconcile_refuses_while_any_source_has_no_result(self) -> None:
        pipeline.submit_reading(self.run.run_dir, [reader_result(self.tasks[0])])
        with self.assertRaises(StageError) as caught:
            pipeline.reconcile_reading(self.run.run_dir)
        self.assertIn("no reader result", " ".join(caught.exception.errors))

    def test_worker_failure_is_kept_visible_after_reconciliation(self) -> None:
        results = [reader_result(t) for t in self.tasks[1:]]
        results.append(reader_result(self.tasks[0], status="FAILED", catalog=None, error="reader timed out"))
        pipeline.submit_reading(self.run.run_dir, results)
        outcome = pipeline.reconcile_reading(self.run.run_dir)
        self.assertEqual(1, outcome["worker_failures"])
        reconciliation = json.loads((self.run.run_dir / "reading" / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(self.tasks[0]["path"], reconciliation["worker_failures"][0]["path"])

    def test_conflicting_statements_are_preserved_not_voted(self) -> None:
        results = [reader_result(t) for t in self.tasks]
        results[0]["catalog"]["identifiers"] = [{"identifier": "RULE-9", "statement": "limit is 5"}]
        results[1]["catalog"]["identifiers"] = [{"identifier": "RULE-9", "statement": "limit is 10"}]
        pipeline.submit_reading(self.run.run_dir, results)
        outcome = pipeline.reconcile_reading(self.run.run_dir)
        self.assertEqual(1, outcome["identifier_conflicts"])
        reconciliation = json.loads((self.run.run_dir / "reading" / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(reconciliation["identifier_conflicts"][0]["statements"]))

    def test_reconciled_catalog_is_bound_into_the_design_record(self) -> None:
        outcome = read_everything(self.run)
        self.assertEqual("design", outcome["next_stage"])
        self.run.submit("design")
        manifest = json.loads((self.run.run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        design = next(e for e in manifest["stages"] if e["stage"] == "TEST_DESIGN")
        self.assertIn("reading.reconciliation.json", json.dumps(design))
        (self.run.run_dir / "stages" / "reading.reconciliation.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(Exception):
            pipeline.verify_manifest(self.run.run_dir / "run-manifest.json", require_publication=False)


class CatalogReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        start(self.run)
        read_everything(self.run)

    def test_unchanged_sources_are_reused_across_runs(self) -> None:
        second = start(self.run, run_id="second")
        self.assertEqual(len(self.run.pack["sources"]), second["reading_states"]["REUSED"])
        self.assertEqual("design", second["next_stage"])
        self.assertTrue((self.run.run_dir / "stages" / "reading.reconciliation.json").is_file())

    def test_only_the_changed_source_is_invalidated(self) -> None:
        changed = next(iter(self.run.pack["sources"]))
        (self.run.workspace / changed).write_text("changed content that alters the digest\n", encoding="utf-8")
        second = start(self.run, run_id="second")
        plan = task_plan(self.run)
        self.assertEqual([changed], [t["path"] for t in plan["tasks"] if t["state"] == "PLANNED"])
        self.assertEqual(len(self.run.pack["sources"]) - 1, second["reading_states"]["REUSED"])

    def test_a_role_change_invalidates_reuse(self) -> None:
        path = next(p for p, item in self.run.pack["sources"].items() if item["role"] != "FUNCTIONAL_AUTHORITY")
        start(self.run, run_id="second", roles={path: "TECHNICAL_CONTEXT"})
        states = {t["path"]: t["state"] for t in task_plan(self.run)["tasks"]}
        self.assertEqual("PLANNED", states[path])

    def test_frozen_runs_stay_immutable_when_later_runs_read(self) -> None:
        self.run.submit("design")
        self.run.submit("expansion")
        self.run.submit("procedures")
        pipeline.finalize_run(self.run.run_dir, ["JSON"])
        frozen = self.run.run_dir
        before = file_digest(frozen / "canonical-suite.json")
        start(self.run, run_id="later")
        self.assertEqual(before, file_digest(frozen / "canonical-suite.json"))


class SourceKeyTests(unittest.TestCase):
    def test_keys_are_stable_and_collision_safe(self) -> None:
        self.assertEqual(reading.source_key("foo/bar.py"), reading.source_key("foo\\bar.py"))
        self.assertNotEqual(reading.source_key("foo/bar.py"), reading.source_key("foo_bar.py"))
        self.assertNotEqual(reading.source_key("a/spec.md"), reading.source_key("b/spec.md"))


class EvidenceSnapshotTests(unittest.TestCase):
    def test_every_readable_source_is_snapshotted_once_per_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        catalog = json.loads((run.run_dir / "evidence" / "source-catalog.json").read_text(encoding="utf-8"))
        readable = [e for e in catalog["sources"] if e["status"] in {"READ", "TRANSCRIBED"}]
        self.assertEqual(len(readable), len(run.pack["sources"]))
        for entry in readable:
            self.assertTrue((run.run_dir / "evidence" / entry["text_ref"]).is_file())


if __name__ == "__main__":
    unittest.main()
