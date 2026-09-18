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
        self.assertEqual(21, len(DIAGNOSTICS.STAGE_NAMES))
        self.assertIn("coverage_extraction_audit", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("early_deduplication", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("markdown_render", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("source_coverage_audit", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("source_coverage_recovery", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("source_coverage_verification", DIAGNOSTICS.STAGE_NAMES)
        self.assertIn("cross_rf_audit", DIAGNOSTICS.STAGE_NAMES)
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

    def test_scenario_independence_metrics_and_warning_are_preserved(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "test_design_and_scenarios")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "test_design_and_scenarios",
            ["Reviewed every Coverage Point before conservative merging."],
            {
                "coverage_points": 6,
                "scenario_candidates_before_merge": 6,
                "scenario_merge_candidates": 1,
                "scenario_merges_applied": 1,
                "scenarios_after_merge": 5,
                "multi_cp_scenarios": 1,
                "possible_scenario_overcompression_warnings": 1,
            },
        )
        for name in DIAGNOSTICS.STAGE_NAMES:
            if name != "test_design_and_scenarios":
                DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for independence metric test."])

        document = DIAGNOSTICS.finish_run(self.metrics)

        self.assertEqual(6, document["totals"]["scenario_candidates_before_merge"])
        self.assertEqual(1, document["totals"]["scenario_merges_applied"])
        self.assertEqual(5, document["totals"]["scenarios_after_merge"])
        self.assertIn(
            "POSSIBLE_SCENARIO_OVERCOMPRESSION",
            {warning["code"] for warning in document["warnings"]},
        )

    def test_finish_requires_every_stage_to_be_addressed(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)

        with self.assertRaisesRegex(ValueError, "Finish or skip every diagnostic stage"):
            DIAGNOSTICS.finish_run(self.metrics)

    def test_metric_aggregation_does_not_double_generation_counts_and_preserves_arrays(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "scope_resolution")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "scope_resolution",
            ["Resolved synthetic scope."],
            {
                "selected_scope_roots": ["apps", "config", "docs/user"],
                "resolved_scope_paths": ["apps/a.py"],
                "files_opened": 1,
                "files_opened_outside_scope": 0,
            },
        )
        DIAGNOSTICS.begin_stage(self.metrics, "test_case_generation")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "test_case_generation",
            ["Generated cases in memory."],
            {"test_cases_generated": 58},
        )
        DIAGNOSTICS.begin_stage(self.metrics, "json_write")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "json_write",
            ["Serialized prepared cases."],
            {"individual_json_files_written": 58, "json_bytes_written": 4096},
        )
        DIAGNOSTICS.begin_stage(self.metrics, "validation")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "validation",
            ["Ran validator once."],
            {"validator_runs": 1},
        )
        for name in DIAGNOSTICS.STAGE_NAMES:
            if DIAGNOSTICS.stage(DIAGNOSTICS.read_document(self.metrics), name)["status"] == "pending":
                DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for aggregation test."])

        document = DIAGNOSTICS.finish_run(self.metrics)

        self.assertEqual(58, document["totals"]["test_cases_generated"])
        self.assertEqual(58, document["totals"]["individual_json_files_written"])
        self.assertEqual(1, document["totals"]["validator_runs"])
        self.assertEqual(["apps", "config", "docs/user"], document["totals"]["selected_scope_roots"])
        self.assertIsInstance(document["totals"]["selected_scope_roots"], list)
        self.assertEqual(document["totals"]["selected_scope_roots"], document["scope_proof"]["selected_scope_roots"])
        self.assertEqual("last", document["aggregation_strategies"]["test_cases_generated"])

    def test_unknown_metric_requires_an_explicit_aggregation_strategy(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "scope_resolution")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "scope_resolution",
            ["Recorded an unsupported metric."],
            {"mystery_metric": 1},
        )
        for name in DIAGNOSTICS.STAGE_NAMES[1:]:
            DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for strategy test."])

        with self.assertRaisesRegex(ValueError, "No aggregation strategy"):
            DIAGNOSTICS.finish_run(self.metrics)

    def test_execution_metrics_are_derived_from_real_cases_and_source_roles(self) -> None:
        totals = DIAGNOSTICS.output_totals(self.output)

        self.assertEqual(11, totals["test_cases"])
        self.assertEqual(2, totals["test_cases_with_multiple_steps"])
        self.assertEqual(9, totals["test_cases_with_one_step"])
        self.assertGreater(totals["average_steps_per_test_case"], 1)
        self.assertEqual(2, totals["test_cases_with_execution_enrichment"])
        self.assertEqual(2, totals["test_cases_with_multiple_source_roles"])
        self.assertEqual(11, totals["functional_authority_contributions"])
        self.assertEqual(1, totals["technical_context_contributions"])
        self.assertEqual(2, totals["implementation_evidence_contributions"])
        self.assertEqual(0, totals["test_asset_contributions"])
        self.assertEqual(23, totals["source_claims_identified"])
        self.assertEqual(0, totals["automatic_merges"])
        self.assertEqual(0, totals["automatic_removals"])
        self.assertEqual({"1": 9, "2": 1, "3": 1}, totals["step_count_histogram"])
        self.assertEqual(23, totals["atomic_source_claims_identified"])
        self.assertEqual(9, totals["multi_cp_scenarios"])

    def test_detailed_evidence_single_step_distribution_adds_non_blocking_warning(self) -> None:
        index = DIAGNOSTICS.read_document(self.output / "test-cases.json")
        for entry in index["test_cases"]:
            path = self.output / entry["file"]
            case = DIAGNOSTICS.read_document(path)
            case["steps"] = [case["steps"][-1] | {"step": 1}]
            DIAGNOSTICS.write_document(path, case)
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "test_case_generation")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "test_case_generation",
            ["Observed detailed execution evidence."],
            {"detailed_execution_evidence_available": True},
        )
        for name in DIAGNOSTICS.STAGE_NAMES:
            if name != "test_case_generation":
                DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for execution warning test."])

        document = DIAGNOSTICS.finish_run(self.metrics, self.output)

        warning_codes = {warning["code"] for warning in document["warnings"]}
        self.assertIn("POSSIBLE_EXECUTION_UNDER_SPECIFICATION", warning_codes)

    def test_abstract_action_detection_is_non_destructive(self) -> None:
        index = DIAGNOSTICS.read_document(self.output / "test-cases.json")
        path = self.output / index["test_cases"][0]["file"]
        case = DIAGNOSTICS.read_document(path)
        case["steps"][0]["action"] = "Execute the complete flow."
        DIAGNOSTICS.write_document(path, case)

        totals = DIAGNOSTICS.output_totals(self.output)

        self.assertEqual(1, totals["abstract_action_warnings"])
        self.assertEqual("Execute the complete flow.", DIAGNOSTICS.read_document(path)["steps"][0]["action"])

    def test_uniform_steps_warn_only_when_varied_paths_are_observed(self) -> None:
        index = DIAGNOSTICS.read_document(self.output / "test-cases.json")
        for entry in index["test_cases"]:
            path = self.output / entry["file"]
            case = DIAGNOSTICS.read_document(path)
            case["steps"] = [case["steps"][0] | {"step": 1}, case["steps"][-1] | {"step": 2}]
            DIAGNOSTICS.write_document(path, case)
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "execution_path_synthesis")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "execution_path_synthesis",
            ["Observed selected paths with different supported complexity."],
            {"varied_execution_paths_available": True},
        )
        for name in DIAGNOSTICS.STAGE_NAMES:
            if name != "execution_path_synthesis":
                DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for template-bias test."])

        document = DIAGNOSTICS.finish_run(self.metrics, self.output)

        self.assertTrue(document["totals"]["possible_step_template_bias"])
        self.assertIn("POSSIBLE_STEP_TEMPLATE_BIAS", {item["code"] for item in document["warnings"]})

    def test_compound_claim_and_multi_action_signals_are_non_blocking_warnings(self) -> None:
        index = DIAGNOSTICS.read_document(self.output / "test-cases.json")
        index["normative_clauses"][0]["normalized_claim"] = "Show status and record history."
        DIAGNOSTICS.write_document(self.output / "test-cases.json", index)
        case_path = self.output / index["test_cases"][0]["file"]
        case = DIAGNOSTICS.read_document(case_path)
        case["steps"][0]["action"] = "Open the item, select the state, enter a reason, then confirm."
        DIAGNOSTICS.write_document(case_path, case)
        DIAGNOSTICS.start_run(self.metrics)
        for name in DIAGNOSTICS.STAGE_NAMES:
            DIAGNOSTICS.skip_stage(self.metrics, name, ["Not needed for advisory-warning test."])

        document = DIAGNOSTICS.finish_run(self.metrics, self.output)
        warning_codes = {item["code"] for item in document["warnings"]}

        self.assertIn("POSSIBLE_COMPOUND_NORMATIVE_CLAIM", warning_codes)
        self.assertIn("POSSIBLE_MULTI_ACTION_STEP", warning_codes)


if __name__ == "__main__":
    unittest.main()
