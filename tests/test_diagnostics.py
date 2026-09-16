from __future__ import annotations

import importlib.util
import shutil
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIAGNOSTICS = load_script("diagnostics")
VALIDATOR = load_script("validate_output")


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output = self.root / "output"
        self.metrics = self.root / "diagnostics" / "run-metrics.json"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_diagnostics_records_real_macro_timing_without_affecting_validator(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "scope_resolution")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "scope_resolution",
            ["Resolved explicitly selected synthetic sources."],
            {
                "selected_scope_roots": ["examples/requirements.md"],
                "resolved_scope_paths": ["examples/requirements.md"],
                "files_opened": 1,
                "files_opened_outside_scope": 0,
                "files_skipped_out_of_scope": 2,
                "source_reads": 1,
                "source_rereads": 0,
                "temporary_files_created": 0,
            },
        )
        for name in DIAGNOSTICS.STAGE_NAMES[1:]:
            DIAGNOSTICS.skip_stage(self.metrics, name, ["Not exercised by this helper unit test."])
        document = DIAGNOSTICS.finish_run(
            self.metrics,
            self.output,
            ["Measure a complete synthetic agent run before changing the workflow."],
        )

        scope_stage = document["stages"][0]
        self.assertTrue(scope_stage["timing_available"])
        self.assertIsInstance(scope_stage["elapsed_seconds"], float)
        self.assertGreaterEqual(scope_stage["elapsed_seconds"], 0)
        self.assertNotIn("mode", document["run"])
        self.assertIn("unattributed_seconds", document["run"])
        self.assertIn("unattributed_percent", document["run"])
        self.assertEqual(1, document["scope_proof"]["files_opened"])
        self.assertEqual(0, document["scope_proof"]["files_opened_outside_scope"])
        self.assertEqual(0, document["scope_proof"]["source_rereads"])
        self.assertFalse(document["scope_proof"]["scope_violation"])
        self.assertEqual(11, document["totals"]["test_cases"])
        self.assertEqual(11, document["totals"]["markdown_files"])
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_v12_stage_order_has_audit_deduplication_and_markdown(self) -> None:
        self.assertEqual(15, len(DIAGNOSTICS.STAGE_NAMES))
        self.assertIn("coverage_extraction_audit", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("early_deduplication", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("markdown_render", DIAGNOSTICS.STAGE_NAMES)
        self.assertNotIn("test_data_design", DIAGNOSTICS.STAGE_NAMES)

    def test_stage_timer_wraps_work_between_begin_and_end(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "scope_resolution")
        time.sleep(0.01)
        document = DIAGNOSTICS.end_stage(
            self.metrics,
            "scope_resolution",
            ["Performed synthetic work while the stage timer was active."],
        )

        self.assertGreaterEqual(document["stages"][0]["elapsed_seconds"], 0.005)

    def test_high_unattributed_time_adds_warning_without_failing(self) -> None:
        document = DIAGNOSTICS.start_run(self.metrics)
        started = DIAGNOSTICS.parse_timestamp(document["run"]["started_at"])
        document["run"]["started_at"] = DIAGNOSTICS.timestamp(started - timedelta(seconds=2))
        DIAGNOSTICS.write_document(self.metrics, document)
        for name in DIAGNOSTICS.STAGE_NAMES:
            DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for warning test."])

        document = DIAGNOSTICS.finish_run(self.metrics)

        self.assertGreater(document["run"]["unattributed_percent"], 20)
        self.assertEqual("HIGH_UNATTRIBUTED_TIME", document["warnings"][0]["code"])

    def test_deduplication_metrics_are_preserved_when_observed(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "early_deduplication")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "early_deduplication",
            ["Removed one exact semantic duplicate."],
            {
                "scenario_candidates": 4,
                "scenarios_after_dedup": 3,
                "independent_scenarios_preserved": 3,
                "semantic_duplicates_removed": 1,
            },
        )
        for name in DIAGNOSTICS.STAGE_NAMES:
            if name != "early_deduplication":
                DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for metric test."])

        document = DIAGNOSTICS.finish_run(self.metrics)

        self.assertEqual(4, document["totals"]["scenario_candidates"])
        self.assertEqual(3, document["totals"]["independent_scenarios_preserved"])
        self.assertEqual(1, document["totals"]["semantic_duplicates_removed"])

    def test_finish_requires_every_stage_to_be_addressed(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)

        with self.assertRaisesRegex(ValueError, "Finish or skip every diagnostic stage"):
            DIAGNOSTICS.finish_run(self.metrics)


if __name__ == "__main__":
    unittest.main()
