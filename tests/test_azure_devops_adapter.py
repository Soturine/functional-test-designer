from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from integrations.azure_devops import (  # noqa: E402
    apply_preview, build_preview, map_test_case, persist_integration_state, work_item_fields,
)


def case(case_id: str = "TC-001", status: str = "READY") -> dict:
    return {
        "id": case_id, "title": "Confirm reservation", "priority": "HIGH", "status": status,
        "preconditions": ["Eligible reservation exists"],
        "steps": [{"action": "Confirm", "expected_result": "Status is CONFIRMED"}],
        "tags": ["state-transition"], "requirement_refs": ["REQ-001"],
        "coverage_point_refs": ["CP-001"],
    }


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []
    def create_test_case(self, payload):
        self.calls.append(("create", payload["local_id"])); return {"id": "100"}
    def update_test_case(self, external_id, payload):
        self.calls.append(("update", external_id)); return {"id": external_id}


class AzureDevOpsAdapterTests(unittest.TestCase):
    def test_preview_is_idempotent_and_never_writes_without_approval(self) -> None:
        payload = map_test_case(case())
        initial = build_preview([case()], {}, project="P", plan="Plan", suite="Suite")
        mapping = {"test_cases": {"TC-001": {
            "external_id": "100", "content_hash": initial["create"][0]["content_hash"],
            "last_synchronized_version": "7",
        }}}
        second = build_preview([case()], mapping, project="P", plan="Plan", suite="Suite")
        self.assertEqual([{"local_id": "TC-001", "external_id": "100"}], second["unchanged"])
        transport = FakeTransport()
        self.assertEqual([], apply_preview(initial, transport, approved=False))
        self.assertEqual([], transport.calls)

    def test_needs_review_is_skipped_by_default_and_delete_is_absent(self) -> None:
        preview = build_preview([case(status="NEEDS_REVIEW")], {}, project="P", plan="Plan", suite="Suite")
        self.assertEqual("NEEDS_REVIEW", preview["skipped"][0]["status"])
        self.assertNotIn("delete", preview)

    def test_external_change_becomes_conflict_not_overwrite(self) -> None:
        mapping = {"test_cases": {"TC-001": {
            "external_id": "100", "content_hash": "old", "last_synchronized_version": "7",
        }}}
        preview = build_preview(
            [case()], mapping, project="P", plan="Plan", suite="Suite",
            external_versions={"100": "8"},
        )
        self.assertEqual("100", preview["conflicts"][0]["external_id"])

    def test_mapping_state_is_private_run_metadata(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = persist_integration_state(Path(temporary) / ".ftd" / "runs" / "r1", {"test_cases": {}})
            self.assertTrue(path.is_file())
            self.assertIn("integration-state", path.parts)


def review_case(**over) -> dict:
    base = {**case(status="NEEDS_REVIEW"), "automation_suitability": "HIGH", "automation_readiness": "NEEDS_FIXTURE",
            "readiness_blockers": ["MISSING_FIXTURE"], "automation_layer": "UI", "automation_tool_hint": "PLAYWRIGHT",
            "question_refs": ["Q-017", "Q-024"], "source_kind": "CANONICAL"}
    base.update(over)
    return base


class ExecutionMetadataTests(unittest.TestCase):
    """The FTD execution classification is visible and recoverable from the Azure fields alone."""

    def test_status_readiness_blockers_and_questions_are_in_the_description_and_tags(self) -> None:
        fields = work_item_fields(map_test_case(review_case()), "canonical:TC-001")
        description, tags = fields["System.Description"], fields["System.Tags"].split("; ")
        for line in ("Status: NEEDS_REVIEW", "Automation suitability: HIGH", "Automation readiness: NEEDS_FIXTURE",
                     "Automation layer: UI", "Tool hint: PLAYWRIGHT", "Blockers: MISSING_FIXTURE",
                     "Questions: Q-017, Q-024", "Source: CANONICAL"):
            self.assertIn(f"<li>{line}</li>", description)
        self.assertTrue(description.startswith("<h3>FTD execution status</h3>"))
        for tag in ("ftd-managed", "ftd-key:canonical:TC-001", "FTD_STATUS:NEEDS_REVIEW", "FTD_READINESS:NEEDS_FIXTURE",
                    "FTD_SUITABILITY:HIGH", "FTD_LAYER:UI", "FTD_TOOL:PLAYWRIGHT"):
            self.assertIn(tag, tags)
        self.assertNotIn("FTD_STATUS:READY", tags)
        self.assertFalse([t for t in tags if "MISSING_FIXTURE" in t])  # blockers stay out of the tags

    def test_absent_values_are_never_rendered_or_invented(self) -> None:
        fields = work_item_fields(map_test_case(case()), "canonical:TC-001")
        tags = fields["System.Tags"].split("; ")
        self.assertEqual(["FTD_STATUS:READY"], [t for t in tags if t.startswith("FTD_")])
        for label in ("Automation", "Tool hint", "Blockers", "Questions"):
            self.assertNotIn(f"<li>{label}", fields["System.Description"])
        self.assertNotIn("System.State", fields)

    def test_every_status_of_the_selected_package_is_published_with_its_status_visible(self) -> None:
        statuses = ("READY", "NEEDS_REVIEW", "EXPLORATORY", "BLOCKED_EXTERNAL_DEPENDENCY", "BLOCKED_TEST_DATA")
        cases = [case(f"TC-{n:03d}", status) for n, status in enumerate(statuses, 1)]
        preview = build_preview(cases, {}, project="P", plan="Plan", suite="Suite", include_needs_review=True)
        self.assertEqual([], preview["skipped"])
        for item, status in zip(preview["create"], statuses):
            tags = work_item_fields(item["payload"], item["local_id"])["System.Tags"].split("; ")
            self.assertIn(f"FTD_STATUS:{status}", tags)
        excluded = build_preview(cases, {}, project="P", plan="Plan", suite="Suite", include_needs_review=False)
        self.assertEqual(["NEEDS_REVIEW"], [s["status"] for s in excluded["skipped"]])


if __name__ == "__main__":
    unittest.main()
