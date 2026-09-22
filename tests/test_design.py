"""Normative design invariants: identifiers, titles, atomicity, business rules, locale."""

from __future__ import annotations

import unittest

from support import PackRun, by_key

from common import StageError


def design(pack):
    return pack["stages"]["design"]


class DesignStageTests(unittest.TestCase):
    def run_design(self, name, mutate):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.start()
        return run.submit

    def test_pt_br_authority_produces_pt_br_output(self) -> None:  # 1
        run = PackRun("logistics-storage")
        self.addCleanup(run.close)
        started = run.start()
        self.assertEqual(("pt-BR", "FUNCTIONAL_AUTHORITY"), (started["output_locale"], started["locale_source"]))
        run.pack["stages"]["design"]["tests"][0]["objective"] = "Verify that the entry leaves the pallet stored at the informed position."
        with self.assertRaisesRegex(StageError, r"written in 'en' but the run locale is pt-BR"):
            run.submit("design")

    def test_official_title_is_preserved(self) -> None:  # 2
        def wrong_title(pack):
            design(pack)["requirements"][0]["source_title"] = "header"
        submit = self.run_design("saas-accounts", wrong_title)
        with self.assertRaisesRegex(StageError, "differs from the official title 'Invite Team Member'"):
            submit("design")

    def test_title_is_filled_from_authority_when_omitted(self) -> None:  # 2
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        requirement = run.output("test-cases.json")["requirements"][0]
        self.assertEqual(("FR-01", "Invite Team Member"), (requirement["source_identifier"], requirement["source_title"]))

    def test_every_authoritative_identifier_gets_a_disposition(self) -> None:  # 3
        run = PackRun("logistics-storage")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        ledger = run.output("test-cases.json")["identifier_dispositions"]
        self.assertEqual({"RF-01", "RF-02", "RN-01", "RN-02", "CU-01", "FA-01.1"}, {item["identifier"] for item in ledger})
        self.assertTrue(all(item["disposition"] for item in ledger))
        fa = next(item for item in ledger if item["identifier"] == "FA-01.1")
        self.assertEqual("COVERED_BY_MULTIPLE_ATOMIC_TCS", fa["disposition"])

    def test_discovered_business_rule_without_claim_or_test_fails(self) -> None:  # 4
        def drop_rule(pack):
            d = design(pack)
            d["claims"] = [c for c in d["claims"] if c["requirement"] != "BR-02"]
            d["tests"] = [t for t in d["tests"] if t["key"] not in {"T6", "T7"}]
            d["requirements"] = [r for r in d["requirements"] if r["key"] != "BR-02"]
        submit = self.run_design("saas-accounts", drop_rule)
        with self.assertRaisesRegex(StageError, r"identifier BR-02 \(BUSINESS_RULE\) is unaccounted"):
            submit("design")

    def test_identifier_invented_by_the_model_is_rejected(self) -> None:
        def invent(pack):
            design(pack)["requirements"][0]["source_identifier"] = "FR-99"
        submit = self.run_design("saas-accounts", invent)
        with self.assertRaisesRegex(StageError, "FR-99 does not appear in selected authority"):
            submit("design")

    def test_independent_obligations_become_independent_tests(self) -> None:  # 5
        def compress(pack):
            d = design(pack)
            d["claims"].append({"key": "CX", "requirement": "RF-01",
                                "text": "Após a entrada, o status muda para Armazenado, o saldo é atualizado e um registro é criado."})
            d["tests"].append(dict(by_key(d["tests"], "T1"), key="TX", claims=["CX"]))
        submit = self.run_design("logistics-storage", compress)
        with self.assertRaisesRegex(StageError, "claim CX looks compound"):
            submit("design")

    def test_one_test_cannot_exercise_several_claims_without_indivisible_contract(self) -> None:  # 5
        def merge(pack):
            t1 = by_key(design(pack)["tests"], "T2")
            t1["claims"] = ["C2", "C3"]
            design(pack)["tests"] = [t for t in design(pack)["tests"] if t["key"] != "T3"]
        submit = self.run_design("logistics-storage", merge)
        with self.assertRaisesRegex(StageError, "exercises 2 claims; independent failure domains"):
            submit("design")

    def test_indivisible_audit_record_may_remain_one_test(self) -> None:  # 6
        run = PackRun("logistics-storage")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        cases = [run.output(f"test-cases/TC-{n:03d}.json") for n in range(1, 9)]
        audit = next(case for case in cases if case["title"] == "Entrada gera registro de movimentação")
        self.assertEqual(1, len(audit["claim_exercise_map"]))
        self.assertEqual(1, len(audit["coverage_point_refs"]))
        self.assertIn("data, hora e operador", audit["steps"][-1]["expected_result"])

    def test_business_rules_have_their_own_accounted_claims(self) -> None:  # 17
        run = PackRun("aerospace-inspection")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        ledger = {item["identifier"]: item for item in run.output("test-cases.json")["identifier_dispositions"]}
        for rule in ("RN-01", "RN-02", "RN-03"):
            self.assertEqual("BUSINESS_RULE", ledger[rule]["kind"])
            self.assertTrue(ledger[rule]["disposition"].startswith("COVERED"))
            self.assertTrue(ledger[rule]["claim_refs"])

    def test_missing_implementation_cannot_remove_normative_behavior(self) -> None:  # 18
        def drop(pack):
            d = design(pack)
            by_key(d["claims"], "C4")["destination"] = "NOT_TESTABLE"
            by_key(d["claims"], "C4")["reason"] = "the acquirer implementation is missing from the selection"
            d["tests"] = [t for t in d["tests"] if t["key"] != "T4"]
        submit = self.run_design("api-refunds", drop)
        with self.assertRaisesRegex(StageError, "cannot become NOT_TESTABLE because implementation is missing"):
            submit("design")

    def test_domain_model_is_required_and_project_derived(self) -> None:
        def drop(pack):
            design(pack).pop("domain_model")
        submit = self.run_design("iot-line-monitoring", drop)
        with self.assertRaisesRegex(StageError, "project-derived domain_model"):
            submit("design")

    def test_runtime_owned_fields_are_not_accepted(self) -> None:  # 24
        def claim_gates(pack):
            design(pack)["quality_gates"] = [{"gate": "SCOPE_VALID", "status": "PASS"}]
        submit = self.run_design("saas-accounts", claim_gates)
        with self.assertRaisesRegex(StageError, "'quality_gates' is not accepted"):
            submit("design")


if __name__ == "__main__":
    unittest.main()
