"""Mutate a known-good canonical run and assert the relevant gate rejects it.

Accepting a good suite proves nothing on its own. These tests take a canonical
run that validates, break exactly one thing, and require a specific validator or
audit to notice.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_state import OutputSelection, read_canonical_suite, render_selected_outputs  # noqa: E402
from run_operational_benchmarks import load_pack, run_pack  # noqa: E402
from semantic_regression import fingerprint  # noqa: E402
from validate_output import validate  # noqa: E402


PACKS = ROOT / "benchmarks" / "operational-workflows"


class CanonicalMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        root = Path(cls._temporary.name)
        pack = load_pack(PACKS / "benchmark-a.json")
        result = run_pack(pack, root, root / "artifacts")
        cls.canonical = read_canonical_suite(Path(result["canonical_path"]))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def materialize(self, canonical: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "test-cases").mkdir()
            (workspace / "test-cases.json").write_text(
                json.dumps(canonical["index"], indent=2), encoding="utf-8")
            (workspace / "questions.json").write_text(
                json.dumps(canonical["questions"], indent=2), encoding="utf-8")
            cases = {item["id"]: item for item in canonical["cases"]}
            for entry in canonical["index"]["test_cases"]:
                (workspace / entry["file"]).write_text(
                    json.dumps(cases[entry["id"]], indent=2), encoding="utf-8")
            return validate(workspace)

    def mutated(self) -> dict:
        return copy.deepcopy(self.canonical)

    def test_the_unmutated_canonical_run_validates(self) -> None:
        self.assertEqual([], self.materialize(self.canonical))

    def test_deleting_an_atomic_clause_is_detected(self) -> None:
        canonical = self.mutated()
        del canonical["index"]["normative_clauses"][3]
        self.assertTrue(self.materialize(canonical))

    def test_merging_two_coverage_points_is_detected(self) -> None:
        canonical = self.mutated()
        points = canonical["index"]["coverage_points"]
        points[0]["clause_refs"] = points[0]["clause_refs"] + points[1]["clause_refs"]
        del points[1]
        self.assertTrue(self.materialize(canonical))

    def test_changing_a_requirement_ref_is_detected(self) -> None:
        canonical = self.mutated()
        canonical["index"]["coverage_points"][0]["requirement_ref"] = "REQ-404"
        self.assertTrue(self.materialize(canonical))

    def test_setting_ready_despite_a_procedure_gap_is_detected(self) -> None:
        canonical = self.mutated()
        case = canonical["cases"][0]
        case["status"] = "READY"
        case["steps"][0]["needs_clarification"] = True
        errors = self.materialize(canonical)
        self.assertTrue(errors)

    def test_emitting_a_subtest_is_detected(self) -> None:
        canonical = self.mutated()
        canonical["cases"][0]["subtests"] = [{"id": "TC-001-a"}]
        self.assertTrue(self.materialize(canonical))

    def test_removing_a_question_breaks_the_semantic_fingerprint(self) -> None:
        canonical = self.mutated()
        del canonical["questions"]["questions"][0]
        expected = fingerprint({
            "index": canonical["index"], "questions": canonical["questions"],
            "cases": canonical["cases"],
        })
        self.assertNotEqual(canonical["semantic_fingerprint"], expected)

    def test_removing_a_finding_breaks_the_semantic_fingerprint(self) -> None:
        canonical = self.mutated()
        canonical["index"]["findings"] = []
        canonical["index"]["coverage_points"][0]["statement"] = "mutated"
        expected = fingerprint({
            "index": canonical["index"], "questions": canonical["questions"],
            "cases": canonical["cases"],
        })
        self.assertNotEqual(canonical["semantic_fingerprint"], expected)

    def test_a_tampered_canonical_state_cannot_be_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self.mutated()
            canonical["cases"][0]["title"] = "Silently renamed after the freeze"
            path = root / "canonical-suite.json"
            path.write_text(json.dumps(canonical, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                render_selected_outputs(path, root, OutputSelection.normalize(["JSON"]))


class BenchmarkInvariantTests(unittest.TestCase):
    def test_every_benchmark_pack_meets_its_semantic_invariants(self) -> None:
        from run_operational_benchmarks import available_packs, evaluate

        packs = available_packs()
        self.assertGreaterEqual(len(packs), 4)
        for path in packs:
            pack = load_pack(path)
            with self.subTest(pack=pack["id"]), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                report = evaluate(pack, run_pack(pack, root, root / "artifacts"))
                self.assertEqual([], report["violations"])


if __name__ == "__main__":
    unittest.main()
