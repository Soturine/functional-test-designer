"""/ftd-azure-publish: explicit, target-locked, non-destructive publication — with a fake
Azure DevOps only. Nothing here connects to a real organization."""

from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export as az  # noqa: E402
import azure_publish as pub  # noqa: E402
import challenge as ch  # noqa: E402
from integrations import azure_devops as ado  # noqa: E402
from support import PackRun  # noqa: E402

ORG = "https://dev.azure.example/org-a"
SECRET = "fake-secret-value-0123456789"


class FakeAzure:
    """An in-memory organization. Records every call; exposes no delete of any kind."""

    def __init__(self, url: str = ORG, projects=None, plans=None, suites=None):
        self.url = url
        self.projects = projects or [{"id": "p-1", "name": "Shop"}, {"id": "p-2", "name": "Billing"}]
        self.plans = plans or {"p-1": [{"id": 10, "name": "Release", "root_suite_id": 100},
                                       {"id": 11, "name": "Hotfix", "root_suite_id": 110}],
                               "p-2": [{"id": 20, "name": "Release", "root_suite_id": 200}]}
        self.suites = suites or {10: [{"id": 100, "name": "Release", "parent_id": None}],
                                 11: [{"id": 110, "name": "Hotfix", "parent_id": None}],
                                 20: [{"id": 200, "name": "Release", "parent_id": None}]}
        self.items: dict[int, dict] = {}
        self.members: dict[int, list[int]] = {}
        self.calls: list[str] = []
        self.next_id = 5000

    def _log(self, name):
        self.calls.append(name)

    def organization(self):
        self._log("organization")
        return {"url": self.url, "name": self.url.rsplit("/", 1)[-1]}

    def list_projects(self):
        self._log("list_projects")
        return [dict(p) for p in self.projects]

    def list_test_plans(self, project_id):
        self._log("list_test_plans")
        return [dict(p) for p in self.plans.get(project_id, [])]

    def list_suites(self, project_id, plan_id):
        self._log("list_suites")
        return [dict(s) for s in self.suites.get(plan_id, [])]

    def list_suite_test_cases(self, project_id, plan_id, suite_id):
        self._log("list_suite_test_cases")
        return list(self.members.get(suite_id, []))

    def get_work_items(self, project_id, ids):
        self._log("get_work_items")
        return {i: dict(self.items[i]) for i in ids if i in self.items}

    def list_plan_test_cases(self, project_id, plan_id):
        self._log("list_plan_test_cases")
        suite_ids = {s["id"] for s in self.suites.get(plan_id, [])}
        return [{"id": i, "title": self.items[i]["title"]} for sid in suite_ids for i in self.members.get(sid, [])]

    # --- writes ---
    def create_test_case(self, project_id, fields):
        self._log("create_test_case")
        self.next_id += 1
        self.items[self.next_id] = {"id": self.next_id, "rev": 1, "title": fields["System.Title"], "fields": fields}
        return {"id": self.next_id, "rev": 1}

    def update_test_case(self, project_id, work_item_id, fields, expected_rev):
        self._log("update_test_case")
        item = self.items[work_item_id]
        assert item["rev"] == expected_rev
        item.update(rev=item["rev"] + 1, title=fields["System.Title"], fields=fields)
        return {"id": work_item_id, "rev": item["rev"]}

    def create_suite(self, project_id, plan_id, parent_suite_id, name):
        self._log("create_suite")
        self.next_id += 1
        self.suites.setdefault(plan_id, []).append({"id": self.next_id, "name": name, "parent_id": parent_suite_id})
        return {"id": self.next_id}

    def add_test_cases_to_suite(self, project_id, plan_id, suite_id, work_item_ids):
        self._log("add_test_cases_to_suite")
        self.members.setdefault(suite_id, []).extend(work_item_ids)

    def writes(self):
        return [c for c in self.calls if c in ado.WRITE_METHODS]


TARGET = {"organization": ORG, "project": "Shop", "plan": "Release"}


class PublisherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.run.finalize(("JSON",))
        az.convert_run(self.run.run_dir)
        self.azure = FakeAzure()

    def prepare(self, target=None, remote=None):
        return pub.prepare(self.run.run_dir, target or TARGET, remote or self.azure)

    def plan_path(self) -> Path:
        return self.run.artifacts / "output" / "azure" / "publication-plan.json"


class PrepareTests(PublisherTestCase):
    def test_prepare_reads_only_and_writes_a_local_target_locked_plan(self) -> None:
        result = self.prepare()
        self.assertEqual([], self.azure.writes())
        self.assertEqual(0, result["remote_writes"])
        plan = json.loads(self.plan_path().read_text(encoding="utf-8"))
        self.assertEqual(("p-1", "Shop", 10, "Release"), (plan["target"]["project"]["id"], plan["target"]["project"]["name"],
                                                          plan["target"]["plan"]["id"], plan["target"]["plan"]["name"]))
        for field in ("run_id", "package_digest", "canonical_digest"):
            self.assertTrue(plan["source"][field])
        self.assertIn("generated_at", plan)
        self.assertEqual(0, plan["summary"]["delete_operations"])
        self.assertEqual(12, plan["summary"]["create_test_cases"])

    def test_a_readonly_view_cannot_write(self) -> None:
        with self.assertRaises(PermissionError):
            ado.ReadOnlyRemote(self.azure).create_test_case("p-1", {})

    def test_the_destination_is_never_guessed(self) -> None:
        for target, code in (({"organization": ORG, "plan": "Release"}, "TARGET_REQUIRED"),
                             ({"organization": ORG, "project": "Shop"}, "TARGET_REQUIRED"),
                             ({"organization": ORG, "project": "shop", "plan": "Release"}, "TARGET_NOT_FOUND"),
                             ({"organization": ORG, "project": "Sho", "plan": "Release"}, "TARGET_NOT_FOUND"),
                             ({"organization": "https://dev.azure.example/org-b", "project": "Shop", "plan": "Release"},
                              "TARGET_MISMATCH")):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ado.PublicationError, code):
                    self.prepare(target)
        self.assertEqual([], self.azure.writes())

    def test_ambiguous_names_stop_and_ids_resolve_them(self) -> None:
        twins = FakeAzure(plans={"p-1": [{"id": 10, "name": "Release", "root_suite_id": 100},
                                         {"id": 12, "name": "Release", "root_suite_id": 120}], "p-2": []},
                          suites={10: [{"id": 100, "name": "Release", "parent_id": None}],
                                  12: [{"id": 120, "name": "Release", "parent_id": None}]})
        with self.assertRaisesRegex(ado.PublicationError, "AMBIGUOUS_TARGET"):
            self.prepare(remote=twins)
        plan = self.prepare({"organization": ORG, "project": "p-1", "plan": 12}, twins)
        self.assertEqual(12, json.loads(self.plan_path().read_text(encoding="utf-8"))["target"]["plan"]["id"])
        self.assertEqual([], twins.writes())
        self.assertIn("Test Plan: Release (12)", plan["preview"])

    def test_the_preview_names_the_destination_and_counts_every_operation(self) -> None:
        preview = self.prepare()["preview"]
        for line in ("Organization: org-a (https://dev.azure.example/org-a)", "Project: Shop (p-1)",
                     "Test Plan: Release (10)", "Root Suite: none (plan root)", "CREATE test cases       12",
                     "DELETE operations       0"):
            self.assertIn(line, preview)


class ApplyTests(PublisherTestCase):
    def test_apply_without_approval_writes_nothing(self) -> None:
        self.prepare()
        result = pub.apply(self.plan_path(), self.azure)
        self.assertEqual(("APPROVAL_REQUIRED", 0), (result["status"], result["writes"]))
        wrong = pub.apply(self.plan_path(), self.azure, confirmation="PUBLISH Billing / Release")
        self.assertEqual("APPROVAL_REQUIRED", wrong["status"])
        self.assertEqual([], self.azure.writes())

    def test_the_typed_target_phrase_approves_and_multi_suite_cases_reuse_one_work_item(self) -> None:
        self.prepare()
        result = pub.apply(self.plan_path(), self.azure, confirmation="PUBLISH Shop / Release")
        self.assertEqual("APPLIED", result["status"])
        package = json.loads((self.run.artifacts / "output" / "azure" / "azure-export-package.json").read_text(encoding="utf-8"))
        self.assertEqual(len(package["test_cases"]), self.azure.calls.count("create_test_case"))
        placed: dict[int, int] = {}
        for ids in self.azure.members.values():
            for work_item in ids:
                placed[work_item] = placed.get(work_item, 0) + 1
        self.assertTrue(any(count > 1 for count in placed.values()))  # several suites, one work item
        self.assertEqual(len(self.azure.items), len(placed))

    def test_a_second_prepare_after_apply_is_unchanged(self) -> None:
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        before = len(self.azure.writes())
        summary = self.prepare()["summary"]
        self.assertEqual((0, 0, 12, 0, 0), (summary["create_test_cases"], summary["update_test_cases"], summary["unchanged"],
                                           summary["create_suites"], summary["add_suite_placements"]))
        self.assertEqual(before, len(self.azure.writes()))

    def test_a_plan_cannot_run_against_another_project_or_plan(self) -> None:
        self.prepare()
        plan = json.loads(self.plan_path().read_text(encoding="utf-8"))
        elsewhere = FakeAzure(projects=[{"id": "p-9", "name": "Shop"}], plans={"p-9": [{"id": 10, "name": "Release", "root_suite_id": 100}]})
        with self.assertRaisesRegex(ado.PublicationError, "TARGET_NOT_FOUND"):
            pub.apply(self.plan_path(), elsewhere, approved=True)
        other_org = FakeAzure(url="https://dev.azure.example/org-b")
        with self.assertRaisesRegex(ado.PublicationError, "TARGET_MISMATCH"):
            pub.apply(self.plan_path(), other_org, approved=True)
        self.assertEqual(([], []), (elsewhere.writes(), other_org.writes()))
        self.assertEqual("p-1", plan["target"]["project"]["id"])

    def test_a_remote_change_since_the_last_sync_is_a_conflict_never_an_overwrite(self) -> None:
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        first = next(iter(self.azure.items.values()))
        first["rev"] += 1  # someone edited it in Azure
        state = json.loads((self.run.run_dir / "integration-state" / "azure-devops.json").read_text(encoding="utf-8"))
        for entry in state["test_cases"].values():
            entry["content_hash"] = "changed-locally"
        (self.run.run_dir / "integration-state" / "azure-devops.json").write_text(json.dumps(state), encoding="utf-8")
        writes = len(self.azure.writes())
        summary = self.prepare()["summary"]
        self.assertEqual(1, summary["conflicts"])
        result = pub.apply(self.plan_path(), self.azure, approved=True)
        self.assertEqual("CONFLICTS", result["status"])
        self.assertEqual(writes, len(self.azure.writes()))

    def test_a_change_between_prepare_and_apply_stops_before_any_write(self) -> None:
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        state_path = self.run.run_dir / "integration-state" / "azure-devops.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for entry in state["test_cases"].values():
            entry["content_hash"] = "changed-locally"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.prepare()
        next(iter(self.azure.items.values()))["rev"] += 1
        writes = len(self.azure.writes())
        self.assertEqual("CONFLICTS", pub.apply(self.plan_path(), self.azure, approved=True)["status"])
        self.assertEqual(writes, len(self.azure.writes()))

    def test_an_unmanaged_look_alike_is_never_overwritten(self) -> None:
        package = json.loads((self.run.artifacts / "output" / "azure" / "azure-export-package.json").read_text(encoding="utf-8"))
        title = package["test_cases"][0]["title"]
        self.azure.items[42] = {"id": 42, "rev": 3, "title": title}
        self.azure.members[100] = [42]
        plan = self.prepare()
        self.assertEqual(1, plan["summary"]["conflicts"])
        operations = json.loads(self.plan_path().read_text(encoding="utf-8"))["operations"]["test_cases"]
        self.assertEqual("POSSIBLE_UNMANAGED_MATCH", next(o for o in operations if o["action"] == "CONFLICT")["reason"])
        self.assertEqual("CONFLICTS", pub.apply(self.plan_path(), self.azure, approved=True)["status"])
        self.assertEqual({"id": 42, "rev": 3, "title": title}, self.azure.items[42])

    def test_a_changed_package_invalidates_the_plan(self) -> None:
        self.prepare()
        package = self.run.artifacts / "output" / "azure" / "azure-export-package.json"
        package.write_text(package.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ado.PublicationError, "PACKAGE_CHANGED"):
            pub.apply(self.plan_path(), self.azure, approved=True)
        self.assertEqual([], self.azure.writes())

    def test_post_suite_cases_publish_with_their_scoped_keys(self) -> None:
        ch.start_challenge(self.run.run_dir, "field", seeds=[])
        ch.submit_challenge(self.run.run_dir, "field", {"cases": [{
            "key": "H1", "title": "Two owners invite the last seat at once", "discovery": "MODEL_DERIVED",
            "rationale": "Racing invitations could exceed the seat limit.", "execution_tags": ["MANUAL"]}],
            "seed_dispositions": []})
        ch.finalize_challenge(self.run.run_dir, "field")
        az.convert_run(self.run.run_dir)
        self.prepare()
        pub.apply(self.plan_path(), self.azure, approved=True)
        state = json.loads((self.run.run_dir / "integration-state" / "azure-devops.json").read_text(encoding="utf-8"))
        self.assertIn("chaos:field:CH-001", state["test_cases"])
        self.assertEqual("p-1", state["test_cases"]["chaos:field:CH-001"]["project_id"])


class SafetyContractTests(PublisherTestCase):
    def test_no_delete_or_removal_operation_exists(self) -> None:
        for owner in (ado.AzureRemoteWriter, ado.RestAzureRemote, FakeAzure):
            names = [n for n in dir(owner) if not n.startswith("__")]
            self.assertFalse([n for n in names if "delete" in n.lower() or "remove" in n.lower()], owner)
        source = inspect.getsource(ado.RestAzureRemote)
        self.assertNotIn('"DELETE"', source.replace('{"GET", "POST", "PATCH"}', ""))
        with self.assertRaisesRegex(ado.PublicationError, "FORBIDDEN_OPERATION"):
            ado.RestAzureRemote(ORG, ado.EnvironmentCredential("X"))._call("DELETE", "_apis/wit/workitems/1")

    def test_credentials_are_never_persisted(self) -> None:
        requests = []

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(self.body).encode()

        def opener(request):
            requests.append(request)
            return Response({"value": [{"id": "p-1", "name": "Shop"}]})

        with mock.patch.dict("os.environ", {"FTD_TEST_PAT": SECRET}):
            remote = ado.RestAzureRemote(ORG, ado.EnvironmentCredential("FTD_TEST_PAT"), opener=opener)
            self.assertEqual([{"id": "p-1", "name": "Shop"}], remote.list_projects())
            self.assertTrue(requests[0].get_header("Authorization").startswith("Basic "))
            self.prepare()
            pub.apply(self.plan_path(), self.azure, approved=True)
        self.assertNotIn(SECRET, repr(remote))
        encoded = __import__("base64").b64encode(f":{SECRET}".encode()).decode()
        for path in self.run.root.rglob("*"):
            if path.is_file():
                text = path.read_bytes()
                self.assertNotIn(SECRET.encode(), text, path)
                self.assertNotIn(encoded.encode(), text, path)

    def test_ftd_azure_itself_never_opens_a_connection(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                mock.patch("socket.socket", side_effect=AssertionError("network")):
            result = az.convert_run(self.run.run_dir)
        self.assertEqual(0, result["live_azure_calls"])

    def test_the_dispatcher_never_publishes_without_an_explicit_phase(self) -> None:
        import workflow
        with self.assertRaisesRegex(ValueError, "phase 'prepare' or 'apply'"):
            workflow.dispatch("ftd-azure-publish", run_dir=str(self.run.run_dir), remote=self.azure)
        result = workflow.dispatch("ftd-azure", run_dir=str(self.run.run_dir))
        self.assertEqual(0, result["live_azure_calls"])
        self.assertEqual([], self.azure.calls)
        prepared = workflow.dispatch("ftd-azure-publish", phase="prepare", run_dir=str(self.run.run_dir), remote=self.azure,
                                     organization=ORG, project="Shop", plan="Release")
        self.assertEqual(0, prepared["remote_writes"])
        self.assertEqual([], self.azure.writes())



class PrepareCommandLineTests(unittest.TestCase):
    """Missing target values are reported at once, before any credential or connection."""

    def prepare(self, *args: str) -> str:
        import contextlib
        import io
        out = io.StringIO()
        with mock.patch.object(pub, "remote_for", side_effect=AssertionError("no remote before validation")), \
                contextlib.redirect_stdout(out):
            code = pub.main(["--prepare", *args])
        self.assertEqual(1, code)
        return out.getvalue()

    def test_a_missing_project_is_rejected_immediately(self) -> None:
        text = self.prepare("--run", "runs/r", "--organization", ORG, "--plan", "Release")
        self.assertIn("TARGET_REQUIRED", text)
        self.assertIn("--project", text)
        self.assertNotIn("--plan,", text)

    def test_a_missing_plan_is_rejected_immediately(self) -> None:
        text = self.prepare("--run", "runs/r", "--organization", ORG, "--project", "Shop")
        self.assertIn("TARGET_REQUIRED", text)
        self.assertIn("--plan", text)

    def test_every_missing_value_is_named(self) -> None:
        text = self.prepare()
        for flag in ("--run", "--organization", "--project", "--plan"):
            self.assertIn(flag, text)


if __name__ == "__main__":
    unittest.main()
