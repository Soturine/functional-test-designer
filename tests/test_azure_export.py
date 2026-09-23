"""ftd-azure: canonical + Challenge projection into a normalized Azure export package."""

from __future__ import annotations

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
        package = az.build_export_package(run.run_dir, challenge_ids=[])
        self.assertEqual(12, package["diagnostics"]["canonical_test_cases"])
        self.assertEqual(0, package["diagnostics"]["challenge_test_cases"])
        self.assertTrue(all(c["export_key"].startswith("canonical:") for c in package["test_cases"]))

    def test_no_external_requirement_id_is_invented_without_a_mapping(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
        self.assertTrue(all(r["external_id"] is None for r in package["requirements"]))

    def test_supplied_requirement_mapping_is_used(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        identifier = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")["index"]["requirements"][0]["source_identifier"]
        package = az.build_export_package(run.run_dir, challenge_ids=[], requirement_mapping={identifier: {"external_id": "1234"}})
        mapped = next(r for r in package["requirements"] if r["identifier"] == identifier)
        self.assertEqual("1234", mapped["external_id"])


class ChallengeIncludedExportTests(unittest.TestCase):
    def test_canonical_plus_one_finalized_challenge_run_works(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        self.assertEqual(1, package["diagnostics"]["challenge_test_cases"])
        self.assertEqual(1, len(package["challenge_runs"]))

    def test_canonical_plus_multiple_finalized_challenge_runs_works(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        _finalized_challenge(run, "night-shift")
        package = az.build_export_package(run.run_dir)
        self.assertEqual(2, package["diagnostics"]["challenge_test_cases"])
        self.assertEqual({"field-pass", "night-shift"}, {c["challenge_run_id"] for c in package["challenge_runs"]}.union())

    def test_unfinished_challenge_run_is_excluded_by_default(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "in-progress", seeds=[])  # never submitted/finalized
        package = az.build_export_package(run.run_dir)
        self.assertEqual(0, package["diagnostics"]["challenge_test_cases"])

    def test_explicitly_requesting_an_unfinished_challenge_run_is_rejected(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        ch.start_challenge(run.run_dir, "in-progress", seeds=[])
        with self.assertRaises(ValueError):
            az.build_export_package(run.run_dir, challenge_ids=["in-progress"])


class StableExportKeyTests(unittest.TestCase):
    def test_ch_stays_ch_locally_but_gets_a_scoped_azure_export_key(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        challenge_case = next(c for c in package["test_cases"] if c["source_kind"] == "CHALLENGE")
        self.assertEqual("CH-001", challenge_case["local_id"])  # local identity, unchanged
        self.assertEqual("challenge:field-pass:CH-001", challenge_case["export_key"])  # scoped Azure key

    def test_two_challenge_runs_each_minting_ch_001_do_not_collide(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        _finalized_challenge(run, "night-shift")
        package = az.build_export_package(run.run_dir)
        keys = [c["export_key"] for c in package["test_cases"] if c["source_kind"] == "CHALLENGE"]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("challenge:field-pass:CH-001", keys)
        self.assertIn("challenge:night-shift:CH-001", keys)


class RequirementGroupingTests(unittest.TestCase):
    def test_requirement_to_test_case_grouping_places_canonical_tcs_under_their_requirement(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
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
        self.assertIn("challenge:field-pass:CH-001", fr01["test_case_refs"])
        entry = next(c for c in package["test_cases"] if c["export_key"] == "challenge:field-pass:CH-001")
        self.assertEqual("DIRECT", entry["trace_origin"])

    def test_ch_with_only_related_tc_inherits_placement_without_normative_authority(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        canonical = ch.pipeline.read_canonical(run.run_dir / "canonical-suite.json")
        related_tc = canonical["cases"][0]["id"]
        _finalized_challenge(run, "field-pass", related_test_cases=[related_tc])
        package = az.build_export_package(run.run_dir)
        entry = next(c for c in package["test_cases"] if c["export_key"] == "challenge:field-pass:CH-001")
        self.assertEqual("INHERITED_FROM_RELATED_TC", entry["trace_origin"])
        placed = [r["identifier"] for r in package["requirements"] if "challenge:field-pass:CH-001" in r["test_case_refs"]]
        self.assertTrue(placed)

    def test_unassociated_ch_goes_to_the_unassigned_group(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        _finalized_challenge(run, "field-pass")
        package = az.build_export_package(run.run_dir)
        unassigned = next(r for r in package["requirements"] if r["identifier"] is None)
        self.assertEqual(az.UNASSIGNED, unassigned["title"])
        self.assertIn("challenge:field-pass:CH-001", unassigned["test_case_refs"])

    def test_a_tc_relevant_to_several_requirements_is_one_work_item_with_several_placements(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
        multi = [c for c in package["test_cases"] if len(c["requirement_refs"]) > 1]
        self.assertTrue(multi, "fixture should contain at least one multi-requirement Test Case")
        key = multi[0]["export_key"]
        placements = [r["identifier"] for r in package["requirements"] if key in r["test_case_refs"]]
        self.assertGreater(len(placements), 1)
        self.assertEqual(1, sum(c["export_key"] == key for c in package["test_cases"]))  # never cloned


class PreviewAndPublishTests(unittest.TestCase):
    def test_preview_is_local_and_read_only(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        self.assertEqual({"target", "create", "update", "unchanged", "skipped", "conflicts", "suite_mapping"}, set(preview))
        self.assertGreater(len(preview["create"]), 0)

    def test_existing_mapping_yields_update_or_unchanged_instead_of_duplicate_create(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
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
        package = az.build_export_package(run.run_dir, challenge_ids=[])
        preview = az.preview_export(package, project="P", plan="L", suite="S")
        results = apply_preview(preview, transport=None, approved=False)
        self.assertEqual([], results)

    def test_no_secrets_appear_in_package_or_preview(self) -> None:
        run = PackRun("saas-accounts")
        self.addCleanup(run.close)
        run.finalize()
        package = az.build_export_package(run.run_dir, challenge_ids=[])
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


class McpCompatibilityTests(unittest.TestCase):
    def test_ftd_mcp_natural_phrase_still_routes_to_ftd_mcp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import workflow
        self.assertEqual("ftd-mcp", workflow.normalize_intent("Prepare the last suite for Azure DevOps Test Plans"))

    def test_ftd_azure_natural_phrase_routes_to_ftd_azure(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import workflow
        self.assertEqual("ftd-azure", workflow.normalize_intent("Prepare this finalized FTD run for Azure DevOps."))


if __name__ == "__main__":
    unittest.main()
