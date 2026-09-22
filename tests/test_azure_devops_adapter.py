from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from integrations.azure_devops import (  # noqa: E402
    apply_preview, build_preview, map_test_case, persist_integration_state,
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


if __name__ == "__main__":
    unittest.main()
