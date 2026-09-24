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
        self.assertEqual(len(self.run.pack["sources"]), len(order["reader_assignments"]))  # 3 file selectors
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

    def test_an_empty_source_is_accounted_for_without_a_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = reading.plan([
                {"path": "pkg/__init__.py", "role": "IMPLEMENTATION_EVIDENCE", "status": "READ",
                 "content_digest": reading.EMPTY_DIGEST},
                {"path": "pkg/core.py", "role": "IMPLEMENTATION_EVIDENCE", "status": "READ", "content_digest": "z"},
            ], Path(temp), Path(temp) / "run")
        states = {task["path"]: task["state"] for task in plan["tasks"]}
        self.assertEqual({"pkg/__init__.py": "EMPTY", "pkg/core.py": "PLANNED"}, states)


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
        self.assertIn("no reader disposition", " ".join(caught.exception.errors))

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


class SelectorReaderTests(unittest.TestCase):
    """The user-declared selector is the reader unit; every physical file stays accounted."""

    SELECTED = [{"path": "docs/requirements.md", "role": "FUNCTIONAL_AUTHORITY"},
                {"path": "docs/rules.md", "role": "FUNCTIONAL_AUTHORITY"},
                {"path": "docs/manual.md", "role": "TECHNICAL_CONTEXT"},
                {"path": "src", "role": "IMPLEMENTATION_EVIDENCE"}]

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.workspace, self.artifacts = root / "ws", root / "artifacts"
        (self.workspace / "docs").mkdir(parents=True)
        (self.workspace / "src" / "core").mkdir(parents=True)
        (self.workspace / "docs" / "requirements.md").write_text("# Spec\n\nREQ-1 - Save\nThe user saves a record.\n", encoding="utf-8")
        (self.workspace / "docs" / "rules.md").write_text("RULE-1 - Unique\nNames are unique.\n", encoding="utf-8")
        (self.workspace / "docs" / "manual.md").write_text("# Manual\nOpen Records and press Save.\n", encoding="utf-8")
        for name in ("a", "b", "c"):
            (self.workspace / "src" / f"{name}.py").write_text(f"def {name}():\n    return 1\n", encoding="utf-8")
        (self.workspace / "src" / "core" / "d.py").write_text("def d():\n    return 2\n", encoding="utf-8")

    def start(self, selected, run_id="r", **reading_opts):
        result = pipeline.start_run(workspace=self.workspace, sources_selected=selected, artifact_root=self.artifacts,
                                    run_id=run_id, reading=reading_opts or None)
        run_dir = Path(result["run_dir"])
        return result, run_dir, json.loads((run_dir / "reading" / "task-plan.json").read_text(encoding="utf-8"))

    def selector_result(self, plan, sid, files=None, **over):
        tasks = [t for t in plan["tasks"] if t["selector_id"] == sid and t["state"] == "PLANNED"]
        files = tasks if files is None else files
        result = {"selector_id": sid, "reader": {"role": reading.READER_ROLE, "model": "test-double"},
                  "catalog": {"operations": [{"file": files[0]["path"], "fact": "defines a function"}]},
                  "files": [{"source_key": t["source_key"], "content_digest": t["content_digest"], "status": "INSPECTED"}
                            for t in files]}
        result.update(over)
        return result

    def sid(self, plan, path):
        return next(s["selector_id"] for s in plan["selectors"] if s["path"] == path)

    def test_three_files_and_one_directory_are_four_reader_responsibilities(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        order = json.loads((run_dir / "work-order.json").read_text(encoding="utf-8"))
        self.assertEqual(4, len(plan["selectors"]))
        self.assertEqual(4, len(order["reader_assignments"]))
        src = next(a for a in order["reader_assignments"] if a["selector_path"] == "src")
        self.assertEqual(4, src["files_total"])  # every physical file under src/ is in the ledger
        self.assertEqual(7, len(plan["tasks"]))

    def test_one_file_and_one_directory_are_two_reader_responsibilities(self) -> None:
        _, _, plan = self.start([self.SELECTED[0], {"path": "src", "role": "IMPLEMENTATION_EVIDENCE"}])
        self.assertEqual(2, len(reading.assignments(plan)))

    def test_a_large_directory_stays_one_selector_with_every_file_accounted(self) -> None:
        for n in range(100):
            (self.workspace / "src" / f"m{n:03d}.py").write_text(f"X{n} = {n}\n", encoding="utf-8")
        _, _, plan = self.start([self.SELECTED[0], self.SELECTED[3]])
        self.assertEqual(2, len(plan["selectors"]))
        src = next(s for s in plan["selectors"] if s["path"] == "src")
        self.assertEqual(104, len(src["files"]))
        self.assertEqual(105, len(plan["tasks"]))

    def test_a_directory_result_missing_one_file_cannot_reconcile(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        results = [self.selector_result(plan, s["selector_id"]) for s in plan["selectors"]]
        src = next(r for r in results if r["selector_id"] == self.sid(plan, "src"))
        src["files"].pop()  # silently omits one physical file
        pipeline.submit_reading(run_dir, results)
        with self.assertRaises(StageError):
            pipeline.reconcile_reading(run_dir)
        with self.assertRaises(pipeline.IntegrityError):
            pipeline.submit_stage(run_dir, "design", {})

    def test_complete_selector_results_reconcile_with_file_provenance(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        pipeline.submit_reading(run_dir, [self.selector_result(plan, s["selector_id"]) for s in plan["selectors"]])
        outcome = pipeline.reconcile_reading(run_dir)
        self.assertEqual("design", outcome["next_stage"])
        rec = json.loads((run_dir / "reading" / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertTrue(all(s["complete"] for s in rec["selectors"]))
        self.assertEqual(0, rec["telemetry"]["unaccounted_files"])
        self.assertIsNone(rec["telemetry"]["reader_model_host_verified"])
        src = next(s for s in rec["selectors"] if s["path"] == "src")
        catalog = json.loads((run_dir / "reading" / src["catalog_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(4, len(catalog["files"]))
        self.assertTrue(all(item["file"].startswith("src/") for item in catalog["catalog"]["operations"]))

    def test_a_reader_cannot_account_for_or_cite_files_outside_its_selector(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        manual = self.sid(plan, "docs/manual.md")
        foreign = [t for t in plan["tasks"] if t["path"] == "src/a.py"]
        with self.assertRaisesRegex(StageError, "does not own"):
            pipeline.submit_reading(run_dir, [self.selector_result(plan, manual, files=foreign)])
        bad = self.selector_result(plan, manual, catalog={"operations": [{"file": "src/a.py", "fact": "x"}]})
        with self.assertRaisesRegex(StageError, "does not own"):
            pipeline.submit_reading(run_dir, [bad])

    def test_readers_cannot_change_the_selector_role_or_decide_semantics(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        src = self.sid(plan, "src")
        with self.assertRaisesRegex(StageError, "role"):
            pipeline.submit_reading(run_dir, [self.selector_result(plan, src, role="FUNCTIONAL_AUTHORITY")])
        with self.assertRaisesRegex(StageError, "main-model decisions"):
            pipeline.submit_reading(run_dir, [self.selector_result(plan, src, catalog={"findings": ["x"]})])

    def test_overlapping_selectors_never_double_own_a_file(self) -> None:
        _, _, plan = self.start([self.SELECTED[0], {"path": "src", "role": "IMPLEMENTATION_EVIDENCE"},
                                 {"path": "src/core", "role": "IMPLEMENTATION_EVIDENCE"}])
        owners = {}
        for s in plan["selectors"]:
            for key in s["files"]:
                self.assertNotIn(key, owners)
                owners[key] = s["path"]
        d = next(t["source_key"] for t in plan["tasks"] if t["path"] == "src/core/d.py")
        self.assertEqual("src/core", owners[d])  # the most specific selector owns it

    def test_source_order_is_kept_independently_of_role(self) -> None:
        _, _, plan = self.start([self.SELECTED[3], self.SELECTED[2], self.SELECTED[0]])
        self.assertEqual(["src", "docs/manual.md", "docs/requirements.md"],
                         [s["path"] for s in sorted(plan["selectors"], key=lambda s: s["order"])])

    def test_more_selectors_than_the_limit_are_queued_in_waves(self) -> None:
        for n in range(10):
            (self.workspace / "docs" / f"note{n}.md").write_text(f"note {n}\n", encoding="utf-8")
        selected = [self.SELECTED[0]] + [{"path": f"docs/note{n}.md", "role": "TECHNICAL_CONTEXT"} for n in range(10)]
        _, _, plan = self.start(selected)
        self.assertEqual(reading.DEFAULT_CONCURRENCY, plan["concurrency"])
        self.assertEqual([1] * 8 + [2] * 3, [a["wave"] for a in reading.assignments(plan)])
        _, _, explicit = self.start(selected, run_id="four", concurrency=4)
        self.assertEqual(3, max(a["wave"] for a in reading.assignments(explicit)))
        _, _, sequential = self.start(selected, run_id="seq", strategy="SEQUENTIAL")
        self.assertEqual([], reading.assignments(sequential))

    def test_internal_shards_reconcile_into_one_selector_catalog(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        src = next(s for s in plan["selectors"] if s["path"] == "src")
        files = [t for t in plan["tasks"] if t["selector_id"] == src["selector_id"]]
        others = [self.selector_result(plan, s["selector_id"]) for s in plan["selectors"] if s is not src]
        pipeline.submit_reading(run_dir, others + [self.selector_result(plan, src["selector_id"], files=files[:2], shard="1")])
        with self.assertRaises(StageError):
            pipeline.reconcile_reading(run_dir)  # shard 2 still missing
        pipeline.submit_reading(run_dir, [self.selector_result(plan, src["selector_id"], files=files[2:], shard="2")])
        pipeline.reconcile_reading(run_dir)
        full = json.loads((run_dir / "reading" / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual({src["selector_id"]: 2}, full["telemetry"]["internal_shards_used"])
        self.assertEqual(1, sum(1 for s in full["selectors"] if s["path"] == "src"))

    def test_only_changed_files_under_a_selector_are_read_again(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        results = []
        for s in plan["selectors"]:
            r = self.selector_result(plan, s["selector_id"])
            for f in r["files"]:
                f.update(status="CATALOGED", catalog={"headings": ["h"]})
            results.append(r)
        pipeline.submit_reading(run_dir, results)
        pipeline.reconcile_reading(run_dir)
        (self.workspace / "src" / "b.py").write_text("def b():\n    return 42\n", encoding="utf-8")
        _, _, second = self.start(self.SELECTED, run_id="second")
        states = {t["path"]: t["state"] for t in second["tasks"]}
        self.assertEqual("PLANNED", states["src/b.py"])
        self.assertEqual({"REUSED"}, {states[p] for p in ("src/a.py", "src/c.py", "src/core/d.py")})
        src = next(a for a in reading.assignments(second) if a["selector_path"] == "src")
        self.assertEqual(["src/b.py"], [t["path"] for t in src["files_pending"]])

    def test_a_plan_from_before_selectors_is_upgraded_without_rereading(self) -> None:
        _, run_dir, plan = self.start(self.SELECTED)
        legacy = {k: v for k, v in plan.items() if k != "selectors"}
        for t in legacy["tasks"]:
            t.pop("selector_id")
        legacy["tasks"][0]["state"] = "CATALOGED"
        (run_dir / "reading" / "task-plan.json").write_text(json.dumps(legacy), encoding="utf-8")
        self.start(self.SELECTED)  # same sources: resumes and upgrades in place
        upgraded = json.loads((run_dir / "reading" / "task-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(4, len(upgraded["selectors"]))
        self.assertEqual("CATALOGED", upgraded["tasks"][0]["state"])
        self.assertEqual("SELECTOR_OWNERSHIP_ATTACHED", upgraded["history"][0]["event"])


class HostFileTests(unittest.TestCase):
    def test_json_written_with_a_utf8_bom_is_accepted(self) -> None:
        from common import read_json
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"status": "CATALOGED"}).encode("utf-8"))
            self.assertEqual({"status": "CATALOGED"}, read_json(path))


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
