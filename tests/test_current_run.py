"""The current validated run: recorded only when a canonical run is VALIDATED, verified again
whenever it is used, and always overridden by an explicit --run."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export  # noqa: E402
import azure_publish  # noqa: E402
import challenge as ch  # noqa: E402
import pipeline  # noqa: E402
import workflow  # noqa: E402
from support import PackRun  # noqa: E402
from test_azure_publish import ORG, FakeAzure  # noqa: E402


class CurrentRunTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.run.finalize(("JSON",))
        self.pointer = self.run.artifacts / ".ftd" / "current-run.json"

    def second_run(self, run_id: str, last_stage: str | None = "procedures") -> Path:
        result = pipeline.start_run(
            workspace=self.run.workspace, artifact_root=self.run.artifacts, run_id=run_id,
            sources_selected=[{"path": p, "role": i["role"]} for p, i in self.run.pack["sources"].items()],
            locale=self.run.pack.get("locale"), request_text=self.run.pack.get("request", ""),
            reading={"strategy": "SEQUENTIAL"})
        run_dir = Path(result["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            if last_stage is None:
                break
            pipeline.submit_stage(run_dir, stage, self.run.pack["stages"][stage])
            if stage == last_stage:
                break
        return run_dir


class RecordingTests(CurrentRunTestCase):
    def test_a_validated_run_becomes_current(self) -> None:
        current = json.loads(self.pointer.read_text(encoding="utf-8"))
        canonical = pipeline.read_canonical(self.run.run_dir / "canonical-suite.json")
        self.assertEqual((self.run.run_dir.name, str(self.run.run_dir), canonical["semantic_fingerprint"]),
                         (current["run_id"], current["run_dir"], current["canonical_digest"]))
        self.assertTrue(current["validated_at"])
        self.assertEqual(self.run.run_dir, pipeline.resolve_run(None, self.run.artifacts))

    def test_incomplete_and_failed_runs_never_replace_it(self) -> None:
        before = self.pointer.read_bytes()
        incomplete = self.second_run("incomplete", "design")
        with self.assertRaises(pipeline.IntegrityError):
            pipeline.finalize_run(incomplete, ["JSON"])  # a newer run failing to finalize
        self.second_run("started-only", None)
        self.assertEqual(before, self.pointer.read_bytes())
        self.assertEqual(self.run.run_dir, pipeline.resolve_run(None, self.run.artifacts))

    def test_a_chaos_run_never_replaces_it(self) -> None:
        before = self.pointer.read_bytes()
        ch.start_challenge(self.run.run_dir, "night", seeds=[])
        ch.submit_challenge(self.run.run_dir, "night", {"cases": [{
            "key": "H1", "title": "Two owners invite the last seat at once", "discovery": "MODEL_DERIVED",
            "rationale": "Racing invitations could exceed the seat limit.", "execution_tags": ["MANUAL"]}],
            "seed_dispositions": []})
        ch.finalize_challenge(self.run.run_dir, "night")
        self.assertEqual(before, self.pointer.read_bytes())

    def test_the_last_run_to_validate_is_current_whatever_the_folder_times(self) -> None:
        newer = self.second_run("zz-newer")
        pipeline.finalize_run(newer, ["JSON"])
        old_time = time.time() + 3600  # make the older folder look newest on disk
        os.utime(self.run.run_dir, (old_time, old_time))
        self.assertEqual(newer, pipeline.resolve_run(None, self.run.artifacts))


class ResolutionTests(CurrentRunTestCase):
    def test_an_explicit_run_always_wins(self) -> None:
        other = self.second_run("other")
        pipeline.finalize_run(other, ["JSON"])  # now current
        self.assertEqual(self.run.run_dir.resolve(), pipeline.resolve_run(self.run.run_dir, self.run.artifacts))
        self.assertEqual(self.run.run_dir, pipeline.resolve_run(self.run.run_dir.name, self.run.artifacts))
        with self.assertRaisesRegex(pipeline.IntegrityError, "neither a run directory nor a run id"):
            pipeline.resolve_run("no-such-run", self.run.artifacts)

    def test_a_missing_pointer_is_a_clear_error(self) -> None:
        self.pointer.unlink()
        with self.assertRaisesRegex(pipeline.IntegrityError, "no --run given and no current validated run"):
            pipeline.resolve_run(None, self.run.artifacts)

    def test_corrupt_or_stale_pointers_fail_safely(self) -> None:
        good = self.pointer.read_text(encoding="utf-8")
        for broken in ("{not json", json.dumps({"run_id": "x"}),
                       json.dumps({**json.loads(good), "canonical_digest": "0" * 64}),
                       json.dumps({**json.loads(good), "run_dir": str(self.second_run("unfinished", "design"))})):
            with self.subTest(pointer=broken[:40]):
                self.pointer.write_text(broken, encoding="utf-8")
                with self.assertRaisesRegex(pipeline.IntegrityError, "cannot be trusted"):
                    pipeline.resolve_run(None, self.run.artifacts)

    def test_a_tampered_current_run_is_refused(self) -> None:
        manifest = self.run.run_dir / "run-manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["stages"][0]["sha256"] = "0" * 64
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(pipeline.IntegrityError, "cannot be trusted"):
            pipeline.resolve_run(None, self.run.artifacts)


class CommandTests(CurrentRunTestCase):
    def cli(self, main, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_user_commands_work_without_run(self) -> None:
        root = str(self.run.artifacts)
        code, text = self.cli(workflow.main, ["azure", "--output-dir", root])
        self.assertEqual(0, code, text)
        self.assertEqual(0, json.loads(text)["live_azure_calls"])
        self.assertEqual(0, self.cli(workflow.main, ["check", "--output-dir", root])[0])
        self.assertEqual(0, self.cli(workflow.main, ["render", "--output-dir", root, "--output", "json"])[0])
        self.assertIn("findings", workflow.dispatch("ftd-check", output_dir=root))
        order = workflow.dispatch("ftd-chaos", output_dir=root)
        self.assertTrue(order)
        pipeline.verify_manifest(self.run.run_dir / "run-manifest.json")

    def test_azure_publish_prepare_shows_the_resolved_run_and_never_publishes(self) -> None:
        azure_export.convert_run(self.run.run_dir)
        fake = FakeAzure()
        with mock.patch.object(azure_publish, "remote_for", return_value=fake):
            code, text = self.cli(azure_publish.main, [
                "--prepare", "--output-dir", str(self.run.artifacts), "--organization", ORG,
                "--project", "Shop", "--plan", "Release"])
        self.assertEqual(0, code, text)
        digest = pipeline.read_canonical(self.run.run_dir / "canonical-suite.json")["semantic_fingerprint"]
        self.assertTrue(text.startswith(f"Run: {self.run.run_dir.name}\nCanonical digest: {digest}"))
        self.assertIn(f"Canonical digest: {digest}", text.split("Organization:", 1)[1])  # in the preview too
        self.assertEqual([], fake.writes())
        self.assertFalse((self.run.artifacts / "output" / "azure" / "publication-result.json").exists())

    def test_post_generation_passes_its_own_run_and_never_reads_the_pointer(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        result = pipeline.start_run(
            workspace=run.workspace, artifact_root=run.artifacts, run_id="gen",
            sources_selected=[{"path": p, "role": i["role"]} for p, i in run.pack["sources"].items()],
            locale=run.pack.get("locale"), request_text="", reading={"strategy": "SEQUENTIAL"},
            normalized_request={"guidance": [], "seeds": [], "source_order": [],
                                "effective": {"post_generation": ["CHAOS", "REFRESH_PUBLICATION", "AZURE_LOCAL_EXPORT"]}})
        run.run_dir = Path(result["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            run.submit(stage)
        with mock.patch.object(pipeline, "resolve_run", side_effect=AssertionError("pointer used")):
            outcome = pipeline.finalize_run(run.run_dir, ["JSON"])["post_generation"]
        self.assertIn(f'--run "{run.run_dir}"', outcome["next_actions"][0]["command"])


if __name__ == "__main__":
    unittest.main()
