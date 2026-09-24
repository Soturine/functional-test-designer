"""ftd-azure: canonical + chaos projection into local, requirement-grouped Azure input JSON."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export as az  # noqa: E402
import challenge as ch  # noqa: E402
from support import PackRun  # noqa: E402


def _case(**over):
    base = {
        "key": "H1", "title": "A concurrent action on the same record", "discovery": "MODEL_DERIVED",
        "rationale": "Two actors racing on the same record could corrupt or duplicate its state.",
        "execution_tags": ["MANUAL"],
    }
    base.update(over)
    return base


def _finalized_challenge(run, challenge_id: str, **case_overrides) -> None:
    ch.start_challenge(run.run_dir, challenge_id, seeds=[])
    ch.submit_challenge(run.run_dir, challenge_id, {"cases": [_case(**case_overrides)], "seed_dispositions": []})
    ch.finalize_challenge(run.run_dir, challenge_id)


class CanonicalOnlyExportTests(unittest.TestCase):
    def test_canonical_only_export_works_without_any_challenge_run(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        self.assertEqual(12, package["diagnostics"]["canonical_test_cases"])
        self.assertEqual(0, package["diagnostics"]["chaos_test_cases"])
        self.assertTrue(all(c["export_key"].startswith("canonical:") for c in package["test_cases"]))

    def test_no_external_requirement_id_is_invented_without_a_mapping(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        self.assertTrue(all(r["external_id"] is None for r in package["requirements"]))

    def test_supplied_requirement_mapping_is_used(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        identifier = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")["index"]["requirements"][0]["source_identifier"]
        package = az.build_export_package(run.run_dir, chaos_ids=[], requirement_mapping={identifier: {"external_id": "1234"}})
        mapped = next(r for r in package["requirements"] if r["identifier"] == identifier)
        self.assertEqual("1234", mapped["external_id"])


class ChaosIncludedExportTests(unittest.TestCase):
    def test_canonical_plus_one_finalized_challenge_run_works(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        self.assertEqual(1, package["diagnostics"]["chaos_test_cases"])
        self.assertEqual(1, len(package["chaos_runs"]))

    def test_canonical_plus_multiple_finalized_challenge_runs_works(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        _finalized_challenge(run, "night-shift")
        package = az.build_export_package(run.run_dir)
        self.assertEqual(2, package["diagnostics"]["chaos_test_cases"])
        self.assertEqual({"field-pass", "night-shift"}, {c["chaos_run_id"] for c in package["chaos_runs"]})

    def test_unfinished_challenge_run_is_excluded_by_default(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "in-progress", seeds=[])  # never submitted/finalized
        package = az.build_export_package(run.run_dir)
        self.assertEqual(0, package["diagnostics"]["chaos_test_cases"])

    def test_explicitly_requesting_an_unfinished_challenge_run_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "in-progress", seeds=[])
        with self.assertRaises(ValueError):
            az.build_export_package(run.run_dir, chaos_ids=["in-progress"])


class StableExportKeyTests(unittest.TestCase):
    def test_ch_stays_ch_locally_but_gets_a_scoped_azure_export_key(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        challenge_case = next(c for c in package["test_cases"] if c["source_kind"] == "CHAOS")
        self.assertEqual("CH-001", challenge_case["local_id"])  # local identity, unchanged
        self.assertEqual("chaos:field-pass:CH-001", challenge_case["export_key"])  # scoped Azure key

    def test_two_challenge_runs_each_minting_ch_001_do_not_collide(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        _finalized_challenge(run, "night-shift")
        package = az.build_export_package(run.run_dir)
        keys = [c["export_key"] for c in package["test_cases"] if c["source_kind"] == "CHAOS"]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("chaos:field-pass:CH-001", keys)
        self.assertIn("chaos:night-shift:CH-001", keys)


class RequirementGroupingTests(unittest.TestCase):
    def test_requirement_to_test_case_grouping_places_canonical_tcs_under_their_requirement(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        fr01 = next(r for r in package["requirements"] if r["identifier"] == "FR-01")
        self.assertTrue(all(ref.startswith("canonical:") for ref in fr01["test_case_refs"]))
        self.assertTrue(fr01["test_case_refs"])

    def test_ch_with_direct_requirement_refs_is_grouped_under_that_requirement(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass", related_source_identifiers=["FR-01"])
        package = az.build_export_package(run.run_dir)
        fr01 = next(r for r in package["requirements"] if r["identifier"] == "FR-01")
        self.assertIn("chaos:field-pass:CH-001", fr01["test_case_refs"])
        entry = next(c for c in package["test_cases"] if c["export_key"] == "chaos:field-pass:CH-001")
        self.assertEqual("DIRECT", entry["trace_origin"])

    def test_ch_with_only_related_tc_inherits_placement_without_normative_authority(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        canonical = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")
        related_tc = canonical["cases"][0]["id"]
        _finalized_challenge(run, "field-pass", related_test_cases=[related_tc])
        package = az.build_export_package(run.run_dir)
        entry = next(c for c in package["test_cases"] if c["export_key"] == "chaos:field-pass:CH-001")
        self.assertEqual("INHERITED_FROM_RELATED_TC", entry["trace_origin"])
        placed = [r["identifier"] for r in package["requirements"] if "chaos:field-pass:CH-001" in r["test_case_refs"]]
        self.assertTrue(placed)

    def test_unassociated_ch_goes_to_the_unassigned_group(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        unassigned = next(r for r in package["requirements"] if r["identifier"] is None)
        self.assertEqual(az.UNASSIGNED, unassigned["suite_name"])
        self.assertIn("chaos:field-pass:CH-001", unassigned["test_case_refs"])

    def test_a_tc_relevant_to_several_requirements_is_one_work_item_with_several_placements(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        multi = [c for c in package["test_cases"] if len(c["requirement_refs"]) > 1]
        self.assertTrue(multi, "fixture should contain at least one multi-requirement Test Case")
        key = multi[0]["export_key"]
        placements = [r["identifier"] for r in package["requirements"] if key in r["test_case_refs"]]
        self.assertGreater(len(placements), 1)
        self.assertEqual(1, sum(c["export_key"] == key for c in package["test_cases"]))  # never cloned



class OrganizationSuiteTests(unittest.TestCase):
    """Azure suites mirror the publication organization; each case stays one work item."""

    def package(self, **challenge):
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        if challenge:
            _finalized_challenge(run, "field-pass", **challenge)
        return run, az.build_export_package(run.run_dir)

    def test_suites_follow_the_organization_in_its_order(self) -> None:
        run, package = self.package()
        organization = ch.pipeline.organization_for_run(run.run_dir)
        self.assertEqual([g["label"] for g in organization["groups"]], [s["suite_name"] for s in package["suites"]])
        for group, suite in zip(organization["groups"], package["suites"]):
            self.assertEqual([az.canonical_export_key(m["case"]) for m in group["members"]], suite["test_case_refs"])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        first = package["suites"][0]
        self.assertEqual(first["test_case_refs"], preview["suite_mapping"]["suite_members"][first["suite_name"]])

    def test_a_case_in_a_functional_suite_and_an_execution_view_is_one_work_item(self) -> None:
        _, package = self.package()
        views = [s for s in package["suites"] if s["group"] == "LOAD_CONCURRENCY"]
        self.assertTrue(views, "fixture should place at least one case in the load view")
        key = views[0]["test_case_refs"][0]
        homes = [s["suite_name"] for s in package["suites"] if key in s["test_case_refs"]]
        self.assertGreater(len(homes), 1)
        self.assertEqual(1, sum(c["export_key"] == key for c in package["test_cases"]))
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        self.assertEqual(1, sum(item["local_id"] == key for item in preview["create"]))
        membership = next(m for m in preview["suite_mapping"]["memberships"] if m["local_id"] == key)
        self.assertEqual(sorted(homes), sorted(s["suite"] for s in membership["suites"]))

    def test_every_export_key_has_a_suite(self) -> None:
        _, package = self.package(execution_tags=["MANUAL"])
        placed = {key for suite in package["suites"] for key in suite["test_case_refs"]}
        self.assertEqual({c["export_key"] for c in package["test_cases"]}, placed)


    def test_a_revision_inherits_the_finalized_chaos_runs_of_the_run_it_supersedes(self) -> None:
        run, _ = self.package(execution_tags=["MANUAL"])
        result = ch.pipeline.start_run(
            workspace=run.workspace, artifact_root=run.artifacts, run_id="revision",
            sources_selected=[{"path": path, "role": item["role"]} for path, item in run.pack["sources"].items()],
            locale=run.pack.get("locale"), request_text=run.pack.get("request", ""),
            reading={"strategy": "SEQUENTIAL"}, supersedes=run.run_dir.name)
        revision = Path(result["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            ch.pipeline.submit_stage(revision, stage, run.pack["stages"][stage])
        ch.pipeline.finalize_run(revision, ["JSON"])
        package = az.build_export_package(revision)
        self.assertEqual([{"chaos_run_id": "field-pass", "parent_run_id": run.run_dir.name, "cases": 1}],
                         package["chaos_runs"])
        self.assertIn("chaos:field-pass:CH-001", {c["export_key"] for c in package["test_cases"]})
        self.assertFalse((revision / "challenges").exists())  # inherited by reference, never copied


class MappedPayloadContextTests(unittest.TestCase):
    """What a canonical case defines survives, unchanged, into the Azure payload."""

    def test_fixture_definitions_survive_from_canonical_to_package_to_payload(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        canonical = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        payloads = {item["local_id"]: item["payload"] for item in preview["create"]}
        with_data = [c for c in canonical["cases"] if c["test_data"]]
        self.assertTrue(with_data, "fixture should define test data")
        for case in canonical["cases"]:
            key = az.canonical_export_key(case["id"])
            exported = next(c for c in package["test_cases"] if c["export_key"] == key)
            self.assertEqual(case["test_data"], exported["test_data"])
            if key not in payloads:
                continue
            payload = payloads[key]
            self.assertEqual(case["test_data"], payload["test_data"])
            self.assertEqual(case["postconditions"], payload["postconditions"])
            self.assertEqual(case["cleanup"], payload["cleanup"])
            self.assertEqual(case["preconditions"], payload["preconditions"])
            self.assertEqual(case["readiness_blockers"], payload["automation"]["readiness_blockers"])
            self.assertEqual(case["automation_layer"], payload["automation"]["layer"])
            self.assertEqual(case["automation_tool_hint"], payload["automation"]["tool_hint"])
            self.assertEqual(case["automation_readiness"], payload["automation"]["readiness"])
            self.assertEqual("CANONICAL", payload["source_kind"])
            self.assertEqual("SELF_CLEANING" if case["cleanup"] else "REQUIRES_FIXTURE_RESET",
                             payload["execution"]["state_contract"])

    def test_a_chaos_payload_names_its_related_cases_resources_and_state_contract(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        related = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")["cases"][0]["id"]
        _finalized_challenge(run, "field-pass", related_test_cases=[related], required_resources=["Second client device"],
                             environment_requirements=["Isolated staging tenant"])
        package = az.build_export_package(run.run_dir)
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        payload = next(i["payload"] for i in preview["create"] if i["local_id"] == "chaos:field-pass:CH-001")
        self.assertEqual("CHAOS", payload["source_kind"])
        self.assertEqual([related], payload["trace_refs"]["related_test_cases"])
        self.assertEqual(["Second client device"], payload["execution"]["required_resources"])
        self.assertEqual(["Isolated staging tenant"], payload["execution"]["environment_requirements"])
        self.assertEqual("REQUIRES_FIXTURE_RESET", payload["execution"]["state_contract"])


class PreviewAndPublishTests(unittest.TestCase):
    def test_preview_is_local_and_read_only(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        self.assertEqual({"target", "create", "update", "unchanged", "skipped", "conflicts", "suite_mapping"}, set(preview))
        self.assertGreater(len(preview["create"]), 0)

    def test_existing_mapping_yields_update_or_unchanged_instead_of_duplicate_create(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        first = az.preview_export(package, project="P", plan="L", suite="S")
        key = first["create"][0]["local_id"]
        mapping = {"test_cases": {key: {"external_id": "999", "content_hash": first["create"][0]["content_hash"],
                                        "last_synchronized_version": "v1"}}}
        second = az.preview_export(package, project="P", plan="L", suite="S", mapping=mapping)
        self.assertIn(key, {item["local_id"] for item in second["unchanged"]})
        self.assertNotIn(key, {item["local_id"] for item in second["create"]})

    def test_publish_without_approval_writes_nothing_and_reports_it(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        from integrations.azure_devops import apply_preview
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        results = apply_preview(preview, transport=None, approved=False)
        self.assertEqual([], results)

    def test_no_secrets_appear_in_package_or_preview(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        import json
        blob = json.dumps(package) + json.dumps(preview)
        for token in ("password", "secret", "api_key", "token=", "authorization"):
            self.assertNotIn(token, blob.casefold())


class SingleOwnerBoundaryTests(unittest.TestCase):
    """azure_export.py aggregates FTD run/Challenge state; every Azure-specific
    concern (payload mapping, Suite placement, diffing, transport) stays owned by
    integrations/azure_devops.py. This guards against the boundary drifting back
    into a second, competing Azure implementation."""

    def test_azure_export_defines_no_competing_azure_mapping_or_diffing_functions(self) -> None:
        reserved = {"map_test_case", "build_preview", "build_suite_mapping", "build_group_suite_mapping",
                    "apply_preview", "_suite_mapping"}
        own_functions = {
            name for name, value in vars(az).items()
            if callable(value) and getattr(value, "__module__", None) == az.__name__
        }
        self.assertEqual(set(), own_functions & reserved)

    def test_suite_placement_is_delegated_to_the_azure_adapter(self) -> None:
        from integrations import azure_devops
        self.assertIs(az.build_group_suite_mapping, azure_devops.build_group_suite_mapping)
        self.assertIs(az.load_integration_state, azure_devops.load_integration_state)


class RequirementSuiteNameTests(unittest.TestCase):
    def test_groups_are_named_identifier_dash_official_title(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, chaos_ids=[])
        for group in package["requirements"]:
            if group["identifier"] and group["title"]:
                self.assertEqual(f"{group['identifier']} — {group['title']}", group["suite_name"])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        names = set(preview["suite_mapping"]["suite_members"])
        self.assertEqual({s["suite_name"] for s in package["suites"]}, names)  # suites follow the organization

    def test_any_identifier_scheme_is_accepted(self) -> None:
        self.assertEqual("REQ.7 — Export audit", az.suite_name("REQ.7", "Export audit"))
        self.assertEqual("X-1", az.suite_name("X-1", None))
        self.assertEqual(az.UNASSIGNED, az.suite_name(None, None))


class LegacyKeyMigrationTests(unittest.TestCase):
    def test_challenge_keys_migrate_to_chaos_keys_without_losing_external_ids(self) -> None:
        state = {"test_cases": {"challenge:field-pass:CH-001": {"external_id": "77"},
                                "canonical:TC-001": {"external_id": "12"}}}
        migrated = az.migrate_integration_state(state)
        self.assertEqual({"chaos:field-pass:CH-001", "canonical:TC-001"}, set(migrated["test_cases"]))
        self.assertEqual("77", migrated["test_cases"]["chaos:field-pass:CH-001"]["external_id"])
        self.assertEqual("chaos:a:CH-9", az.migrate_export_key("challenge:a:CH-9"))

    def test_migrated_state_yields_unchanged_instead_of_a_duplicate_create(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        first = az.convert_run(run.run_dir)
        preview = json.loads(Path(first["preview"]).read_text(encoding="utf-8"))
        created = next(c for c in preview["create"] if c["local_id"] == "chaos:field-pass:CH-001")
        from integrations.azure_devops import persist_integration_state
        persist_integration_state(run.run_dir, {"test_cases": {"challenge:field-pass:CH-001": {
            "external_id": "77", "content_hash": created["content_hash"], "last_synchronized_version": "1"}}})
        second = json.loads(Path(az.convert_run(run.run_dir)["preview"]).read_text(encoding="utf-8"))
        self.assertIn("chaos:field-pass:CH-001", {c["local_id"] for c in second["unchanged"]})


class LocalConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.run.finalize()

    def test_convert_writes_local_package_and_preview_under_output_azure(self) -> None:
        result = az.convert_run(self.run.run_dir, output="JSON")
        destination = self.run.artifacts / "output" / "azure"
        self.assertEqual((destination / "azure-export-package.json").resolve(), Path(result["package"]).resolve())
        self.assertTrue((destination / "azure-preview.json").is_file())
        self.assertEqual(0, result["live_azure_calls"])
        preview = json.loads((destination / "azure-preview.json").read_text(encoding="utf-8"))
        self.assertEqual("LOCAL_PREVIEW_ONLY", preview["operation"])

    def test_output_is_deterministic(self) -> None:
        _finalized_challenge(self.run, "field-pass")
        az.convert_run(self.run.run_dir)
        path = self.run.artifacts / "output" / "azure" / "azure-export-package.json"
        first = path.read_bytes()
        az.convert_run(self.run.run_dir)
        self.assertEqual(first, path.read_bytes())

    def test_only_json_output_is_accepted(self) -> None:
        with self.assertRaises(ValueError):
            az.convert_run(self.run.run_dir, output="json,html")

    def test_no_live_transport_is_invoked(self) -> None:
        from unittest import mock
        from integrations import azure_devops
        with mock.patch.object(azure_devops, "apply_preview", side_effect=AssertionError("live call")):
            az.convert_run(self.run.run_dir)

    def test_chaos_id_selection_and_canonical_only(self) -> None:
        _finalized_challenge(self.run, "field-pass")
        _finalized_challenge(self.run, "night-shift")
        self.assertEqual(["field-pass", "night-shift"], az.convert_run(self.run.run_dir)["chaos_runs"])
        self.assertEqual(["night-shift"], az.convert_run(self.run.run_dir, chaos_ids=["night-shift"])["chaos_runs"])
        self.assertEqual([], az.convert_run(self.run.run_dir, chaos_ids=[])["chaos_runs"])

    def test_workflow_alias_dispatches_the_same_conversion(self) -> None:
        import workflow
        result = workflow.dispatch_request("/ftd-azure --output json", run_dir=str(self.run.run_dir), output="json")
        self.assertEqual(12, result["canonical_test_cases"])


if __name__ == "__main__":
    unittest.main()
