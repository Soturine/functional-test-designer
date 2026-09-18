#!/usr/bin/env python3
"""Run the neutral, deterministic scenario-independence regression benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scenario_independence import candidate_from_coverage_point, merge_candidates, metrics


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "benchmarks" / "scenario-independence" / "fixture.json"


def run(fixture_path: Path) -> dict[str, Any]:
    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    results = []
    aggregate = {
        "coverage_points": 0,
        "scenario_candidates_before_merge": 0,
        "scenario_merge_candidates": 0,
        "scenario_merges_applied": 0,
        "scenarios_after_merge": 0,
        "multi_cp_scenarios": 0,
        "possible_scenario_overcompression_warnings": 0,
        "semantic_duplicates_removed": 0,
        "test_cases_generated": 0,
    }
    for fixture in document["fixtures"]:
        candidates = []
        for number, profile_values in enumerate(fixture["profiles"], 1):
            cp_id = f"CP-{fixture['id']}-{number}"
            profile = dict(fixture.get("defaults", {})) | dict(profile_values)
            coverage_point = {
                "id": cp_id,
                "requirement_ref": f"REQ-{fixture['id']}",
                "source_refs": profile.pop(
                    "source_refs",
                    [{"source": "requirements.md", "reference": f"{fixture['id']}-{number}"}],
                ),
            }
            candidates.append(candidate_from_coverage_point(coverage_point, profile))
        scenarios, decisions = merge_candidates(candidates)
        observed = metrics(len(candidates), candidates, scenarios, decisions)
        if observed["scenarios_after_merge"] != fixture["expected_scenarios"]:
            raise AssertionError(
                f"Fixture {fixture['id']} expected {fixture['expected_scenarios']} scenarios, "
                f"got {observed['scenarios_after_merge']}"
            )
        if observed["test_cases_generated"] != fixture["expected_test_cases"]:
            raise AssertionError(f"Fixture {fixture['id']} Test Case count differs")
        if observed["scenario_merges_applied"] != fixture["expected_merges"]:
            raise AssertionError(f"Fixture {fixture['id']} merge count differs")
        expected_reason = fixture.get("expected_merge_reason")
        if expected_reason and {item["reason"] for item in decisions} != {expected_reason}:
            raise AssertionError(f"Fixture {fixture['id']} merge reason differs")
        result = {"fixture": fixture["id"], **observed}
        results.append(result)
        for key in aggregate:
            aggregate[key] += observed[key]
    return {"benchmark": document["name"], "fixtures": results, "metrics": aggregate}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
