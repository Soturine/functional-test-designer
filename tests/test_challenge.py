"""Post-suite challenge: canonical immutability, seed semantics and grounding."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from common import StageError, file_digest  # noqa: E402
import challenge as ch  # noqa: E402
from support import PackRun  # noqa: E402


def _write_seed(text: str) -> Path:
    directory = Path(tempfile.mkdtemp())
    path = directory / "qa-ideas.md"
    path.write_text(text, encoding="utf-8")
    return path


def _case(**over):
    base = {
        "key": "H1", "title": "A concurrent action on the same record",
        "discovery": "MODEL_DERIVED",
        "rationale": "Two actors racing on the same record could corrupt or duplicate its state.",
        "execution_tags": ["MANUAL"],
    }
    base.update(over)
    return base


class PostSuiteRequirementTests(unittest.TestCase):
    def test_challenge_rejects_an_unfinished_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.through("design")
        with self.assertRaises(ch.ChallengeError):
            ch.start_challenge(run.run_dir, "early", seeds=[])

    def test_finalized_run_can_be_challenged_and_reused(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        start = ch.start_challenge(run.run_dir, "first", seeds=[])
        self.assertTrue(Path(start["work_order"]).is_file())

    def test_same_frozen_run_supports_multiple_independent_challenge_runs(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "pass-1", seeds=[], focus="operator error")
        ch.start_challenge(run.run_dir, "pass-2", seeds=[], focus="physical devices")
        self.assertTrue((run.run_dir / "challenges" / "pass-1").is_dir())
        self.assertTrue((run.run_dir / "challenges" / "pass-2").is_dir())


class CanonicalImmutabilityTests(unittest.TestCase):
    def test_challenge_never_mutates_the_parent_canonical_or_manifest(self) -> None:
        run = PackRun("iot-line-monitoring")
        self.addCleanup(run.close)
        run.finalize()
        canonical_before = file_digest(run.run_dir / "canonical-suite.json")
        manifest_before = (run.run_dir / "run-manifest.json").read_text(encoding="utf-8")
        tc_count_before = len(run.output("test-cases.json")["test_cases"])

        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            evidence_refs=[{"source": source, "reference": "n/a"}],
            preconditions=["A line sensor is actively streaming readings."],
            steps=[{"action": "Power off the sensor mid-reading.",
                    "expected_result": "The reading is marked incomplete."}],
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        ch.finalize_challenge(run.run_dir, "run")

        self.assertEqual(canonical_before, file_digest(run.run_dir / "canonical-suite.json"))
        self.assertEqual(manifest_before, (run.run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(tc_count_before, len(run.output("test-cases.json")["test_cases"]))

    def test_a_failing_submit_leaves_the_parent_and_the_challenge_run_untouched(self) -> None:
        run = PackRun("erp-sales-orders")
        self.addCleanup(run.close)
        run.finalize()
        canonical_before = file_digest(run.run_dir / "canonical-suite.json")
        start = ch.start_challenge(run.run_dir, "run", seeds=[])
        bad = {"cases": [_case(discovery="NOT_A_REAL_DISCOVERY")], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", bad)
        self.assertEqual(canonical_before, file_digest(run.run_dir / "canonical-suite.json"))
        self.assertFalse((Path(start["challenge_dir"]) / "challenge-result.json").is_file())

    def test_challenge_cases_use_a_separate_id_namespace_from_canonical_tests(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case()], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["challenge_cases_generated"])
        cases = ch.finalize_challenge(run.run_dir, "run")
        stored = ch.read_json(Path(cases["challenge_dir"]) / "challenge-cases.json")["cases"]
        self.assertTrue(all(case["id"].startswith("CH-") for case in stored))


class SeedSemanticsTests(unittest.TestCase):
    def test_zero_seed_files_is_a_valid_challenge(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        start = ch.start_challenge(run.run_dir, "run", seeds=[])
        self.assertEqual(0, start["seeds_received"])

    def test_multiple_informal_seed_files_are_accepted_and_preserved_verbatim(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed_a = _write_seed("- what if two admins act at once?\n")
        seed_b = _write_seed("- try revoking access mid-flight\n")
        start = ch.start_challenge(run.run_dir, "run", seeds=[seed_a, seed_b])
        self.assertEqual(2, start["seeds_received"])
        work_order = ch.read_json(Path(start["work_order"]))
        self.assertEqual({s["path"] for s in work_order["seeds"]}, {seed_a.name, seed_b.name})

    def test_a_seed_is_never_promoted_to_normative_authority(self) -> None:
        """An unsupported rule from a seed becomes an honest disposition, never an Acceptance claim."""
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- the system should surely lock out after three failed attempts\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {
            "cases": [_case(
                discovery="HUMAN_SEEDED", inspired_by=[f"{seed.name}#lockout"],
                execution_tags=["EXPLORATORY"],
                unknowns=[{"kind": "MISSING_ORACLE", "detail": "no authority source defines a lockout threshold"}],
            )],
            "seed_dispositions": [{"seed": seed.name, "disposition": "QUESTIONED",
                                    "summary": "no authority for a lockout threshold", "cases": ["H1"]}],
        }
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["seed_items_questioned"])
        # Nothing about this seed idea touched the canonical suite.
        self.assertNotIn("basis", payload["cases"][0])

    def test_every_seed_file_needs_a_disposition_or_the_submit_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- an idea that silently disappears\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {"cases": [], "seed_dispositions": []}
        with self.assertRaises(StageError) as caught:
            ch.submit_challenge(run.run_dir, "run", payload)
        self.assertIn("seed_disposition", str(caught.exception))

    def test_inspired_by_must_name_a_seed_actually_passed_to_this_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(discovery="HUMAN_SEEDED", inspired_by=["nonexistent.md#idea"])],
                   "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_model_can_derive_cases_the_seed_never_mentioned(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- what if two admins act at once?\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {
            "cases": [
                _case(key="H1", discovery="HUMAN_SEEDED", inspired_by=[f"{seed.name}#concurrent"]),
                _case(key="M1", title="A device left connected past its session timeout",
                      discovery="MODEL_DERIVED", execution_tags=["PHYSICAL_DEVICE"]),
            ],
            "seed_dispositions": [{"seed": seed.name, "disposition": "MATERIALIZED", "cases": ["H1"]}],
        }
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["model_derived_cases"])
        self.assertEqual(2, result["challenge_cases_generated"])


class ProvenanceAndGroundingTests(unittest.TestCase):
    def test_related_test_case_must_exist_in_the_parent_canonical_suite(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(related_test_cases=["TC-999"])], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_steps_without_evidence_refs_or_a_declared_gap_are_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do the thing.", "expected_result": "It works."}],
        )], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_a_declared_execution_gap_keeps_the_case_without_fabricating_a_path(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            execution_tags=["EXTERNAL_ENVIRONMENT"],
            preconditions=["Two admin sessions exist for one account."],
            steps=[{"action": "Race two concurrent invitations for the same email.",
                    "expected_result": "Only one invitation record survives."}],
            unknowns=[{"kind": "UNKNOWN_SETUP_PATH", "detail": "no evidence shows how to force two concurrent requests"}],
        )], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["challenge_cases_generated"])


class ManualPlanAndCanonicalGapTests(unittest.TestCase):
    def test_non_automatable_cases_are_preserved_in_the_plan_not_deleted(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            execution_tags=["PHYSICAL_DEVICE", "CHAOS_RECOVERY"], automation_suitability="MANUAL_ONLY",
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        result = ch.finalize_challenge(run.run_dir, "run")
        plan = (Path(result["challenge_dir"]) / "challenge-plan.md").read_text(encoding="utf-8")
        self.assertIn("CH-001", plan)
        self.assertIn("Chaos / recovery", plan)

    def test_potential_canonical_gap_is_advisory_and_never_mutates_the_parent(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        canonical_before = file_digest(run.run_dir / "canonical-suite.json")
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            canonical_gap_candidate={
                "authority_evidence": "the spec mentions a lockout policy in passing",
                "why_normative": "it reads as a required control, not an exploratory idea",
            },
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        result = ch.finalize_challenge(run.run_dir, "run")
        plan = (Path(result["challenge_dir"]) / "challenge-plan.md").read_text(encoding="utf-8")
        self.assertIn("Potential canonical gaps", plan)
        self.assertIn("CH-001", plan.split("Potential canonical gaps")[1])
        self.assertEqual(canonical_before, file_digest(run.run_dir / "canonical-suite.json"))


class DiagnosticsTests(unittest.TestCase):
    def test_targeted_lookup_and_full_reread_are_reported_honestly(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do the grounded action.", "expected_result": "It is observed."}],
            evidence_refs=[{"source": source, "reference": "section"}],
        )], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["targeted_source_lookups"])
        self.assertEqual(0, result["full_source_rereads"])

    def test_verify_reports_the_parent_digest_and_resolves_references(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        ch.submit_challenge(run.run_dir, "run", {"cases": [_case()], "seed_dispositions": []})
        ch.finalize_challenge(run.run_dir, "run")
        verified = ch.verify_challenge(run.run_dir, "run")
        self.assertTrue(verified["verified"])
        self.assertEqual(file_digest(run.run_dir / "canonical-suite.json"), verified["parent_canonical_digest"])


if __name__ == "__main__":
    unittest.main()
