"""FTD ADR and Azure DevOps: a local delta, and a guarded publication against a fake Azure only.
Nothing here connects to a real organization."""

from __future__ import annotations

import inspect
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adr_support as fx  # noqa: E402
import adr  # noqa: E402
import adr_azure  # noqa: E402
import azure_export as az  # noqa: E402
import azure_publish as pub  # noqa: E402
from integrations import azure_devops as ado  # noqa: E402
from test_azure_publish import FakeAzure, TARGET  # noqa: E402


class TaggedAzure(FakeAzure):
    """The shared fake, returning Work Item tags as the remote contract (and the REST remote) does."""

    def get_work_items(self, project_id, ids):
        items = super().get_work_items(project_id, ids)
        for item in items.values():
            item.setdefault("tags", (item.get("fields") or {}).get("System.Tags", ""))
        return items


class HistoryAzure(TaggedAzure):
    """A fake organization that can also report (read-only) execution history."""

    def __init__(self, executed: set[int] | None = None, unreadable: bool = False):
        super().__init__()
        self.executed = executed or set()
        self.unreadable = unreadable

    def test_case_history(self, project_id, plan_id, work_item_id):
        self._log("test_case_history")
        if self.unreadable:
            raise PermissionError("no access to test results")
        executed = work_item_id in self.executed
        return {"executed": executed, "results": int(executed), "evidence": "NOT_QUERIED"}


class AdrAzureTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.run = fx.AdrRun()
        self.addCleanup(self.run.close)
        fx.write_corpus(self.run.corpus)
        self.run_dir = self.run.run_dir
        self.azure = HistoryAzure()
        # The suite was published normally (v2.4 behaviour) before any ADR arrived.
        az.convert_run(self.run_dir)
        pub.prepare(self.run_dir, TARGET, self.azure)
        pub.apply(self.run.artifacts / "output" / "azure" / "publication-plan.json", self.azure, approved=True)
        self.work_item = {key: int(entry["external_id"]) for key, entry in self.state()["test_cases"].items()}

    def state(self) -> dict:
        return json.loads((self.run_dir / "integration-state" / "azure-devops.json").read_text(encoding="utf-8"))

    def package(self, adr_id: str = "adr-001") -> dict:
        return json.loads((self.run.artifacts / "output" / "adr" / adr_id / "azure" / "azure-adr-export-package.json")
                          .read_text(encoding="utf-8"))

    def prepare(self, adr_id: str = "adr-001", remote=None, **kwargs) -> dict:
        return pub.prepare(self.run_dir, TARGET, remote or self.azure, adr=adr_id, **kwargs)

    def plan_path(self, adr_id: str = "adr-001") -> Path:
        return self.run.artifacts / "output" / "adr" / adr_id / "azure" / "publication-plan.json"

    def operations(self, adr_id: str = "adr-001") -> dict:
        plan = json.loads(self.plan_path(adr_id).read_text(encoding="utf-8"))
        return {op["export_key"]: op for op in plan["operations"]["test_cases"]}


class DeltaPackageTests(AdrAzureTestCase):
    def test_the_delta_holds_only_the_changed_definitions_with_stable_keys(self) -> None:
        self.run.round()
        package = self.package()
        self.assertEqual({"canonical:TC-002": "UPDATE", "adr:TC-013": "CREATE"},
                         {r["export_key"]: r["adr"]["action"] for r in package["test_cases"]})
        self.assertEqual(11, package["diagnostics"]["untouched"])
        self.assertEqual(0, package["diagnostics"]["delete_operations"])
        placed = {k for s in package["suites"] for k in s["test_case_refs"]}
        self.assertEqual({"canonical:TC-002", "adr:TC-013"}, placed)
        self.assertTrue(package["test_cases"][0]["adr"]["semantic_change"])

    def test_v24_metadata_is_unchanged_and_adr_metadata_is_additive(self) -> None:
        self.run.round()
        record = next(r for r in self.package()["test_cases"] if r["export_key"] == "canonical:TC-002")
        payload = ado.map_test_case({**record, "id": record["export_key"], "tags": record["execution_tags"]})
        plain = ado.work_item_fields(payload, record["export_key"])
        with_adr = adr_azure.adr_fields(record, payload)
        self.assertEqual(ado.read_ftd_metadata(plain["System.Description"]),
                         ado.read_ftd_metadata(with_adr["System.Description"]))
        self.assertTrue(with_adr["System.Description"].startswith(plain["System.Description"]))
        self.assertEqual({k: v for k, v in plain.items() if k != "System.Description"},
                         {k: v for k, v in with_adr.items() if k != "System.Description"})
        metadata = adr_azure.read_adr_metadata(with_adr["System.Description"])
        self.assertEqual(("adr-001", "UPDATE", ["ADR-007"]),
                         (metadata["adr_run_id"], metadata["action"], metadata["decision_refs"]))
        self.assertIsNone(adr_azure.read_adr_metadata(plain["System.Description"]))

    def test_new_case_keys_never_embed_the_round_id_and_survive_later_rounds(self) -> None:
        self.run.round()
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        self.run.round(fx.round2_analysis(), fx.round2_procedures())
        keys = {r["export_key"]: r["adr"]["action"] for r in self.package("adr-002")["test_cases"]}
        self.assertEqual({"adr:TC-013": "UPDATE", "adr:TC-014": "CREATE"}, keys)
        self.assertFalse([k for k in keys if re.search(r"adr-\d", k)])


class GuardedPublicationTests(AdrAzureTestCase):
    def test_an_unexecuted_existing_case_updates_the_same_work_item_and_nothing_is_duplicated(self) -> None:
        self.run.round()
        before = len(self.azure.items)
        summary = self.prepare()["summary"]
        self.assertEqual((1, 1, 0, 0, 0), (summary["create_test_cases"], summary["update_test_cases"],
                                           summary["review_required"], summary["conflicts"], summary["delete_operations"]))
        self.assertEqual(11, summary["untouched"])
        operations = self.operations()
        self.assertEqual(self.work_item["canonical:TC-002"], int(operations["canonical:TC-002"]["work_item_id"]))
        self.assertNotIn("canonical:TC-001", operations)
        writes_before = len(self.azure.writes())
        self.assertEqual("APPROVAL_REQUIRED", pub.apply(self.plan_path(), self.azure)["status"])
        self.assertEqual(writes_before, len(self.azure.writes()))
        result = pub.apply(self.plan_path(), self.azure, confirmation="PUBLISH Shop / Release")
        self.assertEqual("APPLIED", result["status"])
        self.assertEqual(before + 1, len(self.azure.items))  # only TC-013 is new
        updated = self.azure.items[self.work_item["canonical:TC-002"]]
        self.assertTrue(updated["title"].startswith("TC-002 — Invitation expires after three days"))
        self.assertEqual("adr-001", adr_azure.read_adr_metadata(updated["fields"]["System.Description"])["adr_run_id"])
        self.assertEqual("adr-001", self.state()["test_cases"]["canonical:TC-002"]["adr_run_id"])
        again = self.prepare()["summary"]
        self.assertEqual((0, 0, 2), (again["create_test_cases"], again["update_test_cases"], again["unchanged"]))

    def test_a_later_round_updates_the_work_item_an_earlier_round_created(self) -> None:
        self.run.round()
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        created = int(self.state()["test_cases"]["adr:TC-013"]["external_id"])
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        self.run.round(fx.round2_analysis(), fx.round2_procedures())
        self.prepare("adr-002", review={"TC-013": adr_azure.REVIEW_UPDATE_SAME})
        operations = self.operations("adr-002")
        self.assertEqual(("UPDATE", created), (operations["adr:TC-013"]["action"], int(operations["adr:TC-013"]["work_item_id"])))
        self.assertEqual("CREATE", operations["adr:TC-014"]["action"])

    def test_a_remote_edit_or_a_missing_ftd_key_is_a_conflict(self) -> None:
        self.run.round()
        self.azure.items[self.work_item["canonical:TC-002"]]["rev"] += 1
        self.assertEqual("REMOTE_CHANGED_SINCE_LAST_SYNC", self.operations_after_prepare()["canonical:TC-002"]["reason"])
        self.azure.items[self.work_item["canonical:TC-002"]]["rev"] -= 1
        self.azure.items[self.work_item["canonical:TC-002"]]["tags"] = "someone-retagged-it"
        self.assertEqual("FTD_KEY_OWNERSHIP_MISMATCH", self.operations_after_prepare()["canonical:TC-002"]["reason"])
        self.assertEqual("CONFLICTS", pub.apply(self.plan_path(), self.azure, approved=True)["status"])

    def operations_after_prepare(self) -> dict:
        self.prepare()
        return self.operations()

    def test_an_executed_case_with_a_semantic_change_needs_a_human_decision(self) -> None:
        self.run.round()
        executed = HistoryAzure(executed={self.work_item["canonical:TC-002"]})
        executed.items, executed.members, executed.next_id, executed.suites = (
            self.azure.items, self.azure.members, self.azure.next_id, self.azure.suites)
        summary = self.prepare(remote=executed)["summary"]
        operation = self.operations()["canonical:TC-002"]
        self.assertEqual(("REVIEW_REQUIRED", "REVIEW_REQUIRED_EXECUTED_TC"), (operation["action"], operation["reason"]))
        self.assertEqual((1, 0), (summary["review_required"], summary["update_test_cases"]))
        self.assertEqual((0, 0), (summary["execution_evidence_writes"], summary["execution_evidence_deletes"]))
        pub.apply(self.plan_path(), executed, approved=True)
        self.assertTrue(executed.items[self.work_item["canonical:TC-002"]]["title"].startswith("TC-002 — Invitation expires after seven"))
        self.prepare(remote=executed, review={"TC-002": adr_azure.REVIEW_UPDATE_SAME})
        self.assertEqual("UPDATE", self.operations()["canonical:TC-002"]["action"])

    def test_unknown_execution_history_is_never_assumed_empty(self) -> None:
        self.run.round()
        blind = HistoryAzure(unreadable=True)
        blind.items, blind.members, blind.next_id, blind.suites = (
            self.azure.items, self.azure.members, self.azure.next_id, self.azure.suites)
        self.prepare(remote=blind)
        self.assertEqual("EXECUTION_HISTORY_UNKNOWN", self.operations()["canonical:TC-002"]["reason"])
        plain = TaggedAzure()
        plain.items, plain.members, plain.next_id, plain.suites = (
            self.azure.items, self.azure.members, self.azure.next_id, self.azure.suites)
        self.prepare(remote=plain)  # a remote without the history read at all
        self.assertEqual("REVIEW_REQUIRED", self.operations()["canonical:TC-002"]["action"])

    def test_supersession_is_only_a_proposal(self) -> None:
        self.run.round()
        (self.run.corpus / fx.ROUND2_FILE).write_text(fx.ROUND2_TEXT, encoding="utf-8")
        self.run.round(fx.round2_analysis(), fx.round2_procedures())
        (self.run.corpus / fx.ROUND3_FILE).write_text(fx.ROUND3_TEXT, encoding="utf-8")
        self.run.round(fx.round3_analysis(), fx.round3_procedures())
        self.prepare("adr-003")
        plan = json.loads(self.plan_path("adr-003").read_text(encoding="utf-8"))
        self.assertEqual(["canonical:TC-005"], [p["export_key"] for p in plan["operations"]["supersede_proposals"]])
        self.assertNotIn("canonical:TC-005", {op["export_key"] for op in plan["operations"]["test_cases"]})
        self.assertIn("SUPERSEDE_PROPOSAL        1", self.prepare("adr-003")["preview"])

    def test_the_normal_publisher_never_reverts_an_adr_update(self) -> None:
        self.run.round()
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        az.convert_run(self.run_dir)
        pub.prepare(self.run_dir, TARGET, self.azure)
        plan = json.loads((self.run.artifacts / "output" / "azure" / "publication-plan.json").read_text(encoding="utf-8"))
        operation = next(op for op in plan["operations"]["test_cases"] if op["export_key"] == "canonical:TC-002")
        self.assertEqual(("CONFLICT", "MANAGED_BY_ADR_LINEAGE"), (operation["action"], operation["reason"]))

    def test_a_changed_package_or_state_stops_apply(self) -> None:
        self.run.round()
        self.prepare()
        package = self.run.artifacts / "output" / "adr" / "adr-001" / "azure" / "azure-adr-export-package.json"
        package.write_text(package.read_text(encoding="utf-8") + " ", encoding="utf-8")
        writes = len(self.azure.writes())
        with self.assertRaises(ado.PublicationError):
            pub.apply(self.plan_path(), self.azure, approved=True)
        self.assertEqual(writes, len(self.azure.writes()))


class WriteSurfaceTests(unittest.TestCase):
    """Execution evidence (runs, results, attachments, screenshots, logs) is outside ADR ownership."""

    EVIDENCE = re.compile(r"run|result|attachment|evidence|screenshot|log", re.IGNORECASE)

    def test_the_remote_write_allowlist_is_frozen(self) -> None:
        self.assertEqual(("create_test_case", "update_test_case", "create_suite", "add_test_cases_to_suite"),
                         ado.WRITE_METHODS)
        public = {n for n, v in vars(ado.RestAzureRemote).items() if callable(v) and not n.startswith("_")}
        self.assertEqual(set(), public - set(ado.READ_METHODS) - set(ado.WRITE_METHODS),
                         "a new remote method needs an explicit allowlist decision")
        for name in ado.WRITE_METHODS:
            self.assertIsNone(self.EVIDENCE.search(name.replace("test_case", "")), name)

    def test_execution_history_is_read_only_and_writes_never_target_execution_data(self) -> None:
        source = inspect.getsource(ado.RestAzureRemote)
        for call in re.findall(r'self\._call\("(POST|PATCH)", f?"([^"]*)"', source):
            self.assertNotRegex(call[1], r"(?i)/runs|/results|attachments|TestPoint|/test/")
        history = inspect.getsource(ado.RestAzureRemote.test_case_history)
        self.assertNotRegex(history, r'"(POST|PATCH|DELETE|PUT)"')
        with self.assertRaises(ado.PublicationError):
            ado.RestAzureRemote("https://dev.azure.example/org", ado.EnvironmentCredential("X"))._call("DELETE", "x")

    def test_adr_code_has_no_direct_remote_write(self) -> None:
        for module in (adr_azure, adr):
            source = inspect.getsource(module)
            with self.subTest(module=module.__name__):
                for name in (*ado.WRITE_METHODS, "delete", "_call("):
                    self.assertNotIn(f".{name}(", source)


if __name__ == "__main__":
    unittest.main()
