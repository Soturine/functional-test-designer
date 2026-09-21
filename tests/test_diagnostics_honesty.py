"""Diagnostics describe the whole real run and never fabricate what was not observed."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_operational_benchmarks import load_pack, run_pack  # noqa: E402


PACKS = ROOT / "benchmarks" / "operational-workflows"
REQUIRED_METRICS = (
    "resolved_selected_sources", "sources_inspected_content", "sources_metadata_only",
    "sources_irrelevant_with_reason", "sources_failed", "source_read_telemetry_available",
    "functional_authority_source_behaviors", "primary_atomic_claims",
    "independent_review_source_behaviors", "source_behavior_gaps",
    "test_files_selected", "test_functions_inventory_count", "test_asset_business_behaviors",
    "test_asset_technical_only_behaviors", "test_asset_missing_dispositions",
    "scenario_opportunities", "adversarial_opportunities", "negative_opportunities",
    "operator_error_opportunities", "resilience_opportunities", "recovery_opportunities",
    "concurrency_opportunities", "e2e_opportunities",
    "one_step_cases", "legitimate_one_step_cases", "path_compression_warnings",
    "cases_missing_setup_acquisition", "cases_missing_procedural_provenance",
    "human_execution_ready", "human_execution_not_ready",
    "automation_execution_ready", "automation_execution_not_ready",
)


class DiagnosticsHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        root = Path(cls._temporary.name)
        pack = load_pack(PACKS / "benchmark-a.json")
        result = run_pack(pack, root, root / "artifacts")
        cls.diagnostics = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
        cls.raw = Path(result["diagnostics"]).read_text(encoding="utf-8")
        cls.pack = pack

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_every_required_metric_is_reported(self) -> None:
        missing = [name for name in REQUIRED_METRICS if name not in self.diagnostics]
        self.assertEqual([], missing)

    def test_unobservable_read_telemetry_is_null_not_zero(self) -> None:
        self.assertFalse(self.diagnostics["source_read_telemetry_available"])
        for name in ("source_reads", "source_rereads", "source_max_concurrency",
                     "agent_reasoning_seconds"):
            with self.subTest(metric=name):
                self.assertIsNone(self.diagnostics[name])

    def test_run_wall_clock_covers_more_than_the_attributed_stages(self) -> None:
        self.assertGreaterEqual(
            self.diagnostics["run_wall_clock_seconds"],
            self.diagnostics["attributed_stage_seconds"],
        )
        self.assertGreaterEqual(self.diagnostics["unattributed_seconds"], 0.0)

    def test_diagnostics_are_initialized_before_the_expensive_analysis(self) -> None:
        self.assertEqual("scope_resolution", self.diagnostics["phases"][0]["name"])
        self.assertEqual("rendering", self.diagnostics["phases"][-1]["name"])

    def test_every_checkpoint_of_the_real_path_is_recorded(self) -> None:
        created = {
            item["checkpoint"] for item in self.diagnostics["checkpoint_events"]
            if item["event"] == "created"
        }
        self.assertEqual(
            {
                "SCOPE_RESOLVED", "SOURCE_ACCOUNTING_COMPLETE", "EVIDENCE_BARRIER_COMPLETE",
                "SOURCE_REVIEW_COMPLETE", "SOURCE_ATOMICITY_COMPLETE",
                "OPPORTUNITY_AUDIT_COMPLETE", "SCENARIOS_FROZEN", "PROCEDURAL_COMPLETE",
                "VALIDATED",
            },
            created,
        )

    def test_diagnostics_never_copy_selected_source_content(self) -> None:
        for content in self.pack["files"].values():
            for line in content.splitlines():
                stripped = line.strip("# -").strip()
                if len(stripped) > 30:
                    with self.subTest(line=stripped[:40]):
                        self.assertNotIn(stripped, self.raw)

    def test_readiness_counts_are_reported_rather_than_optimized_to_one_hundred(self) -> None:
        total = (
            self.diagnostics["human_execution_ready"]
            + self.diagnostics["human_execution_not_ready"]
        )
        self.assertEqual(self.pack["expected_invariants"]["test_cases_exact"], total)
        self.assertEqual(
            total,
            self.diagnostics["automation_execution_ready"]
            + self.diagnostics["automation_execution_not_ready"],
        )


if __name__ == "__main__":
    unittest.main()
