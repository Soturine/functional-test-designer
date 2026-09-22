#!/usr/bin/env python3
"""Inventory selected Test Assets statically and give every behavior a disposition.

Selected tests are a challenge set and coverage evidence, never Functional
Authority. Hand-picking two recognizable tests out of hundreds is not review, so
discovery is mechanical and the classification of each discovered behavior is
explicit. Nothing here imports or executes the inspected code.
"""

from __future__ import annotations

import ast
import re
from typing import Any


TEST_ASSET_CLASSIFICATIONS = {
    "BUSINESS_RELEVANT",
    "TECHNICAL_ONLY",
    "DUPLICATE_EXISTING_COVERAGE",
    "IMPLEMENTATION_CHARACTERIZATION",
    "POSSIBLE_MISSING_SCENARIO",
    "OUT_OF_SCOPE_WITH_REASON",
}
REASON_REQUIRED_CLASSIFICATIONS = {"OUT_OF_SCOPE_WITH_REASON", "DUPLICATE_EXISTING_COVERAGE"}
CHALLENGE_DISPOSITIONS = {
    "ALREADY_COVERED_BY", "MATERIALIZED_AS_DERIVED_TC",
    "MATERIALIZED_AS_CHARACTERIZATION_TC", "QUESTION_REQUIRED",
    "INVALID_OR_OUT_OF_SCOPE", "TECHNICAL_ONLY",
}
TEST_NAME = re.compile(r"^test[_A-Z0-9]", re.IGNORECASE)
HIGH_SIGNAL_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


class TestAssetInventoryError(ValueError):
    """Raised when selected Test Assets were not meaningfully reviewed."""


def _is_test_function(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and bool(TEST_NAME.match(node.name))
    )


def _parametrization(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    """Count statically visible parametrization cases; return None when dynamic."""
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        name = ""
        while isinstance(target, ast.Attribute):
            name = target.attr if not name else name
            target = target.value
        if "parametrize" not in {name, getattr(decorator.func, "attr", "")}:
            continue
        for argument in decorator.args:
            if isinstance(argument, (ast.List, ast.Tuple)):
                return len(argument.elts)
        return None
    return None


def _constants(node: ast.AST) -> list[str]:
    found: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and HIGH_SIGNAL_CONSTANT.match(child.id):
            found.append(child.id)
        elif isinstance(child, ast.Attribute) and HIGH_SIGNAL_CONSTANT.match(child.attr):
            found.append(child.attr)
    return sorted(dict.fromkeys(found))


def discover_python_test_assets(source_text: str, source: str) -> list[dict[str, Any]]:
    """Statically discover every test behavior in one selected Python test asset."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        raise TestAssetInventoryError(f"Selected test asset {source} could not be parsed: {exc.msg}")
    behaviors: list[dict[str, Any]] = []

    def record(node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str | None) -> None:
        docstring = ast.get_docstring(node) or ""
        behaviors.append({
            "id": f"TA-{len(behaviors) + 1:03d}",
            "source": source,
            "test_class": owner,
            "test_function": node.name,
            "reference": f"{owner}::{node.name}" if owner else node.name,
            "documented": bool(docstring.strip()),
            "parametrized_cases": _parametrization(node),
            "referenced_constants": _constants(node),
        })

    for node in tree.body:
        if _is_test_function(node):
            record(node, None)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if _is_test_function(child):
                    record(child, node.name)
    return behaviors


def audit_test_asset_inventory(
    discovered: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    *, strict_challenge: bool = False,
) -> dict[str, Any]:
    """Require one explicit classification per discovered Test Asset behavior."""
    expected = {str(item["reference"]) for item in discovered}
    seen: set[str] = set()
    counts = {value: 0 for value in sorted(TEST_ASSET_CLASSIFICATIONS)}
    promoted: list[str] = []
    disposition_counts: dict[str, int] = {value: 0 for value in sorted(CHALLENGE_DISPOSITIONS)}
    for item in classifications:
        reference = str(item.get("reference", "")).strip()
        if reference not in expected:
            raise TestAssetInventoryError(
                f"Test asset classification {reference or '<missing>'} was never discovered"
            )
        if reference in seen:
            raise TestAssetInventoryError(f"Test asset {reference} is classified more than once")
        seen.add(reference)
        classification = str(item.get("classification", ""))
        if classification not in TEST_ASSET_CLASSIFICATIONS:
            raise TestAssetInventoryError(
                f"Test asset {reference} requires a supported classification"
            )
        if classification in REASON_REQUIRED_CLASSIFICATIONS and not str(item.get("reason", "")).strip():
            raise TestAssetInventoryError(f"Test asset {reference} requires a reason")
        if item.get("promoted_to_normative_scenario"):
            if classification not in {"BUSINESS_RELEVANT", "POSSIBLE_MISSING_SCENARIO"}:
                raise TestAssetInventoryError(
                    f"Test asset {reference} cannot become a functional Test Case from "
                    "technical coverage alone"
                )
            if not item.get("normative_support_refs"):
                raise TestAssetInventoryError(
                    f"Test asset {reference} cannot become normative without Functional Authority support"
                )
            promoted.append(reference)
        if strict_challenge:
            disposition = str(item.get("disposition", ""))
            if disposition not in CHALLENGE_DISPOSITIONS:
                raise TestAssetInventoryError(
                    f"Test asset {reference} requires an explicit challenge-set disposition"
                )
            targets = list(item.get("target_refs", []))
            if disposition in {
                "ALREADY_COVERED_BY", "MATERIALIZED_AS_DERIVED_TC",
                "MATERIALIZED_AS_CHARACTERIZATION_TC", "QUESTION_REQUIRED",
            } and not targets:
                raise TestAssetInventoryError(f"Test asset {reference} disposition requires target_refs")
            if disposition in {"INVALID_OR_OUT_OF_SCOPE", "TECHNICAL_ONLY"} and not str(item.get("reason", "")).strip():
                raise TestAssetInventoryError(f"Test asset {reference} disposition requires a reason")
            disposition_counts[disposition] += 1
        counts[classification] += 1

    missing = sorted(expected - seen)
    if missing:
        raise TestAssetInventoryError(
            "Discovered Test Asset behaviors have no disposition: " + ", ".join(missing)
        )
    return {
        "test_functions_inventory_count": len(discovered),
        "test_asset_business_behaviors": counts["BUSINESS_RELEVANT"],
        "test_asset_technical_only_behaviors": counts["TECHNICAL_ONLY"],
        "test_asset_duplicate_behaviors": counts["DUPLICATE_EXISTING_COVERAGE"],
        "test_asset_characterization_behaviors": counts["IMPLEMENTATION_CHARACTERIZATION"],
        "test_asset_possible_missing_scenarios": counts["POSSIBLE_MISSING_SCENARIO"],
        "test_asset_out_of_scope_behaviors": counts["OUT_OF_SCOPE_WITH_REASON"],
        "test_asset_behaviors_promoted": len(promoted),
        "test_asset_missing_dispositions": 0,
        "test_asset_behaviors_total": len(discovered),
        "test_asset_business_relevant": counts["BUSINESS_RELEVANT"],
        "test_asset_already_covered": disposition_counts["ALREADY_COVERED_BY"],
        "test_asset_promoted_to_derived": disposition_counts["MATERIALIZED_AS_DERIVED_TC"],
        "test_asset_promoted_to_characterization": disposition_counts["MATERIALIZED_AS_CHARACTERIZATION_TC"],
        "test_asset_questions": disposition_counts["QUESTION_REQUIRED"],
        "test_asset_rejected": disposition_counts["INVALID_OR_OUT_OF_SCOPE"] + disposition_counts["TECHNICAL_ONLY"],
        "test_asset_unresolved": 0,
        "test_asset_challenge_valid": True,
        "classification_counts": counts,
        "challenge_disposition_counts": disposition_counts,
    }
