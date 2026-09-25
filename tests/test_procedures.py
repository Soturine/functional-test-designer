"""Stage B procedures: executability, readiness and automation separation."""

from __future__ import annotations

import re
import unittest

from support import PackRun, procedure

from common import StageError
from procedures import ABSTRACT_ACTION, ENVIRONMENT_CONTROL, classify


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


class UbiquitousProcedureTests(unittest.TestCase):
    """One canonical procedure serves a novice human and an automation agent alike:
    each step says who does which atomic action to which target (where, with which
    semantic data) and what becomes observable, without tool-specific syntax."""

    VAGUE_ACTIONS = (
        "Access the system.", "Perform the operation.", "Validate it.", "Check if it worked.",
        "Continue the flow.", "Do everything required.",
    )

    def reach_procedures(self, mutate=None):
        run = PackRun("saas-accounts", mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    def test_vague_whole_steps_are_rejected(self) -> None:
        for vague in self.VAGUE_ACTIONS:
            with self.subTest(action=vague):
                def blur(pack, vague=vague):
                    procedure(pack, "T1")["steps"][0]["action"] = vague
                run = self.reach_procedures(blur)
                with self.assertRaisesRegex(StageError, "action is abstract; say who does which atomic action"):
                    run.submit("procedures")

    def test_an_unobservable_expected_result_is_rejected(self) -> None:
        def blur(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "It works."
        run = self.reach_procedures(blur)
        with self.assertRaisesRegex(StageError, "expected result is not observable"):
            run.submit("procedures")

    def test_concrete_steps_that_share_a_verb_are_not_flagged(self) -> None:
        from procedures import ABSTRACT_ACTION
        for concrete in ("Open the member management page of ACCOUNT_A.", "Validate the invitation for EMAIL_NEW.",
                         "Access the audit log of ACCOUNT_A as USER_OWNER_A."):
            self.assertIsNone(ABSTRACT_ACTION.search(concrete), concrete)

    def test_a_missing_selector_stays_an_unknown_instead_of_being_invented(self) -> None:
        def unknown_selector(pack):
            procedure(pack, "T1")["unknowns"] = [{"kind": "MISSING_SELECTOR",
                                                  "detail": "the evidence names no locator for the invite form"}]
        run = self.reach_procedures(unknown_selector)
        run.submit("procedures")
        pipeline_result = run.submit  # noqa: F841 - procedures accepted; finalize to read the case
        import pipeline
        pipeline.finalize_run(run.run_dir, ["JSON"])
        case = run.output("test-cases/TC-001.json")
        self.assertEqual("READY", case["status"])  # a human can still run it
        self.assertEqual("NEEDS_SELECTOR", case["automation_readiness"])  # automation gap is explicit

    def test_the_same_canonical_case_translates_to_ui_or_api_automation_without_changing_its_oracle(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        case = run.output("test-cases/TC-001.json")

        def translate(case, adapter):
            # The documented mapping: preconditions -> setup, test data -> fixtures,
            # action -> adapter operation, expected result -> assertion.
            return {"setup": list(case["preconditions"]),
                    "fixtures": {row["name"]: row["description"] for row in case["test_data"]},
                    "operations": [f"{adapter}:{step['action']}" for step in case["steps"]],
                    "assertions": [step["expected_result"] for step in case["steps"]]}

        ui, api = translate(case, "ui"), translate(case, "api")
        self.assertEqual(ui["assertions"], api["assertions"])
        self.assertEqual(ui["fixtures"], api["fixtures"])
        self.assertTrue(all(ui["assertions"]))
        self.assertTrue(all(re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in ui["fixtures"]))

    def test_canonical_cases_carry_no_tool_specific_syntax(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        index = run.output("test-cases.json")
        tool_syntax = re.compile(r"page\.(?:click|fill|goto)|cy\.get|\[data-testid|getByRole|locator\(|#[a-z][\w-]*\b\s*\{")
        for entry in index["test_cases"]:
            case = run.output(f"test-cases/{entry['id']}.json")
            text = " ".join([*case["preconditions"], *(s["action"] + " " + (s["expected_result"] or "") for s in case["steps"])])
            self.assertIsNone(tool_syntax.search(text), entry["id"])


class ExecutableProcedureTests(unittest.TestCase):
    """Semantic weaknesses a passing procedure must not hide: vague chained steps,
    invented environment/physical techniques and invented performance thresholds."""

    def reach(self, name, mutate=None):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    def test_chained_vague_clauses_are_rejected(self) -> None:
        for vague in ("Access the system and perform the operation.",
                      "Open the application, then validate the result.",
                      "Acessar o sistema e realizar a operação."):
            with self.subTest(action=vague):
                self.assertIsNotNone(ABSTRACT_ACTION.search(vague))
        for concrete in ("Access the billing page of ACCOUNT_A and open INVOICE_A.",
                         "Open the application settings and select the Language tab."):
            self.assertIsNone(ABSTRACT_ACTION.search(concrete), concrete)

    def test_environment_and_physical_manipulation_is_recognized_across_domains(self) -> None:
        for action in ("Restart the application service in the test environment.",
                       "Disconnect the network of the payment gateway.",
                       "Cover the label of PACKAGE_A so the scanner cannot read it.",
                       "Power off the infusion pump device during the transfer.",
                       "Reiniciar o serviço de integração do ambiente de teste.",
                       "Detener el servicio de facturación."):
            self.assertIsNotNone(ENVIRONMENT_CONTROL.search(action), action)
        for action in ("Block the user account of CUSTOMER_A.", "Stop editing and save ORDER_A.",
                       "Cancel the order of CUSTOMER_B.", "Print the label of PACKAGE_A."):
            self.assertIsNone(ENVIRONMENT_CONTROL.search(action), action)

    def test_an_ungrounded_restart_is_rejected(self) -> None:
        def restart(pack):
            procedure(pack, "T1")["steps"].insert(0, {
                "action": "Restart the application service in the test environment.",
                "expected_result": "The application answers requests again."})
        run = self.reach("saas-accounts", restart)
        with self.assertRaisesRegex(StageError, "never invent the technique"):
            run.submit("procedures")

    def test_an_unknown_restart_path_keeps_the_scenario_but_is_not_ready(self) -> None:
        def restart(pack):
            proc = procedure(pack, "T1")
            proc["steps"].insert(0, {"action": "Restart the application service in the test environment.",
                                     "expected_result": "The application answers requests again."})
            proc["oracle_step"] = len(proc["steps"])
            proc["unknowns"] = [{"kind": "UNKNOWN_SETUP_PATH",
                                 "detail": "the selected sources do not say which service or how it restarts"}]
        run = self.reach("saas-accounts", restart)
        run.submit("procedures")
        import pipeline
        pipeline.finalize_run(run.run_dir, ["JSON"])
        case = run.output("test-cases/TC-001.json")
        self.assertEqual("NEEDS_REVIEW", case["status"])

    def test_a_restart_supported_by_cited_evidence_is_accepted(self) -> None:
        def restart(pack):
            proc = procedure(pack, "T1")
            proc["steps"].insert(0, {"action": "Restart the application service in the test environment.",
                                     "expected_result": "The application answers requests again."})
            proc["oracle_step"] = len(proc["steps"])
            proc["evidence_refs"] = [*proc.get("evidence_refs", []),
                                     {"source": "src/invitations.py", "reference": "service entry point", "supports": [1]}]
        run = self.reach("saas-accounts", restart)
        run.submit("procedures")

    def test_an_invented_physical_suppression_technique_is_rejected_in_another_language(self) -> None:
        def suppress(pack):
            procedure(pack, "T1")["steps"].insert(0, {
                "action": "Cubrir la etiqueta del PEDIDO_BORRADOR_A para que el lector no la lea.",
                "expected_result": "El lector no registra la etiqueta."})
        run = self.reach("erp-sales-orders", suppress)
        with self.assertRaisesRegex(StageError, "suppresses a signal"):
            run.submit("procedures")

    def test_an_expected_result_that_only_echoes_the_action_is_rejected(self) -> None:
        from procedures import ACTION_ECHO
        for echo in ("The request is sent.", "A resposta é recebida.", "O envio é processado.",
                     "As duas solicitações chegam juntas.", "La respuesta es recibida.", "O formulário processa a tentativa."):
            self.assertIsNotNone(ACTION_ECHO.search(echo), echo)
        for observable in ("The response is 422 with code AMOUNT_EXCEEDS_CAPTURE.",
                           "A resposta contabiliza a leitura como rejeitada.", "The request is rejected with 401."):
            self.assertIsNone(ACTION_ECHO.search(observable), observable)

        def echo(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "The request is sent."
        run = self.reach("saas-accounts", echo)
        with self.assertRaisesRegex(StageError, "only says the action happened"):
            run.submit("procedures")

    def test_alternative_outcomes_are_not_an_oracle(self) -> None:
        from procedures import ALTERNATIVE_OUTCOMES
        for either in ("The record is shown or access is denied.", "O registro é exibido ou o acesso é negado.",
                       "O formulário aceita o envio ou exibe a validação da transição."):
            self.assertIsNotNone(ALTERNATIVE_OUTCOMES.search(either), either)
        for single in ("The order is finalized without error or exception.", "A caixa é associada à ordem e o status é Separada.",
                       "The status is Active or Suspended in the list filter."):
            self.assertIsNone(ALTERNATIVE_OUTCOMES.search(single), single)

        def either(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "The page is shown or access is denied."
        run = self.reach("saas-accounts", either)
        with self.assertRaisesRegex(StageError, "offers alternative outcomes"):
            run.submit("procedures")

    def test_every_fixture_used_is_described_in_test_data(self) -> None:
        def undescribed(pack):
            procedure(pack, "T1")["preconditions"].append("USER_AUDITOR_B watches the account.")
        run = self.reach("saas-accounts", undescribed)
        with self.assertRaisesRegex(StageError, r"uses fixtures \['USER_AUDITOR_B'\] that test_data does not describe"):
            run.submit("procedures")

    def test_codes_from_the_selected_sources_are_vocabulary_not_fixtures(self) -> None:
        # api-refunds steps quote error codes (AMOUNT_EXCEEDS_CAPTURE, TOO_MANY_REFUNDS) that the
        # selected specification and service use; they need no test_data row.
        run = PackRun("api-refunds")
        self.addCleanup(run.close)
        run.finalize(("JSON",))

    def test_a_fixture_named_in_the_sources_still_needs_a_description(self) -> None:
        from procedures import source_vocabulary
        vocabulary = source_vocabulary(["raise Error('TOO_MANY_REFUNDS')", "user = USER_OWNER_A  # test helper",
                                        "PAYMENT_CAPTURED_100 = make_payment()", "EPC_LENGTH = 24"])
        self.assertEqual({"TOO_MANY_REFUNDS", "EPC_LENGTH"}, vocabulary)

        def undescribed(pack):
            # the same token also appears in the selected existing tests
            tests_file = next(source for source in pack["sources"].values() if source["role"] == "TEST_ASSET")
            tests_file["text"] += "\n# USER_OWNER_A is the fixture owner used above\n"
            proc = procedure(pack, "T1")
            proc["test_data"] = [row for row in proc["test_data"] if row["name"] != "USER_OWNER_A"]
        run = self.reach("saas-accounts", undescribed)
        with self.assertRaisesRegex(StageError, r"uses fixtures \['USER_OWNER_A'\]"):
            run.submit("procedures")

    def test_literal_request_content_is_not_counted_as_actions(self) -> None:
        from procedures import compressed_action
        for single in ('As CLIENT_A, in the HTTP client, send POST to /api/v1/scan/?reader_name=GATE_A with the body [{"data": {"id": "TAG_A"}}].',
                       "Como INTEGRACAO_A, no cliente HTTP, enviar POST para /api/v1/pedidos/?read_only=true com o corpo {\"item\": 1}."):
            self.assertFalse(compressed_action(single), single)
        for compound in ("As ADMIN_A, open ORDER_A, select Cancel and then save the form.",
                         "Na APP, abrir Pedidos, informar PEDIDO_A e clicar em Enviar."):
            self.assertTrue(compressed_action(compound), compound)

    def test_object_first_physical_manipulation_is_recognized(self) -> None:
        for action in ("Pass CRATE_A through the gate with the label covered.",
                       "Passar CAIXA_A pelo leitor com a etiqueta coberta.",
                       "Run the export with the database connection disconnected.",
                       "Pasar la caja con la etiqueta cubierta."):
            self.assertIsNotNone(ENVIRONMENT_CONTROL.search(action), action)
        for action in ("Print the label of PACKAGE_A.", "Open the covered-items report.", "Scan the label of CRATE_A."):
            self.assertIsNone(ENVIRONMENT_CONTROL.search(action), action)

    def test_an_undefined_sla_cannot_become_a_pass_fail_threshold(self) -> None:
        def threshold(pack):
            procedure(pack, "T1")["steps"][-1]["expected_result"] += " The response arrives in under 200 ms."
        run = self.reach("saas-accounts", threshold)
        with self.assertRaisesRegex(StageError, "undefined SLA stays undefined"):
            run.submit("procedures")

    def test_a_load_ramp_is_experiment_configuration_not_an_oracle(self) -> None:
        def ramp(pack):
            proc = procedure(pack, "T1")
            proc["steps"][0]["action"] += " Repeat with 10, 20 and 40 requests per second."
        run = self.reach("saas-accounts", ramp)
        run.submit("procedures")  # numbers in the action are the declared experiment, not a pass/fail rule

    def test_a_threshold_the_design_states_is_accepted(self) -> None:
        def stated(pack):
            test = next(t for t in pack["stages"]["design"]["tests"] if t["key"] == "T1")
            test["objective"] += " within 5 seconds"
            procedure(pack, "T1")["steps"][-1]["expected_result"] += " within 5 seconds"
        run = self.reach("saas-accounts", stated)
        run.submit("procedures")



class ExecutionContractTests(unittest.TestCase):
    """Self-contained execution: actors have a starting context, named requests travel as a
    contract, state restoration is explicit, and execution variants place, never clone."""

    def submit(self, name, mutate):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    @staticmethod
    def acting(pack, precondition=None):
        item = procedure(pack, "T1")
        item["test_data"].append({"name": "USER_ADMIN_B", "description": "second user with the Owner role in ACCOUNT_A"})
        item["steps"][0]["action"] = "As USER_ADMIN_B, open the member management page of ACCOUNT_A."
        if precondition:
            item["preconditions"].append(precondition)

    def test_an_actor_without_a_starting_context_is_rejected(self) -> None:
        run = self.submit("saas-accounts", self.acting)
        with self.assertRaisesRegex(StageError, "acts as USER_ADMIN_B, but no precondition or earlier step"):
            run.submit("procedures")

    def test_an_actor_whose_session_is_a_precondition_is_accepted(self) -> None:
        run = self.submit("saas-accounts", lambda pack: self.acting(pack, "USER_ADMIN_B is signed in to ACCOUNT_A."))
        run.submit("procedures")

    def test_a_load_case_naming_a_request_must_carry_its_contract(self) -> None:
        run = self.submit("api-refunds", lambda pack: procedure(pack, "D2").pop("request_contract"))
        with self.assertRaisesRegex(StageError, "describe that request in request_contract"):
            run.submit("procedures")

    def test_a_ui_driven_concurrency_case_needs_no_request_contract(self) -> None:
        run = self.submit("saas-accounts", None)
        self.assertNotIn("request_contract", procedure(run.pack, "D2"))
        run.submit("procedures")

    def test_a_request_contract_is_a_description_not_a_tool_invocation(self) -> None:
        def tool(pack):
            procedure(pack, "D2")["request_contract"]["body"] = "curl -X POST /refunds -d amount=60.00"
        run = self.submit("api-refunds", tool)
        with self.assertRaisesRegex(StageError, "describes the request, not a tool invocation"):
            run.submit("procedures")

    def test_a_request_contract_cannot_invent_a_threshold(self) -> None:
        def invented(pack):
            procedure(pack, "D2")["request_contract"]["measurements"] = ["p95 latency under 350 ms"]
        run = self.submit("api-refunds", invented)
        with self.assertRaisesRegex(StageError, "request_contract.measurements asserts"):
            run.submit("procedures")

    def test_contract_fixtures_must_be_described(self) -> None:
        def undefined(pack):
            procedure(pack, "D2")["request_contract"]["fixture_pool"] = "CLIENT_A and CLIENT_B credentials"
        run = self.submit("api-refunds", undefined)
        with self.assertRaisesRegex(StageError, r"uses fixtures \['CLIENT_B'\]"):
            run.submit("procedures")

    def test_contract_and_state_contract_reach_the_published_case(self) -> None:
        run = PackRun("api-refunds")
        self.addCleanup(run.close)
        run.finalize(("JSON", "MARKDOWN"))
        index = run.output("test-cases.json")
        cases = [run.output(entry["file"]) for entry in index["test_cases"]]
        contract = next(c for c in cases if c.get("request_contract"))
        self.assertEqual(("POST", "/refunds"), (contract["request_contract"]["method"], contract["request_contract"]["endpoint"]))
        for case in cases:
            self.assertEqual("SELF_CLEANING" if case["cleanup"] else "REQUIRES_FIXTURE_RESET", case["state_contract"])
        markdown = (run.artifacts / "output" / next(e["markdown_file"] for e in index["test_cases"]
                                                     if e["id"] == contract["id"])).read_text(encoding="utf-8")
        self.assertIn("## Request contract", markdown)
        self.assertIn("## State restoration", markdown)

    def test_a_physical_execution_variant_places_the_case_in_the_physical_view_without_a_clone(self) -> None:
        def variant(pack):
            procedure(pack, "T1")["execution_variants"] = [
                {"kind": "PHYSICAL_DEVICE", "description": "Submit the invitation from a real handheld enrolled to ACCOUNT_A."}]
        run = PackRun("saas-accounts", variant)
        self.addCleanup(run.close)
        run.finalize(("JSON",))
        organization = run.output("organization.json")
        physical = next(g for g in organization["groups"] if g["id"] == "PHYSICAL_DEVICE")
        self.assertEqual([("TC-001", "EXECUTION_VARIANT")], [(m["case"], m["via"]) for m in physical["members"]])
        self.assertEqual(len(run.output("test-cases.json")["test_cases"]), len(organization["memberships"]))

    def test_an_execution_variant_must_say_how_it_differs(self) -> None:
        run = self.submit("saas-accounts", lambda pack: procedure(pack, "T1").update(
            execution_variants=[{"kind": "PHYSICAL_DEVICE", "description": "real device"}]))
        with self.assertRaisesRegex(StageError, "must describe how that execution differs"):
            run.submit("procedures")



class ProcedureBoilerplateTests(unittest.TestCase):
    """Low-information procedures are rejected; Design and the Test Case count never change."""

    def submit(self, name, mutate):
        run = PackRun(name, mutate)
        self.addCleanup(run.close)
        run.through("expansion")
        return run

    def test_a_semantically_empty_outcome_is_rejected(self) -> None:
        def empty(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "An observable result is shown on the affected resource."
        with self.assertRaisesRegex(StageError, "step 1 expected result names nothing specific"):
            self.submit("saas-accounts", empty).submit("procedures")

    def test_specific_outcomes_and_semantic_fixtures_stay_valid(self) -> None:
        from procedures import semantically_empty
        self.assertTrue(semantically_empty("The expected behavior is observed in the system.", set()))
        self.assertTrue(semantically_empty("O resultado esperado fica visível no recurso afetado.", set()))
        self.assertFalse(semantically_empty("The invite form is shown.", set()))
        self.assertFalse(semantically_empty("The result is shown for USER_A.", {"USER_A"}))
        self.assertFalse(semantically_empty('The system shows "Seat limit reached".', set()))
        self.assertFalse(semantically_empty("The response has status 409.", set()))

    def test_truncated_or_unbalanced_prose_is_rejected(self) -> None:
        def truncated(pack):
            procedure(pack, "T1")["steps"][1]["action"] = "Submit an invitation for EMAIL_NEW and"
        with self.assertRaisesRegex(StageError, "step 2 action is truncated or unbalanced"):
            self.submit("saas-accounts", truncated).submit("procedures")

        def unbalanced(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "The page shows the invite form (with the email field."
        with self.assertRaisesRegex(StageError, "step 1 expected result is truncated or unbalanced"):
            self.submit("saas-accounts", unbalanced).submit("procedures")

    def test_the_oracle_step_keeps_the_designed_message_number_or_code(self) -> None:
        def paraphrased(pack):
            procedure(pack, "T2")["steps"][-1]["expected_result"] = "The API returns an error saying the amount exceeds the capture."
        with self.assertRaisesRegex(StageError, r"drops what the designed oracle states exactly \['422', 'AMOUNT_EXCEEDS_CAPTURE'\]"):
            self.submit("api-refunds", paraphrased).submit("procedures")

    def test_one_oracle_wording_for_different_oracles_is_boilerplate(self) -> None:
        def boilerplate(pack):
            for key in ("T1", "T2", "T5"):
                procedure(pack, key)["steps"][-1]["expected_result"] = "The API answers the request with its documented status."
        with self.assertRaisesRegex(StageError, "3 procedures designed for different oracles observe the same result"):
            self.submit("api-refunds", boilerplate).submit("procedures")

    def test_a_rejected_procedure_never_changes_design_or_the_test_case_count(self) -> None:
        import pipeline
        from common import file_digest

        def empty(pack):
            procedure(pack, "T1")["steps"][0]["expected_result"] = "An observable result is shown on the affected resource."
        run = self.submit("api-refunds", empty)
        stages = run.run_dir / "stages"
        before = {name: file_digest(stages / name) for name in ("design.result.json", "expansion.result.json")}
        with self.assertRaises(StageError):
            run.submit("procedures")
        self.assertEqual(before, {name: file_digest(stages / name) for name in before})
        designed = len(pipeline._result(run.run_dir, "design")["tests"]) + len(pipeline._result(run.run_dir, "expansion")["tests"])
        from support import load_pack
        run.pack["stages"]["procedures"] = load_pack("api-refunds")["stages"]["procedures"]
        run.submit("procedures")
        pipeline.finalize_run(run.run_dir, ["JSON"])
        self.assertEqual(designed, len(run.output("test-cases.json")["test_cases"]))


if __name__ == "__main__":
    unittest.main()
