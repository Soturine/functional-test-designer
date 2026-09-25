"""Publication organization: functional placements in operational order and execution
views that reference Test Cases without cloning them (synthetic, domain-neutral)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402

AUTHORITY = "spec.md"
TEXT = "\n".join([
    "FR-01 - Order Checkout",            # 1
    "The shopper checks out an order.",  # 2
    "FR-02 - Catalog Search",            # 3
    "The shopper searches products.",    # 4
    "UC-01 - Checkout",                  # 5
    "1. The shopper opens the cart.",    # 6
    "2. The system lists the cart items with prices.",  # 7
    "3. The shopper enters the shipping address.",      # 8
    "4. The shopper confirms payment of the order.",    # 9
    "AF-1.1 - Declined card: the payment is declined and the order stays open.",  # 10
    "BR-01 - Prices include tax",        # 11
])
INDEX = [
    {"identifier": "FR-01", "title": "Order Checkout", "source": AUTHORITY, "line": 1},
    {"identifier": "FR-02", "title": "Catalog Search", "source": AUTHORITY, "line": 3},
    {"identifier": "UC-01", "title": "Checkout", "source": AUTHORITY, "line": 5},
    {"identifier": "AF-1.1", "title": "Declined card", "source": AUTHORITY, "line": 10,
     "excerpt": "AF-1.1 - Declined card: the payment is declined and the order stays open."},
    {"identifier": "BR-01", "title": "Prices include tax", "source": AUTHORITY, "line": 11},
]


def case(number, title, identifiers, basis="ACCEPTANCE", primary_type="FUNCTIONAL", **extra):
    return {"id": f"TC-{number:03d}", "title": title, "objective": title, "source_identifiers": identifiers,
            "test_basis": basis, "primary_type": primary_type, "coverage_point_refs": [], "steps": [],
            "automation_layer": "UI", "automation_suitability": "HIGH", "scenario_refs": ["SC-1"], **extra}


def canonical(cases):
    kinds = {"FR": "FUNCTIONAL_REQUIREMENT", "UC": "USE_CASE", "AF": "ALTERNATIVE_FLOW", "BR": "BUSINESS_RULE"}
    requirements = [{"source_identifier": item["identifier"], "source_title": item["title"],
                     "kind": kinds[item["identifier"].split("-")[0]]} for item in INDEX]
    return {"index": {"requirements": requirements, "output_locale": "en", "normative_clauses": [],
                      "coverage_points": []}, "cases": cases}


def organize(cases, chaos=None):
    return pipeline.build_organization(canonical(cases), authority_index=INDEX, authority_texts={AUTHORITY: TEXT},
                                       chaos_runs=chaos)


def group(organization, group_id):
    return next(g for g in organization["groups"] if g["id"] == group_id)


class FunctionalOrderTests(unittest.TestCase):
    def test_placements_follow_the_use_case_main_flow_not_canonical_order(self) -> None:
        cases = [case(1, "Payment confirmation closes the order", ["FR-01", "UC-01"]),
                 case(2, "Shipping address entered is kept", ["FR-01", "UC-01"]),
                 case(3, "Cart opens with the shopper items", ["FR-01", "UC-01"])]
        members = group(organize(cases), "FR01")["members"]
        self.assertEqual(["TC-003", "TC-002", "TC-001"], [m["case"] for m in members])
        self.assertEqual("USE_CASE_MAIN_FLOW", group(organize(cases), "FR01")["order_source"])

    def test_an_alternative_flow_case_sits_after_the_step_it_branches_from(self) -> None:
        cases = [case(1, "Declined card keeps the order open", ["FR-01", "AF-1.1", "UC-01"]),
                 case(2, "Payment confirmation closes the order", ["FR-01", "UC-01"]),
                 case(3, "Cart opens with the shopper items", ["FR-01", "UC-01"]),
                 case(4, "Shipping address entered is kept", ["FR-01", "UC-01"])]
        order = [m["case"] for m in group(organize(cases), "FR01")["members"]]
        self.assertEqual(["TC-003", "TC-004", "TC-002", "TC-001"], order)

    def test_without_a_documented_flow_the_canonical_order_is_kept(self) -> None:
        cases = [case(1, "Search by name", ["FR-02"]), case(2, "Search by category", ["FR-02"]),
                 case(3, "Empty search", ["FR-02"])]
        fr02 = group(organize(cases), "FR02")
        self.assertEqual(["TC-001", "TC-002", "TC-003"], [m["case"] for m in fr02["members"]])
        self.assertEqual("CANONICAL_ORDER", fr02["order_source"])

    def test_rule_only_and_end_to_end_cases_go_to_their_own_groups(self) -> None:
        cases = [case(1, "Price shows tax", ["BR-01"]), case(2, "Checkout journey", ["UC-01"], basis="E2E"),
                 case(3, "Cart opens with the shopper items", ["FR-01", "UC-01"])]
        organization = organize(cases)
        self.assertEqual(["TC-001"], [m["case"] for m in group(organization, "TRANSVERSAL")["members"]])
        self.assertEqual(["TC-002"], [m["case"] for m in group(organization, "E2E")["members"]])
        self.assertNotIn("TC-002", [m["case"] for m in group(organization, "FR01")["members"]])


class MembershipVersusOrderTests(unittest.TestCase):
    """A flow orders a requirement's real members; it never makes a case a member."""

    def test_a_flow_alone_cannot_make_a_case_a_requirement_member(self) -> None:
        cases = [case(1, "Declined card keeps the order open", ["AF-1.1", "UC-01"]),
                 case(2, "Cart opens with the shopper items", ["FR-01", "UC-01"]),
                 case(3, "Payment confirmation closes the order", ["FR-01", "UC-01"])]
        organization = organize(cases)
        self.assertEqual(["TC-002", "TC-003"], [m["case"] for m in group(organization, "FR01")["members"]])
        uc = group(organization, "UC01")
        self.assertEqual(("USE_CASE", ["TC-001"]), (uc["kind"], [m["case"] for m in uc["members"]]))
        self.assertEqual(["UC01"], [m["group"] for m in organization["memberships"]["TC-001"]])
        self.assertEqual(3, len(organization["memberships"]))  # every case placed, none added or dropped

    def test_the_use_case_group_follows_its_own_flow(self) -> None:
        cases = [case(1, "Payment confirmation closes the order", ["UC-01"]),
                 case(2, "Declined card keeps the order open", ["AF-1.1"]),
                 case(3, "Cart opens with the shopper items", ["UC-01"])]
        uc = group(organize(cases), "UC01")
        self.assertEqual(["TC-003", "TC-001", "TC-002"], [m["case"] for m in uc["members"]])
        self.assertEqual("USE_CASE_MAIN_FLOW", uc["order_source"])

    def test_requirement_groups_come_before_use_case_groups(self) -> None:
        cases = [case(1, "Declined card keeps the order open", ["AF-1.1"]), case(2, "Search by name", ["FR-02"])]
        ids = [g["id"] for g in organize(cases)["groups"]]
        self.assertLess(ids.index("FR02"), ids.index("UC01"))

    def test_the_fallback_order_is_stable(self) -> None:
        cases = [case(3, "Empty search", ["FR-02"]), case(1, "Search by name", ["FR-02"]),
                 case(2, "Search by category", ["FR-02"])]
        first, second = organize(cases), organize(list(cases))
        self.assertEqual(first, second)
        self.assertEqual(["TC-003", "TC-001", "TC-002"], [m["case"] for m in group(first, "FR02")["members"]])
        self.assertEqual("CANONICAL_ORDER", group(first, "FR02")["order_source"])


class MembershipTests(unittest.TestCase):
    def test_one_case_in_its_functional_group_and_the_load_view_without_a_clone(self) -> None:
        cases = [case(1, "Checkout under concurrent shoppers", ["FR-01"], primary_type="CONCURRENCY"),
                 case(2, "Cart opens with the shopper items", ["FR-01", "UC-01"])]
        organization = organize(cases)
        self.assertIn("TC-001", [m["case"] for m in group(organization, "FR01")["members"]])
        self.assertEqual(["TC-001"], [m["case"] for m in group(organization, "LOAD_CONCURRENCY")["members"]])
        self.assertEqual({"FR01", "LOAD_CONCURRENCY"}, {m["group"] for m in organization["memberships"]["TC-001"]})
        self.assertEqual(0, organization["diagnostics"]["cloned_cases"])

    def test_a_post_suite_case_joins_its_related_group_and_its_execution_views(self) -> None:
        cases = [case(1, "Cart opens with the shopper items", ["FR-01", "UC-01"]),
                 case(2, "Payment confirmation closes the order", ["FR-01", "UC-01"])]
        chaos = [{"chaos_run_id": "chaos-001", "cases": [
            {"id": "CH-001", "title": "Card terminal loses power during payment", "related_test_cases": ["TC-001"],
             "execution_tags": ["PHYSICAL_DEVICE", "CHAOS_RECOVERY"]}]}]
        organization = organize(cases, chaos)
        fr01 = [m["case"] for m in group(organization, "FR01")["members"]]
        self.assertEqual(["TC-001", "CH-001", "TC-002"], fr01)  # right after the case it challenges
        self.assertEqual({"FR01", "PHYSICAL_DEVICE", "CHAOS_RESILIENCE"},
                         {m["group"] for m in organization["memberships"]["chaos-001:CH-001"]})
        for view in ("PHYSICAL_DEVICE", "CHAOS_RESILIENCE"):
            entry = group(organization, view)["members"][0]
            self.assertEqual(("CH-001", "POST_SUITE", "chaos-001"), (entry["case"], entry["origin"], entry["chaos_run_id"]))

    def test_a_manual_view_identical_to_the_physical_one_is_omitted(self) -> None:
        cases = [case(1, "Scanner reads the parcel label", ["FR-01"], primary_type="HARDWARE_INTEGRATION",
                      automation_suitability="MANUAL_ONLY")]
        ids = [g["id"] for g in organize(cases)["groups"]]
        self.assertIn("PHYSICAL_DEVICE", ids)
        self.assertNotIn("MANUAL_FIELD", ids)

    def test_labels_follow_the_run_locale(self) -> None:
        document = canonical([case(1, "Price shows tax", ["BR-01"])])
        document["index"]["output_locale"] = "pt-BR"
        organization = pipeline.build_organization(document, authority_index=INDEX, authority_texts={AUTHORITY: TEXT})
        self.assertEqual("Regras de negócio transversais", group(organization, "TRANSVERSAL")["label"])


if __name__ == "__main__":
    unittest.main()
