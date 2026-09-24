"""Mandatory second pass: evaluated dimensions, checklists, semantic coverage, E2E."""

from __future__ import annotations

import json
import unittest

from support import PackRun, candidate

from common import StageError


def expansion(pack):
    return pack["stages"]["expansion"]


class ExpansionStageTests(unittest.TestCase):
    def reach_expansion(self, name, mutate=None):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("design")
        return run

    def test_operator_error_discovery_produces_candidates(self) -> None:  # 7
        run = self.reach_expansion("logistics-storage")
        result = run.submit("expansion")
        self.assertEqual("procedures", result["next_stage"])
        run.submit("procedures")
        import pipeline
        final = pipeline.finalize_run(run.run_dir, ["JSON", "DIAGNOSTICS"])
        summary = {item["dimension"]: item for item in run.output("test-cases.json")["expansion_summary"]}
        self.assertEqual(3, summary["OPERATOR_ERROR"]["candidates_considered"])
        self.assertEqual(1, summary["OPERATOR_ERROR"]["materialized"])
        self.assertEqual(1, final["metrics"]["by_dimension"]["OPERATOR_ERROR"])

    def test_zero_operator_error_candidates_requires_an_evaluation(self) -> None:  # 8
        def skip(pack):
            expansion(pack)["dimensions"] = [d for d in expansion(pack)["dimensions"] if d["dimension"] != "OPERATOR_ERROR"]
        run = self.reach_expansion("saas-accounts", skip)
        with self.assertRaisesRegex(StageError, "dimensions were not evaluated: OPERATOR_ERROR"):
            run.submit("expansion")

    def test_zero_operator_error_candidates_is_valid_after_evaluation(self) -> None:  # 8
        def none_apply(pack):
            record = next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "OPERATOR_ERROR")
            record["candidates"] = []
            record["patterns_reviewed"] = [{"items": [
                "WRONG_RESOURCE", "WRONG_ASSOCIATION", "WRONG_ACTOR", "WRONG_STATE", "WRONG_SEQUENCE", "REPEATED_ACTION",
                "OMITTED_ACTION", "STALE_OPERATION", "PARTIAL_OPERATION", "CROSS_CONTEXT_MISTAKE",
                "PHYSICAL_DIGITAL_MISMATCH", "WRONG_ACKNOWLEDGEMENT", "MANUAL_AFTER_AUTOMATIC", "ABANDONED_OPERATION",
            ], "status": "NOT_APPLICABLE", "reason": "readings arrive from sensors without human data entry in this scope"}]
            record["summary"] = "Human interaction was evaluated and is limited to acknowledgement, covered by authorization tests."
        run = self.reach_expansion("iot-line-monitoring", none_apply)
        self.assertTrue(run.submit("expansion")["recorded"])

    def test_every_operator_pattern_must_be_evaluated(self) -> None:  # 8
        def partial(pack):
            record = next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "OPERATOR_ERROR")
            record["patterns_reviewed"] = record["patterns_reviewed"][:1]
        run = self.reach_expansion("saas-accounts", partial)
        with self.assertRaisesRegex(StageError, "OPERATOR_ERROR patterns_reviewed did not evaluate"):
            run.submit("expansion")

    def test_chaos_evaluates_failure_surfaces_even_when_none_materialize(self) -> None:  # 9
        run = self.reach_expansion("aerospace-inspection")
        self.assertTrue(run.submit("expansion")["recorded"])

        def missing(pack):
            next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "CHAOS").pop("surfaces_reviewed")
        other = self.reach_expansion("aerospace-inspection", missing)
        with self.assertRaisesRegex(StageError, "CHAOS surfaces_reviewed did not evaluate"):
            other.submit("expansion")

    def test_already_covered_requires_semantic_compatibility(self) -> None:  # 10
        def unrelated(pack):
            item = candidate(pack, "STATE_TRANSITION", "S1")
            item["intent"] = {"actor": "Owner", "state": "account with free seats", "trigger": "owner exports the audit log",
                              "failure_domain": "audit export format", "expected": "a CSV file is downloaded"}
        run = self.reach_expansion("saas-accounts", unrelated)
        with self.assertRaisesRegex(StageError, r"S1 is not semantically covered by \['T3'\]"):
            run.submit("expansion")

    def test_unrelated_test_asset_cannot_map_to_a_generic_test(self) -> None:  # 11
        def generic(pack):
            assets = expansion(pack)["test_assets"]
            index = next(i for i, a in enumerate(assets) if a["asset"].endswith("::test_fourth_refund_is_rejected"))
            assets[index] = {
                "asset": assets[index]["asset"], "disposition": "ALREADY_COVERED_BY", "covered_by": ["T1"],
                "intent": assets[index]["intent"],
            }
        run = self.reach_expansion("api-refunds", generic)
        with self.assertRaisesRegex(StageError, "test_fourth_refund_is_rejected is not semantically covered"):
            run.submit("expansion")

    def test_every_discovered_test_asset_needs_a_disposition(self) -> None:
        def forget(pack):
            expansion(pack)["test_assets"].pop()
        run = self.reach_expansion("api-refunds", forget)
        with self.assertRaisesRegex(StageError, "1 discovered test asset behavior"):
            run.submit("expansion")

    def test_e2e_stage_must_map_the_composed_atomic_behavior(self) -> None:  # 19
        def wrong_stage(pack):
            stage = candidate(pack, "E2E", "E1")["test"]["stages"][1]
            stage["test"] = "T6"
        run = self.reach_expansion("saas-accounts", wrong_stage)
        with self.assertRaisesRegex(StageError, "stage 2 does not map to the behavior of T6"):
            run.submit("expansion")

    def test_e2e_needs_at_least_two_distinct_atomic_stages(self) -> None:  # 19
        def single(pack):
            test = candidate(pack, "E2E", "E1")["test"]
            test["stages"] = test["stages"][:1]
        run = self.reach_expansion("iot-line-monitoring", single)
        with self.assertRaisesRegex(StageError, "at least two distinct atomic stages"):
            run.submit("expansion")

    def test_every_use_case_gets_a_journey_disposition(self) -> None:  # 23 (journeys)
        def drop(pack):
            record = next(d for d in expansion(pack)["dimensions"] if d["dimension"] == "E2E")
            record["candidates"] = []
        run = self.reach_expansion("erp-sales-orders", drop)
        with self.assertRaisesRegex(StageError, "use case CU-01 has no E2E journey disposition"):
            run.submit("expansion")

    def test_derived_tests_need_an_authority_oracle(self) -> None:
        def implementation_oracle(pack):
            candidate(pack, "BOUNDARY", "B1")["test"]["oracle_source"] = {"source": "src/invitations.py", "reference": "invite"}
        run = self.reach_expansion("saas-accounts", implementation_oracle)
        with self.assertRaisesRegex(StageError, "DERIVED and needs oracle_source in Functional Authority"):
            run.submit("expansion")


class ImplementationTestAssetTests(unittest.TestCase):
    """Existing tests below an implementation selection challenge the suite; they keep
    the implementation role and never become authority."""

    @staticmethod
    def as_implementation(pack):
        for source in pack["sources"].values():
            if source["role"] == "TEST_ASSET":
                source["role"] = "IMPLEMENTATION_EVIDENCE"

    def check(self, name: str) -> None:
        explicit = PackRun(name)
        self.addCleanup(explicit.close)
        explicit_assets = explicit.start()["test_assets"]
        run = PackRun(name, self.as_implementation)
        self.addCleanup(run.close)
        started = run.start()
        self.assertGreater(started["test_assets"], 0)
        self.assertEqual(explicit_assets, started["test_assets"])
        state = json.loads((run.run_dir / "sources.json").read_text(encoding="utf-8"))
        roles = {record["path"]: record["role"] for record in state["records"]}
        for asset in state["test_assets"]:
            self.assertEqual("IMPLEMENTATION_EVIDENCE", asset["source_role"])
            self.assertEqual("IMPLEMENTATION_EVIDENCE", roles[asset["source"]])
        authority_sources = {item["source"] for item in state["authority_index"]}
        self.assertTrue(authority_sources)
        self.assertFalse({a["source"] for a in state["test_assets"]} & authority_sources)
        run.submit("design")
        run.submit("expansion")
        result = json.loads((run.run_dir / "stages" / "expansion.result.json").read_text(encoding="utf-8"))
        challenge = result["test_asset_challenge"]
        self.assertEqual(started["test_assets"], len(challenge))
        self.assertTrue(all(item["source_role"] == "IMPLEMENTATION_EVIDENCE" for item in challenge))

    def test_saas_tests_inside_implementation_are_challenged(self) -> None:
        self.check("saas-accounts")

    def test_refund_api_tests_inside_implementation_are_challenged(self) -> None:
        self.check("api-refunds")

    def test_undispositioned_implementation_side_test_is_rejected(self) -> None:
        def mutate(pack):
            self.as_implementation(pack)
            pack["stages"]["expansion"]["test_assets"].pop()
        run = PackRun("saas-accounts", mutate)
        self.addCleanup(run.close)
        run.through("design")
        with self.assertRaisesRegex(StageError, "1 discovered test asset behavior"):
            run.submit("expansion")


if __name__ == "__main__":
    unittest.main()
