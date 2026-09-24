"""Post-suite challenge: canonical immutability, item-level seed semantics, real
targeted lookup, evidence validation, state machine, grounding and the manual plan."""

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


class WorkOrderContextTests(unittest.TestCase):
    def test_work_order_reuses_the_parent_domain_model_and_authority_excerpts(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        start = ch.start_challenge(run.run_dir, "run", seeds=[])
        work_order = ch.read_json(Path(start["work_order"]))
        self.assertTrue(work_order["domain_model"].get("actors"))
        self.assertTrue(work_order["authority_excerpts"])
        self.assertTrue(work_order["canonical_cases"])


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
            unknowns=[{"kind": "UNKNOWN_SETUP_PATH", "detail": "the sources do not say how the sensor is powered off on the bench"}],
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        ch.finalize_challenge(run.run_dir, "run")

        self.assertEqual(canonical_before, file_digest(run.run_dir / "canonical-suite.json"))
        self.assertEqual(manifest_before, (run.run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(tc_count_before, len(run.output("test-cases.json")["test_cases"]))

    def test_challenge_cases_follow_the_canonical_step_rules(self) -> None:
        run = PackRun("iot-line-monitoring")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            evidence_refs=[{"source": source, "reference": "n/a"}],
            preconditions=["SENSOR_A is streaming readings."],
            steps=[{"action": "Power off the sensor mid-reading.", "expected_result": "The request is sent."},
                   {"action": "Open the alarm list.", "expected_result": "The alarm is shown or the list is empty."},
                   {"action": "Send readings in a burst.", "expected_result": "All readings are stored within 200 ms."}],
        )], "seed_dispositions": []}
        with self.assertRaises(StageError) as caught:
            ch.submit_challenge(run.run_dir, "run", payload)
        text = str(caught.exception)
        for fragment in ("never invent the technique", "only says the action happened", "alternative outcomes",
                         "no related canonical Test Case states", "uses fixtures ['SENSOR_A']"):
            self.assertIn(fragment, text)

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
        lineage = ch.read_json(Path(start["challenge_dir"]) / "challenge-run.json")
        self.assertEqual("STARTED", lineage["status"])

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


class StateMachineTests(unittest.TestCase):
    def test_second_submit_to_the_same_challenge_run_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case()], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        with self.assertRaises(ch.ChallengeError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_finalize_before_submit_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        with self.assertRaises(ch.ChallengeError):
            ch.finalize_challenge(run.run_dir, "run")

    def test_second_finalize_does_not_rewrite_the_finalized_output(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        ch.submit_challenge(run.run_dir, "run", {"cases": [_case()], "seed_dispositions": []})
        ch.finalize_challenge(run.run_dir, "run")
        with self.assertRaises(ch.ChallengeError):
            ch.finalize_challenge(run.run_dir, "run")


class SeedItemSemanticsTests(unittest.TestCase):
    def test_zero_seed_files_is_a_valid_challenge(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        start = ch.start_challenge(run.run_dir, "run", seeds=[])
        self.assertEqual(0, start["seeds_received"])

    def test_each_bullet_becomes_its_own_addressable_seed_item(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed(
            "# QA notes\n\n- disconnect the device mid-operation\n"
            "- two operators confirm at once\n- retry after the response is lost\n"
        )
        start = ch.start_challenge(run.run_dir, "run", seeds=[seed])
        self.assertEqual(3, start["seed_items_received"])
        work_order = ch.read_json(Path(start["work_order"]))
        anchors = [item["anchor"] for item in work_order["seeds"][0]["items"]]
        self.assertEqual(["qa-ideas.md#seed-001", "qa-ideas.md#seed-002", "qa-ideas.md#seed-003"], anchors)

    def test_a_seed_item_is_never_promoted_to_normative_authority(self) -> None:
        """An unsupported rule from a seed becomes an honest disposition, never an Acceptance claim."""
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- the system should surely lock out after three failed attempts\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {
            "cases": [_case(
                discovery="HUMAN_SEEDED", inspired_by=["qa-ideas.md#seed-001"],
                execution_tags=["EXPLORATORY"],
                unknowns=[{"kind": "MISSING_ORACLE", "detail": "no authority source defines a lockout threshold"}],
            )],
            "seed_dispositions": [{"seed_ref": "qa-ideas.md#seed-001", "disposition": "QUESTIONED",
                                    "summary": "no authority for a lockout threshold", "cases": ["H1"]}],
        }
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["seed_items_questioned"])
        self.assertNotIn("basis", payload["cases"][0])

    def test_every_seed_item_needs_a_disposition_or_the_submit_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- an idea that silently disappears\n- a second idea, dispositioned\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {"cases": [], "seed_dispositions": [
            {"seed_ref": "qa-ideas.md#seed-002", "disposition": "NOT_APPLICABLE", "cases": []},
        ]}
        with self.assertRaises(StageError) as caught:
            ch.submit_challenge(run.run_dir, "run", payload)
        self.assertIn("seed-001", str(caught.exception))

    def test_already_covered_requires_a_real_covering_test_case(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- what if the invite is sent twice?\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {"cases": [], "seed_dispositions": [
            {"seed_ref": "qa-ideas.md#seed-001", "disposition": "ALREADY_COVERED", "cases": []},
        ]}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_already_covered_resolves_to_a_real_canonical_test_case(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- what if the invite is sent twice?\n")
        start = ch.start_challenge(run.run_dir, "run", seeds=[seed])
        work_order = ch.read_json(Path(start["work_order"]))
        existing_tc = work_order["canonical_cases"][0]["id"]
        payload = {"cases": [], "seed_dispositions": [
            {"seed_ref": "qa-ideas.md#seed-001", "disposition": "ALREADY_COVERED", "covered_by": [existing_tc], "cases": []},
        ]}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["seed_items_already_covered"])

    def test_inspired_by_must_name_a_seed_item_actually_passed_to_this_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(discovery="HUMAN_SEEDED", inspired_by=["nonexistent.md#seed-001"])],
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
                _case(key="H1", discovery="HUMAN_SEEDED", inspired_by=["qa-ideas.md#seed-001"]),
                _case(key="M1", title="A device left connected past its session timeout",
                      discovery="MODEL_DERIVED", execution_tags=["PHYSICAL_DEVICE"]),
            ],
            "seed_dispositions": [{"seed_ref": "qa-ideas.md#seed-001", "disposition": "MATERIALIZED", "cases": ["H1"]}],
        }
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["model_derived_cases"])
        self.assertEqual(2, result["challenge_cases_generated"])

    def test_final_seed_disposition_references_resolve_to_assigned_ch_ids(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        seed = _write_seed("- what if two admins act at once?\n")
        ch.start_challenge(run.run_dir, "run", seeds=[seed])
        payload = {"cases": [_case(discovery="HUMAN_SEEDED", inspired_by=["qa-ideas.md#seed-001"])],
                   "seed_dispositions": [{"seed_ref": "qa-ideas.md#seed-001", "disposition": "MATERIALIZED", "cases": ["H1"]}]}
        ch.submit_challenge(run.run_dir, "run", payload)
        result = ch.read_json(ch._challenge_dir(run.run_dir, "run") / "challenge-result.json")
        self.assertEqual(["CH-001"], result["seed_dispositions"][0]["cases"])
        self.assertNotIn("H1", str(result["seed_dispositions"]))


class TargetedLookupTests(unittest.TestCase):
    def test_a_real_lookup_increments_the_lookup_metric(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        looked_up = ch.lookup_evidence(run.run_dir, "run", source, query="invite")
        self.assertTrue(looked_up["excerpt"])
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do the grounded action.", "expected_result": "It is observed."}],
            evidence_refs=[{"source": source, "reference": looked_up["locator"]}],
        )], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["runtime_targeted_lookups"])
        self.assertEqual(0, result["runtime_full_source_rereads"])
        self.assertEqual("NOT_OBSERVABLE", result["model_source_rereads"])

    def test_submitting_an_evidence_ref_alone_does_not_fake_a_lookup(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do the grounded action.", "expected_result": "It is observed."}],
            evidence_refs=[{"source": source, "reference": "cited without ever calling lookup"}],
        )], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(0, result["runtime_targeted_lookups"])

    def test_lookup_rejects_a_source_outside_the_selected_scope(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        with self.assertRaises(ch.ChallengeError):
            ch.lookup_evidence(run.run_dir, "run", "outside/scope.py", query="x")

    def test_lookup_rejects_an_out_of_range_line_selection(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        with self.assertRaises(ch.ChallengeError):
            ch.lookup_evidence(run.run_dir, "run", source, line_start=9999, line_end=10000)


class EvidenceReferenceValidationTests(unittest.TestCase):
    def test_evidence_ref_with_unknown_source_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do it.", "expected_result": "Observed."}],
            evidence_refs=[{"source": "not/a/selected/source.py", "reference": "n/a"}],
        )], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_evidence_ref_with_an_invalid_line_range_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do it.", "expected_result": "Observed."}],
            evidence_refs=[{"source": source, "reference": "bad range", "line_start": 9999, "line_end": 10000}],
        )], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

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


class ExecutionTagsAndReadinessTests(unittest.TestCase):
    def test_a_project_specific_tag_beyond_the_core_set_is_accepted(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(execution_tags=["NIGHT_SHIFT_ONLY"])], "seed_dispositions": []}
        result = ch.submit_challenge(run.run_dir, "run", payload)
        self.assertEqual(1, result["challenge_cases_generated"])

    def test_a_malformed_tag_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(execution_tags=["not upper snake"])], "seed_dispositions": []}
        with self.assertRaises(StageError):
            ch.submit_challenge(run.run_dir, "run", payload)

    def test_exploratory_tag_keeps_exploratory_status_even_without_unknowns(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        ch.submit_challenge(run.run_dir, "run", {"cases": [_case(execution_tags=["EXPLORATORY"])], "seed_dispositions": []})
        result = ch.finalize_challenge(run.run_dir, "run")
        cases = ch.read_json(Path(result["challenge_dir"]) / "challenge-cases.json")["cases"]
        self.assertEqual("EXPLORATORY", cases[0]["status"])

    def test_a_grounded_case_without_unknowns_is_ready(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        source = next(iter(run.pack["sources"]))
        payload = {"cases": [_case(
            preconditions=["A record exists."],
            steps=[{"action": "Do the grounded action.", "expected_result": "It is observed."}],
            evidence_refs=[{"source": source, "reference": "n/a"}],
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        result = ch.finalize_challenge(run.run_dir, "run")
        cases = ch.read_json(Path(result["challenge_dir"]) / "challenge-cases.json")["cases"]
        self.assertEqual("READY", cases[0]["status"])


class ManualPlanAndCanonicalGapTests(unittest.TestCase):
    def test_non_automatable_cases_are_preserved_in_the_plan_not_deleted(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "run", seeds=[])
        payload = {"cases": [_case(
            execution_tags=["PHYSICAL_DEVICE", "CHAOS_RECOVERY"], automation_suitability="MANUAL_ONLY",
            required_resources=["a spare reader device"], environment_requirements=["lab network"],
        )], "seed_dispositions": []}
        ch.submit_challenge(run.run_dir, "run", payload)
        result = ch.finalize_challenge(run.run_dir, "run")
        plan = (Path(result["challenge_dir"]) / "challenge-plan.md").read_text(encoding="utf-8")
        self.assertIn("CH-001", plan)
        self.assertIn("spare reader device", plan)
        self.assertIn("Chaos / recovery", plan)

    def test_canonical_hardware_or_mixed_layer_case_appears_regardless_of_suitability(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        canonical = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")
        # None of this pack's canonical suitability values are LOW/MANUAL_ONLY by default,
        # so a HARDWARE/MIXED layer case would otherwise vanish from the plan; force one.
        canonical["cases"][0]["automation_layer"] = "HARDWARE"
        canonical["cases"][0]["automation_suitability"] = "HIGH"
        ch.start_challenge(run.run_dir, "run", seeds=[])
        plan = ch.render_manual_plan(canonical, [])
        self.assertIn(canonical["cases"][0]["id"], plan.split("Physical device tests")[1].split("##")[0])

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


class VerifyTests(unittest.TestCase):
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
