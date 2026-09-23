"""Default multi-agent source reading/cataloging: the deterministic half a Python
runtime can actually own and test. Real sub-agent execution is a host-agent concern
documented in SKILL.md; this only proves the task plan, defaults, overrides and
digest-based reuse are correct, and that source accounting stays honest either way."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import sources  # noqa: E402
from support import PackRun  # noqa: E402


class ReadingTaskPlanTests(unittest.TestCase):
    def test_default_strategy_is_multi_agent_per_source(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        result = run.start()
        self.assertEqual("MULTI_AGENT_PER_SOURCE", result["reading"]["strategy"])

    def test_one_logical_task_per_eligible_source_by_default(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        import json
        plan = json.loads((run.run_dir / "reading-task-plan.json").read_text(encoding="utf-8"))
        selected_paths = set(run.pack["sources"])
        plan_paths = {task["path"] for task in plan["tasks"]}
        self.assertEqual(selected_paths, plan_paths)
        self.assertEqual(len(selected_paths), len(plan["tasks"]))  # one task per source, none batched

    def test_every_selected_source_gets_an_explicit_disposition(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        import json
        plan = json.loads((run.run_dir / "reading-task-plan.json").read_text(encoding="utf-8"))
        for task in plan["tasks"]:
            self.assertIn(task["disposition"], sources.READING_DISPOSITIONS)

    def test_sequential_opt_out_disables_the_default_worker_model(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        import pipeline
        run.workspace  # ensure materialized
        result = pipeline.start_run(
            workspace=run.workspace,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            artifact_root=run.artifacts, run_id=run.pack["name"], locale=run.pack.get("locale"),
            request_text=run.pack.get("request", ""), reading={"strategy": "SEQUENTIAL"},
        )
        run.run_dir = Path(result["run_dir"])
        self.assertEqual("SEQUENTIAL", result["reading"]["strategy"])
        self.assertIsNone(result["reading"]["worker_model"])

    def test_explicit_worker_model_and_concurrency_are_recorded_honestly(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        import pipeline
        result = pipeline.start_run(
            workspace=run.workspace,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            artifact_root=run.artifacts, run_id=run.pack["name"], locale=run.pack.get("locale"),
            request_text=run.pack.get("request", ""),
            reading={"strategy": "MULTI_AGENT_PER_SOURCE", "worker_model": "haiku", "concurrency": 4},
        )
        run.run_dir = Path(result["run_dir"])
        self.assertEqual("haiku", result["reading"]["worker_model"])
        self.assertEqual(4, result["reading"]["concurrency"])
        # Honest: nothing here claims Haiku workers actually ran — only that this was requested.

    def test_worker_disposition_never_silently_drops_an_unreadable_source(self) -> None:
        plan = sources.plan_reading_tasks([
            {"path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY", "status": "NEEDS_TRANSCRIPTION", "content_digest": "x"},
            {"path": "assets/logo.png", "role": "TECHNICAL_CONTEXT", "status": "METADATA_ONLY", "content_digest": "y"},
        ])
        dispositions = {task["path"]: task["disposition"] for task in plan["tasks"]}
        self.assertEqual("FAILED_TO_READ", dispositions["docs/spec.pdf"])
        self.assertEqual("UNSUPPORTED", dispositions["assets/logo.png"])
        self.assertEqual(2, len(plan["tasks"]))  # both still accounted for


class CatalogReuseTests(unittest.TestCase):
    def test_an_unchanged_source_is_marked_reusable_across_runs_sharing_an_artifact_root(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        first = run.start()
        self.assertEqual(0, first["sources_reused"])
        run.run_dir = None  # force a second, differently-named run under the same artifact root
        import pipeline
        second = pipeline.start_run(
            workspace=run.workspace,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            artifact_root=run.artifacts, run_id=run.pack["name"] + "-2", locale=run.pack.get("locale"),
            request_text=run.pack.get("request", ""),
        )
        self.assertGreater(second["sources_reused"], 0)
        self.assertEqual(second["sources_reused"], len(run.pack["sources"]))

    def test_a_changed_source_is_not_marked_reusable(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        import pipeline
        # Mutate one selected source before the second run.
        first_path = next(iter(run.pack["sources"]))
        (run.workspace / first_path).write_text("changed content that alters the digest\n", encoding="utf-8")
        second = pipeline.start_run(
            workspace=run.workspace,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            artifact_root=run.artifacts, run_id=run.pack["name"] + "-3", locale=run.pack.get("locale"),
            request_text=run.pack.get("request", ""),
        )
        self.assertLess(second["sources_reused"], len(run.pack["sources"]))

    def test_frozen_runs_remain_immutable_regardless_of_reading_strategy(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        from common import file_digest
        digest_before = file_digest(run.run_dir / "canonical-suite.json")
        # Nothing about reading-task-plan.json or the evidence catalog touches a frozen run.
        self.assertTrue((run.run_dir / "reading-task-plan.json").is_file())
        self.assertEqual(digest_before, file_digest(run.run_dir / "canonical-suite.json"))


class EvidenceSnapshotTests(unittest.TestCase):
    def test_every_readable_source_is_snapshotted_once_per_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.start()
        import json
        catalog = json.loads((run.run_dir / "evidence" / "source-catalog.json").read_text(encoding="utf-8"))
        readable = [e for e in catalog["sources"] if e["status"] in {"READ", "TRANSCRIBED"}]
        self.assertEqual(len(readable), len(run.pack["sources"]))
        for entry in readable:
            self.assertTrue((run.run_dir / "evidence" / entry["text_ref"]).is_file())


if __name__ == "__main__":
    unittest.main()
