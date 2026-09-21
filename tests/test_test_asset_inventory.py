"""Selected Test Assets are inventoried statically and dispositioned explicitly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from test_asset_inventory import (  # noqa: E402
    TestAssetInventoryError, audit_test_asset_inventory, discover_python_test_assets,
)


SAMPLE = '''
import pytest

STATUS_REJECTED = "REJECTED"


def helper_not_a_test():
    return 1


def test_module_level_behavior():
    """A documented module-level behavior."""
    assert True


@pytest.mark.parametrize("value", [1, 2, 3])
def test_parametrized_boundary(value):
    assert value


class TestTransfers:
    def test_rejects_without_permission(self):
        """Rejects the transfer for an operator without permission."""
        assert STATUS_REJECTED

    def test_internal_serializer_shape(self):
        assert True

    def not_a_test(self):
        return None
'''


class StaticDiscoveryTests(unittest.TestCase):
    def test_discovery_finds_every_test_behavior_without_executing_the_asset(self) -> None:
        behaviors = discover_python_test_assets(SAMPLE, "tests/legacy_test_transfers.py")
        references = [item["reference"] for item in behaviors]
        self.assertEqual(
            [
                "test_module_level_behavior",
                "test_parametrized_boundary",
                "TestTransfers::test_rejects_without_permission",
                "TestTransfers::test_internal_serializer_shape",
            ],
            references,
        )

    def test_discovery_records_parametrization_docstrings_and_high_signal_constants(self) -> None:
        behaviors = {
            item["reference"]: item
            for item in discover_python_test_assets(SAMPLE, "tests/legacy_test_transfers.py")
        }
        self.assertEqual(3, behaviors["test_parametrized_boundary"]["parametrized_cases"])
        self.assertTrue(behaviors["test_module_level_behavior"]["documented"])
        self.assertFalse(behaviors["TestTransfers::test_internal_serializer_shape"]["documented"])
        self.assertEqual(
            ["STATUS_REJECTED"],
            behaviors["TestTransfers::test_rejects_without_permission"]["referenced_constants"],
        )

    def test_an_unparsable_asset_is_reported_rather_than_silently_skipped(self) -> None:
        with self.assertRaisesRegex(TestAssetInventoryError, "could not be parsed"):
            discover_python_test_assets("def broken(:\n", "tests/broken.py")


class TestAssetDispositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.discovered = discover_python_test_assets(SAMPLE, "tests/legacy_test_transfers.py")

    def classifications(self) -> list[dict[str, object]]:
        return [
            {"reference": "test_module_level_behavior", "classification": "BUSINESS_RELEVANT"},
            {"reference": "test_parametrized_boundary", "classification": "POSSIBLE_MISSING_SCENARIO"},
            {"reference": "TestTransfers::test_rejects_without_permission",
             "classification": "BUSINESS_RELEVANT"},
            {"reference": "TestTransfers::test_internal_serializer_shape",
             "classification": "TECHNICAL_ONLY"},
        ]

    def test_hand_picking_a_couple_of_tests_leaves_the_rest_unaccounted(self) -> None:
        with self.assertRaisesRegex(TestAssetInventoryError, "no disposition"):
            audit_test_asset_inventory(self.discovered, self.classifications()[:2])

    def test_a_technical_test_cannot_be_promoted_to_a_functional_test_case(self) -> None:
        classifications = self.classifications()
        classifications[3]["promoted_to_normative_scenario"] = True
        with self.assertRaisesRegex(TestAssetInventoryError, "technical coverage alone"):
            audit_test_asset_inventory(self.discovered, classifications)

    def test_test_assets_are_never_functional_authority_on_their_own(self) -> None:
        classifications = self.classifications()
        classifications[1]["promoted_to_normative_scenario"] = True
        with self.assertRaisesRegex(TestAssetInventoryError, "Functional Authority support"):
            audit_test_asset_inventory(self.discovered, classifications)

    def test_a_business_relevant_asset_may_be_promoted_with_authority_support(self) -> None:
        classifications = self.classifications()
        classifications[1]["promoted_to_normative_scenario"] = True
        classifications[1]["normative_support_refs"] = [
            {"source": "requirements.md", "reference": "RF-002#AC-3"}
        ]
        metrics = audit_test_asset_inventory(self.discovered, classifications)
        self.assertEqual(1, metrics["test_asset_behaviors_promoted"])
        self.assertEqual(4, metrics["test_functions_inventory_count"])
        self.assertEqual(2, metrics["test_asset_business_behaviors"])
        self.assertEqual(1, metrics["test_asset_technical_only_behaviors"])
        self.assertEqual(0, metrics["test_asset_missing_dispositions"])

    def test_a_duplicate_disposition_requires_a_reason(self) -> None:
        classifications = self.classifications()
        classifications[0]["classification"] = "DUPLICATE_EXISTING_COVERAGE"
        with self.assertRaisesRegex(TestAssetInventoryError, "requires a reason"):
            audit_test_asset_inventory(self.discovered, classifications)

    def test_a_classification_for_an_undiscovered_behavior_is_rejected(self) -> None:
        classifications = self.classifications()
        classifications.append({"reference": "test_imagined", "classification": "TECHNICAL_ONLY"})
        with self.assertRaisesRegex(TestAssetInventoryError, "never discovered"):
            audit_test_asset_inventory(self.discovered, classifications)


if __name__ == "__main__":
    unittest.main()
