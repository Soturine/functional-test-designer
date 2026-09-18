from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from parallel_evidence import (  # noqa: E402
    EvidenceRecord,
    SourceAssignment,
    analyze_selected_sources,
)


class ParallelEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assignments = [
            SourceAssignment("requirements.md", "FUNCTIONAL_AUTHORITY", "requirements"),
            SourceAssignment("implementation.py", "IMPLEMENTATION_EVIDENCE", "implementation"),
            SourceAssignment("operator-guide.md", "TECHNICAL_CONTEXT", "guide"),
            SourceAssignment("settings.yaml", "OTHER_SELECTED", "settings"),
            SourceAssignment("existing-tests.md", "TEST_ASSET", "existing tests"),
        ]

    def test_selected_sources_fan_out_and_join_at_one_complete_barrier(self) -> None:
        barrier = threading.Barrier(len(self.assignments))

        def analyzer(assignment: SourceAssignment) -> list[EvidenceRecord]:
            barrier.wait(timeout=2)
            time.sleep(0.01)
            return [EvidenceRecord(
                source=assignment.source,
                source_role=assignment.source_role,
                source_ref=assignment.source_ref,
                source_excerpt_ref="line 1",
                observation_or_claim=f"Evidence from {assignment.source}",
            )]

        result = analyze_selected_sources(
            self.assignments,
            {item.source for item in self.assignments},
            analyzer,
            max_workers=5,
        )

        self.assertTrue(result.barrier_complete)
        self.assertEqual(5, result.metrics["source_analysis_workers_started"])
        self.assertEqual(5, result.metrics["source_analysis_workers_completed"])
        self.assertEqual(5, result.metrics["source_analysis_max_concurrency"])
        self.assertEqual(5, result.metrics["source_files_assigned"])
        self.assertEqual(0, result.metrics["duplicate_source_reads"])
        self.assertEqual(5, result.metrics["evidence_records_generated"])
        self.assertGreater(
            result.metrics["aggregate_worker_seconds"],
            result.metrics["stage_wall_clock_seconds"],
        )
        self.assertEqual(
            [item.source for item in self.assignments],
            [record.source for record in result.records],
        )

    def test_one_file_cannot_have_multiple_analysis_owners(self) -> None:
        assignments = [self.assignments[0], self.assignments[0]]

        with self.assertRaisesRegex(ValueError, "one analysis owner"):
            analyze_selected_sources(assignments, {"requirements.md"}, lambda _: [])

    def test_worker_cannot_read_an_unselected_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside selected scope"):
            analyze_selected_sources(
                [self.assignments[1]], {"requirements.md"}, lambda _: []
            )

    def test_worker_cannot_decide_normative_oracle_or_final_design(self) -> None:
        def analyzer(assignment: SourceAssignment) -> list[dict]:
            return [{
                "source": assignment.source,
                "source_role": assignment.source_role,
                "source_ref": assignment.source_ref,
                "source_excerpt_ref": "line 1",
                "observation_or_claim": "A worker observation.",
                "normative_oracle": "Worker-selected final truth.",
            }]

        with self.assertRaisesRegex(ValueError, "cannot decide final semantic fields"):
            analyze_selected_sources(
                [self.assignments[0]], {self.assignments[0].source}, analyzer
            )

    def test_role_fan_in_preserves_provenance(self) -> None:
        result = analyze_selected_sources(
            self.assignments[:2],
            {item.source for item in self.assignments[:2]},
            lambda assignment: [EvidenceRecord(
                source=assignment.source,
                source_role=assignment.source_role,
                source_ref=assignment.source_ref,
                source_excerpt_ref="line 2",
                observation_or_claim="Observed evidence.",
            )],
            max_workers=2,
        )

        by_role = result.records_by_role()

        self.assertEqual("requirements.md", by_role["FUNCTIONAL_AUTHORITY"][0].source)
        self.assertEqual("implementation.py", by_role["IMPLEMENTATION_EVIDENCE"][0].source)


if __name__ == "__main__":
    unittest.main()
