from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_reconciliation import audit_reconciliation  # noqa: E402
from risk_expansion import expand_risk_profiles  # noqa: E402
from scenario_independence import build_scenario_family_pipeline  # noqa: E402
from source_inventory import SourceInventoryError, audit_source_inventory  # noqa: E402
from validate_output import validate  # noqa: E402
from workflow_entrypoints import dispatch  # noqa: E402
from tests.test_workflow_entrypoints import generation_request  # noqa: E402


def cp(number: int, statement: str) -> dict:
    return {
        "id": f"CP-{number:03d}", "requirement_ref": "REQ-001", "statement": statement,
        "clause_refs": [f"CLAUSE-{number:03d}"],
        "source_refs": [{"source": "requirements.md", "reference": f"rule {number}"}],
        "disposition": "TEST_CASE", "target_refs": [],
    }


def profile(title: str, oracle: str, **values: object) -> dict:
    result = {
        "title": title, "behavior": title, "scenario_family": "Order submission",
        "scenario_family_title": "Order submission", "test_basis": "ACCEPTANCE",
        "primary_type": "FUNCTIONAL", "normative_oracle": oracle,
        "assertion_oracle": oracle, "observation_target": title,
        "actor": "operator", "state": "draft", "setup": "draft order exists",
        "input_partition": title, "trigger": "submit", "event": "order submitted",
        "execution_boundary": title, "objective": title,
        "material_preconditions": ["An operator and an isolated draft order exist."],
    }
    result.update(values)
    return result


class V22AtomicDesignTests(unittest.TestCase):
    def test_shared_event_creates_merge_metadata_without_destroying_atomic_tests(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "Status changes"), cp(2, "Audit is recorded")],
            {
                "CP-001": profile("Change status", "Status is SUBMITTED."),
                "CP-002": profile("Record audit", "An audit record exists."),
            },
        )
        self.assertEqual(2, len(design["test_identities"]))
        self.assertEqual(1, len(design["scenarios"]))
        self.assertEqual(["TC-001", "TC-002"], design["scenarios"][0]["test_case_refs"])
        self.assertEqual(1, len(design["merge_candidates"]))
        self.assertEqual(0, design["metrics"]["actual_merges"])

    def test_missing_implementation_keeps_acceptance_design_record(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "Submit order")],
            {"CP-001": profile(
                "Submit order", "Status is SUBMITTED.",
                execution_status="BLOCKED_IMPLEMENTATION_GAP",
            )},
        )
        identity = design["test_identities"][0]
        self.assertEqual("ACCEPTANCE", identity.test_basis)
        self.assertEqual("BLOCKED_IMPLEMENTATION_GAP", identity.execution_status)
        self.assertEqual("Status is SUBMITTED.", identity.normative_oracle)

    def test_acceptance_and_characterization_can_coexist_without_oracle_rewrite(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "Identifier length")],
            {"CP-001": [
                profile("Accept normative length", "A 32-character value is accepted."),
                profile(
                    "Characterize observed length", "unused",
                    test_basis="CHARACTERIZATION", normative_oracle=None,
                    implementation_oracle="A 24-character value is currently accepted.",
                    finding_refs=["FND-001"], execution_status="NEEDS_REVIEW",
                ),
            ]},
        )
        identities = design["test_identities"]
        self.assertEqual(["ACCEPTANCE", "CHARACTERIZATION"], [item.test_basis for item in identities])
        self.assertEqual("A 32-character value is accepted.", identities[0].normative_oracle)
        self.assertEqual("A 24-character value is currently accepted.", identities[1].normative_oracle)

    def test_e2e_composes_atomic_cases_instead_of_hiding_them(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "Create"), cp(2, "Submit"), cp(3, "Journey")],
            {
                "CP-001": profile("Create", "Draft exists."),
                "CP-002": profile("Submit", "Status is SUBMITTED."),
                "CP-003": profile(
                    "Create and submit journey", "The submitted order is traceable.",
                    test_basis="E2E", primary_type="E2E", composes=["TC-001", "TC-002"],
                ),
            },
        )
        self.assertEqual(("TC-001", "TC-002"), design["test_identities"][2].composes)
        self.assertEqual(1, design["metrics"]["e2e_tests"])

    def test_exploratory_risk_does_not_invent_an_oracle(self) -> None:
        design = build_scenario_family_pipeline(
            [cp(1, "Interrupted submission")],
            {"CP-001": profile(
                "Explore interruption", "unused", test_basis="EXPLORATORY",
                primary_type="EXPLORATORY", normative_oracle=None,
                execution_status="EXPLORATORY", question_refs=["Q-001"],
            )},
        )
        self.assertIsNone(design["test_identities"][0].normative_oracle)

    def test_risk_expansion_adds_supported_derived_and_exploratory_candidates(self) -> None:
        base = {"CP-001": profile("Submit", "Status is SUBMITTED.")}
        conditions = [
            {"id": "RISK-001", "oracle_support": "NORMATIVE", "risk_class": "CONCURRENCY"},
            {"id": "RISK-002", "oracle_support": "UNDEFINED", "risk_class": "RECOVERY"},
        ]
        expanded, metrics = expand_risk_profiles(
            base, conditions, [
                {"risk_condition_ref": "RISK-001", "coverage_point_ref": "CP-001", "profile": profile(
                    "Concurrent submission", "Only one state transition is committed.",
                    primary_type="CONCURRENCY",
                )},
                {"risk_condition_ref": "RISK-002", "coverage_point_ref": "CP-001", "profile": profile(
                    "Explore response loss", "unused", normative_oracle=None,
                    question_refs=["Q-001"], primary_type="RECOVERY",
                )},
            ], coverage_point_ids={"CP-001"},
        )
        self.assertEqual(3, len(expanded["CP-001"]))
        self.assertEqual("DERIVED", expanded["CP-001"][1]["test_basis"])
        self.assertEqual("EXPLORATORY", expanded["CP-001"][2]["test_basis"])
        self.assertEqual({"risk_candidates_added": 2, "exploratory_policy_gaps": 1}, metrics)

    def test_source_inventory_cannot_pass_when_authoritative_reference_is_omitted(self) -> None:
        sources = [{"path": "requirements.md", "role": "FUNCTIONAL_AUTHORITY"}]
        inventory = [{
            "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
            "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED",
            "reason": "Selected approved requirements.",
        }]
        with self.assertRaisesRegex(SourceInventoryError, "Referenced authoritative"):
            audit_source_inventory(
                sources, inventory, referenced_authoritative_paths=["business-rules.md"]
            )

    def test_benchmark_reconciliation_explains_ideas_without_targeting_count(self) -> None:
        result = audit_reconciliation(
            [{"id": "LEGACY-1"}, {"id": "LEGACY-2"}],
            [
                {"benchmark_item_ref": "LEGACY-1", "disposition": "COVERED_BY", "target_refs": ["TC-001"]},
                {"benchmark_item_ref": "LEGACY-2", "disposition": "KNOWN_GAP", "target_refs": [], "reason": "No selected authority."},
            ],
            test_case_ids={"TC-001"}, question_ids=set(),
        )
        self.assertEqual(2, result["benchmark_items_reconciled"])
        self.assertFalse(result["target_count_used_as_goal"])

    def test_shared_runtime_emits_a_valid_v22_atomic_view(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request["schema_version"] = "2.2"
            request["source_inventory"] = [{
                "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
                "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED",
                "reason": "Selected approved requirement.",
            }]
            request["scenario_profiles"]["CP-001"].update({
                "scenario_family": "Dashboard refresh", "test_basis": "ACCEPTANCE",
                "primary_type": "FUNCTIONAL", "automation_candidate": True,
                "automation_layer": "UI", "automation_tool_hint": "PLAYWRIGHT",
            })
            result = dispatch("ftd-gen", **request)
            self.assertEqual("2.2", result["cases"][0]["schema_version"])
            self.assertEqual("ACCEPTANCE", result["cases"][0]["test_basis"])
            self.assertEqual(0, result["design"]["metrics"]["actual_merges"])
            diagnostics = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
            serialized_steps = sum(len(case["steps"]) for case in result["cases"])
            self.assertEqual(serialized_steps, diagnostics["steps_total"])
            self.assertIsNotNone(diagnostics["finished_at"])
            self.assertTrue(diagnostics["stage_provenance"])
            self.assertTrue(all(
                stage["status"] == "COMPLETE"
                and stage["validation_result"] == "PASS"
                for stage in diagnostics["stage_provenance"]
            ))
            self.assertTrue(all(
                gate["status"] == "PASS"
                for gate in diagnostics["quality_gates"]
            ))
            report = (root / "artifacts" / "output" / "report.html").read_text(encoding="utf-8")
            self.assertIn("Normative TCs", report)
            self.assertIn("Automation Candidate", report)

    def test_v22_reference_integrity_is_reciprocal_and_catches_wrong_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = generation_request(root, root / "artifacts")
            request.update({
                "schema_version": "2.2",
                "formats": ["JSON", "MARKDOWN", "HTML"],
                "source_inventory": [{
                    "path": "requirements.md", "authority": "NORMATIVE_PRIMARY",
                    "family": "FUNCTIONAL_REQUIREMENT", "disposition": "INCLUDED",
                    "reason": "Selected approved requirement.",
                }],
                "questions": [{
                    "id": "Q-001", "related_test_cases": ["TC-001"],
                    "requirement_refs": ["REQ-001"],
                    "source_refs": [{"source": "requirements.md", "reference": "RF-001"}],
                    "question": "Where is the dashboard opened in the test environment?",
                    "reason": "Execution detail is absent.", "blocking": False,
                    "impact": "EXECUTION_DETAIL",
                }],
                "findings": [{
                    "id": "FND-001", "type": "IMPLEMENTATION_DIVERGENCE",
                    "statement": "The selected implementation does not expose the documented counter.",
                    "requirement_refs": ["REQ-001"],
                    "source_refs": [{"source": "requirements.md", "reference": "RF-001"}],
                    "related_test_cases": ["TC-001"],
                    "coverage_disposition": "COVERED_BY_EXISTING_SCENARIO",
                }],
            })
            request["scenario_profiles"]["CP-001"].update({
                "scenario_family": "Dashboard refresh", "test_basis": "ACCEPTANCE",
                "primary_type": "FUNCTIONAL", "question_refs": ["Q-001"],
                "finding_refs": ["FND-001"],
            })
            result = dispatch("ftd-gen", **request)
            output = root / "artifacts" / "output"
            self.assertEqual([], validate(output))
            case_path = output / "test-cases" / "TC-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["question_refs"] = ["Q-999"]
            case_path.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
            errors = validate(output)
            self.assertTrue(any("unknown question: Q-999" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
