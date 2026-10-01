"""Non-regression firewall: the public workflows must behave exactly as the frozen v2.4.2 baseline.

The baseline (tests/fixtures/regression-baseline.json) was captured from the v2.4.2 implementation
over the public synthetic domain packs before any ADR code existed. A difference here is a
regression until an intended, justified change of that existing behavior proves otherwise.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import regression_snapshot as rs  # noqa: E402


def differences(expected, actual, path: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        found = []
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                found.append(f"{path}/{key}: missing")
            elif key not in expected:
                found.append(f"{path}/{key}: unexpected")
            else:
                found += differences(expected[key], actual[key], f"{path}/{key}")
        return found
    return [] if expected == actual else [f"{path}: {json.dumps(expected)[:160]} -> {json.dumps(actual)[:160]}"]


class RegressionFirewallTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = json.loads(rs.FIXTURE.read_text(encoding="utf-8"))
        cls.actual = json.loads(json.dumps(rs.snapshot(), sort_keys=True))

    def test_every_public_workflow_matches_the_frozen_v242_baseline(self) -> None:
        found = differences(self.expected, self.actual)
        self.assertEqual([], found, "existing behavior changed:\n" + "\n".join(found[:40]))

    def test_the_baseline_covers_every_public_workflow_and_pack(self) -> None:
        packs = self.expected["packs"]
        self.assertEqual(6, len(packs))
        for name, pack in packs.items():
            with self.subTest(pack=name):
                for area in ("canonical", "organization", "outputs", "current_run", "check", "clarify", "render",
                             "azure", "manual_import", "publication"):
                    self.assertIn(area, pack)
                self.assertEqual({"automatic": True, "explicit": True, "stale_pointer": "REFUSED"}, pack["current_run"])
                self.assertEqual(0, pack["publication"]["first"]["delete_operations"])
                self.assertEqual("APPROVAL_REQUIRED", pack["publication"]["approval_required"])
                self.assertEqual(0, pack["publication"]["second"]["create_test_cases"])
                self.assertEqual(0, pack["manual_import"]["existing"]["create"])
        self.assertTrue(any("chaos" in pack for pack in packs.values()))

    def test_v242_metadata_samples_still_parse_to_the_same_data(self) -> None:
        from integrations.azure_devops import read_ftd_metadata
        for sample in self.expected["metadata_samples"]:
            self.assertEqual(sample["parsed"], read_ftd_metadata(sample["description"]))


if __name__ == "__main__":
    unittest.main()
