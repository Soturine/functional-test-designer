"""Optional post-generation actions from the instructions file (read semantically by the host):
canonical finalize → optional chaos → refresh publication → optional local Azure export → stop.
Remote publication is never automatic."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_publish  # noqa: E402
import challenge as ch  # noqa: E402
import instructions  # noqa: E402
import pipeline  # noqa: E402
import workflow  # noqa: E402
from support import PackRun  # noqa: E402


def no_remote():
    """Any attempt to publish or open a connection fails the test."""
    boom = AssertionError("remote publication or network access attempted")
    return [mock.patch.object(azure_publish, "prepare", side_effect=boom),
            mock.patch.object(azure_publish, "apply", side_effect=boom),
            mock.patch("urllib.request.urlopen", side_effect=boom)]


class RequestContractTests(unittest.TestCase):
    def test_only_local_follow_ups_are_accepted(self) -> None:
        ok = instructions.validate_request({"post_generation": ["CHAOS", "AZURE_LOCAL_EXPORT"]}, None)
        self.assertEqual([], ok)
        errors = instructions.validate_request({"post_generation": ["AZURE_PUBLISH"]}, None)
        self.assertTrue(any("remote publication is never automatic" in e for e in errors))
        self.assertTrue(instructions.validate_request({"post_generation": ["DEPLOY"]}, None))

    def test_refreshing_the_publication_is_derived_never_requested(self) -> None:
        errors = instructions.validate_request({"post_generation": ["CHAOS", "REFRESH_PUBLICATION"]}, None)
        self.assertTrue(any("derived automatically after a chaos pass" in e for e in errors))
        self.assertEqual(["CHAOS", "REFRESH_PUBLICATION"], instructions.normalize_post_generation(["CHAOS"]))
        self.assertEqual(["AZURE_LOCAL_EXPORT"], instructions.normalize_post_generation(["AZURE_LOCAL_EXPORT"]))

    def test_the_host_is_told_to_read_any_wording_and_keep_azure_local(self) -> None:
        document = {"path": "x/instructions.md", "digest": "d", "text": "## Depois da run\n- fazer chaos\n- converter azure\n"}
        contract = instructions.normalization_order(document, {}, command="gen")["contract"]["post_generation"]
        self.assertIn("in any wording or heading", contract)
        self.assertIn("Any Azure wording means AZURE_LOCAL_EXPORT", contract)
        self.assertIn("remote publication is never a post-generation action", contract)

    def test_the_current_request_overrides_the_file(self) -> None:
        request = {"post_generation": ["CHAOS", "AZURE_LOCAL_EXPORT"]}
        from_file = instructions.effective_request(request, {}, default_output_dir=Path("out"))
        self.assertEqual(["CHAOS", "REFRESH_PUBLICATION", "AZURE_LOCAL_EXPORT"], from_file["post_generation"])
        self.assertEqual("INSTRUCTIONS", from_file["provenance"]["post_generation"])
        cli = instructions.effective_request(request, {"post_generation": workflow.parse_after("none")},
                                             default_output_dir=Path("out"))
        self.assertEqual([], cli["post_generation"])  # an explicit "none" wins over the file
        self.assertEqual(["AZURE_LOCAL_EXPORT"], workflow.parse_after("azure"))
        with self.assertRaisesRegex(ValueError, "remote publication is never automatic"):
            workflow.parse_after("chaos,publish")


class OrchestrationTests(unittest.TestCase):
    def run_with(self, actions):
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        result = pipeline.start_run(
            workspace=run.workspace, artifact_root=run.artifacts, run_id=run.pack["name"],
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            locale=run.pack.get("locale"), request_text=run.pack.get("request", ""), reading={"strategy": "SEQUENTIAL"},
            normalized_request={"guidance": [], "seeds": [], "source_order": [],
                                "effective": {"post_generation": instructions.normalize_post_generation(actions)}})
        run.run_dir = Path(result["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            run.submit(stage)
        return run

    def package(self, run) -> Path:
        return run.artifacts / "output" / "azure" / "azure-export-package.json"

    def test_azure_alone_exports_the_local_package_right_after_finalize_and_stops(self) -> None:
        run = self.run_with(["AZURE_LOCAL_EXPORT"])
        patches = no_remote()
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        result = pipeline.finalize_run(run.run_dir, ["JSON"])["post_generation"]
        self.assertEqual(["STOP"], result["next_actions"])
        self.assertEqual(0, result["done"]["AZURE_LOCAL_EXPORT"]["live_azure_calls"])
        self.assertTrue(self.package(run).is_file())

    def test_chaos_then_refresh_then_local_azure_then_stop(self) -> None:
        run = self.run_with(["CHAOS", "AZURE_LOCAL_EXPORT"])
        patches = no_remote()
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        result = pipeline.finalize_run(run.run_dir, ["JSON", "MARKDOWN", "HTML"])["post_generation"]
        self.assertEqual("CHAOS", result["next_actions"][0]["action"])
        self.assertEqual("STOP", result["next_actions"][-1])
        self.assertFalse(self.package(run).exists())  # the export waits for the chaos pass
        ch.start_challenge(run.run_dir, "night", seeds=[])
        ch.submit_challenge(run.run_dir, "night", {"cases": [{
            "key": "H1", "title": "Two owners invite the last seat at once", "discovery": "MODEL_DERIVED",
            "rationale": "Racing invitations could exceed the seat limit.", "execution_tags": ["MANUAL"]}],
            "seed_dispositions": []})
        outcome = ch.finalize_challenge(run.run_dir, "night")
        self.assertEqual([run.run_dir.name], outcome["publication_refreshed"])
        self.assertEqual(1, outcome["azure_local_export"][0]["chaos_test_cases"])
        self.assertTrue(self.package(run).is_file())
        self.assertIn(b"night:CH-001", (run.artifacts / "output" / "organization.json").read_bytes())
        self.assertFalse((run.artifacts / "output" / "azure" / "publication-plan.json").exists())

    def test_without_follow_ups_nothing_else_happens(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        result = run.finalize(("JSON",))["post_generation"]
        self.assertEqual({"requested": [], "done": {}, "next_actions": ["STOP"]}, result)
        self.assertFalse(self.package(run).exists())


if __name__ == "__main__":
    unittest.main()
