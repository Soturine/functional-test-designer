"""Stage B procedures: executability, readiness and automation separation."""

from __future__ import annotations

import re
import unittest

from support import PackRun, procedure

from common import StageError
from procedures import classify


class ProcedureStageTests(unittest.TestCase):
    def reach_procedures(self, name, mutate=None):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    def test_semantic_fixtures_yield_ready_without_literal_ids(self) -> None:  # 12, 13
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        case = run.output("test-cases/TC-001.json")
        data = " ".join(f"{row['name']} {row['description']}" for row in case["test_data"])
        self.assertEqual("READY", case["status"])
        self.assertIn("USER_OWNER_A", data)
        self.assertIsNone(re.search(r"\b\d{3,}\b", data))
        self.assertEqual([], case["readiness_blockers"])

    def test_only_material_unknowns_create_needs_review(self) -> None:  # 13
        self.assertEqual("READY", classify([{"kind": "MISSING_FIXTURE"}], "HIGH", "ACCEPTANCE", False)["status"])
        self.assertEqual("NEEDS_REVIEW", classify([{"kind": "UNKNOWN_SETUP_PATH"}], "HIGH", "ACCEPTANCE", False)["status"])
        self.assertEqual("NEEDS_REVIEW", classify([], "HIGH", "ACCEPTANCE", True)["status"])

    def test_automation_suitability_and_readiness_are_separate(self) -> None:  # 14
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        case = run.output("test-cases/TC-002.json")
        self.assertEqual(("READY", "MEDIUM", "NEEDS_FIXTURE"),
                         (case["status"], case["automation_suitability"], case["automation_readiness"]))
        self.assertTrue(case["automation_candidate"])
        self.assertEqual("NOT_APPLICABLE", classify([], "MANUAL_ONLY", "ACCEPTANCE", False)["automation_readiness"])
        blocked = classify([{"kind": "EXTERNAL_DEPENDENCY_UNAVAILABLE"}], "HIGH", "ACCEPTANCE", False)
        self.assertEqual(("BLOCKED_EXTERNAL_DEPENDENCY", "BLOCKED_EXTERNAL_DEPENDENCY"),
                         (blocked["status"], blocked["automation_readiness"]))

    def test_one_step_needs_a_completeness_reason(self) -> None:  # 15
        def no_reason(pack):
            procedure(pack, "T6").pop("single_step_reason")
        run = self.reach_procedures("saas-accounts", no_reason)
        with self.assertRaisesRegex(StageError, "has one step; explain in single_step_reason"):
            run.submit("procedures")

    def test_multi_action_flow_cannot_be_compressed_into_one_step(self) -> None:  # 16
        def compress(pack):
            item = procedure(pack, "T1")
            item["steps"] = [{"action": "Open the member page, select invite, enter EMAIL_NEW and then submit the form.",
                              "expected_result": "A pending invitation for EMAIL_NEW is created and listed."}]
            item["single_step_reason"] = "everything happens on one page"
        run = self.reach_procedures("saas-accounts", compress)
        with self.assertRaisesRegex(StageError, "compresses a multi-action flow into one step"):
            run.submit("procedures")

    def test_generic_preconditions_and_placeholders_are_rejected(self) -> None:
        def generic(pack):
            item = procedure(pack, "T3")
            item["preconditions"] = ["Preconditions for: Valid invitation adds a member"]
            item["test_data"] = [{"name": "invite", "description": "<valid invitation id>"}]
        run = self.reach_procedures("saas-accounts", generic)
        with self.assertRaisesRegex(StageError, "generic precondition") as caught:
            run.submit("procedures")
        self.assertIn("placeholder", str(caught.exception))

    def test_oracle_step_must_observe_the_designed_oracle(self) -> None:
        def drift(pack):
            procedure(pack, "T5")["steps"][-1]["expected_result"] = "The page reloads."
        run = self.reach_procedures("saas-accounts", drift)
        with self.assertRaisesRegex(StageError, "does not observe the designed oracle"):
            run.submit("procedures")

    def test_every_test_case_needs_a_procedure(self) -> None:
        def drop(pack):
            pack["stages"]["procedures"]["procedures"].pop()
        run = self.reach_procedures("iot-line-monitoring", drop)
        with self.assertRaisesRegex(StageError, r"1 Test Case\(s\) have no procedure"):
            run.submit("procedures")

    def test_status_is_runtime_owned(self) -> None:  # 24
        def claim_ready(pack):
            procedure(pack, "X1")["status"] = "READY"
        run = self.reach_procedures("iot-line-monitoring", claim_ready)
        with self.assertRaisesRegex(StageError, r"runtime-owned or unknown fields \['status'\]"):
            run.submit("procedures")

    def test_procedure_text_follows_the_run_locale(self) -> None:  # 1
        def english(pack):
            procedure(pack, "T1")["steps"][0]["action"] = "Open the pallet entry screen and wait for it to load."
        run = self.reach_procedures("logistics-storage", english)
        with self.assertRaisesRegex(StageError, "written in 'en' but the run locale is pt-BR"):
            run.submit("procedures")

    def test_missing_external_implementation_keeps_the_normative_test_blocked(self) -> None:  # 18
        run = PackRun("api-refunds")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        index = run.output("test-cases.json")
        ledger = {item["identifier"]: item for item in index["identifier_dispositions"]}
        self.assertEqual("BLOCKED_EXTERNAL_DEPENDENCY", ledger["REQ-3"]["disposition"])
        self.assertEqual(1, index["gap_metrics"]["blocked_normative_tests"])


if __name__ == "__main__":
    unittest.main()
