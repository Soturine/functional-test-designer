#!/usr/bin/env python3
"""Validate functional-test-designer V1.1 output and cross-file invariants."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    print(
        "ERROR: missing dependency 'jsonschema'. Install with "
        "'python -m pip install -r requirements.txt'.",
        file=sys.stderr,
    )
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}")
    except OSError as exc:
        errors.append(f"cannot read {path}: {exc}")
    return None


def json_path(parts: Any) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def validate_schema(instance: Any, schema_name: str, label: str, errors: list[str]) -> None:
    schema_path = SCHEMA_DIR / schema_name
    schema = load_json(schema_path, errors)
    if schema is None:
        return
    try:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        sort_key = lambda item: tuple(str(part) for part in item.absolute_path)
        for error in sorted(validator.iter_errors(instance), key=sort_key):
            errors.append(f"{label} {json_path(error.absolute_path)}: {error.message}")
    except Exception as exc:  # Invalid schemas should fail with a useful message.
        errors.append(f"cannot apply schema {schema_path}: {exc}")


def duplicate_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values = [
        item.get(field)
        for item in items
        if isinstance(item, dict) and isinstance(item.get(field), str)
    ]
    return sorted(value for value, count in Counter(values).items() if count > 1)


def check_duplicates(items: list[dict[str, Any]], field: str, label: str, errors: list[str]) -> None:
    for value in duplicate_values(items, field):
        errors.append(f"duplicate {label}: {value}")


def string_set(values: Any) -> set[str]:
    return {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()


def check_refs(values: Any, known: set[str], label: str, owner: str, errors: list[str]) -> None:
    for value in string_set(values):
        if value not in known:
            errors.append(f"{owner} references unknown {label}: {value}")


def check_source_refs(values: Any, sources: set[str], owner: str, errors: list[str]) -> None:
    if not isinstance(values, list):
        return
    for source_ref in values:
        source = source_ref.get("source") if isinstance(source_ref, dict) else None
        if isinstance(source, str) and source not in sources:
            errors.append(f"{owner} references source absent from index sources: {source}")


def safe_case_path(output_dir: Path, relative: Any, owner: str, errors: list[str]) -> Path | None:
    if not isinstance(relative, str):
        errors.append(f"{owner} file path must be a string")
        return None
    expected = output_dir / relative
    try:
        expected.resolve().relative_to(output_dir.resolve())
    except (OSError, ValueError):
        errors.append(f"{owner} file path escapes output directory: {relative}")
        return None
    return expected


def validate_coverage_points(
    coverage_points: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    requirement_ids: set[str],
    entries_by_id: dict[str, dict[str, Any]],
    questions_by_id: dict[str, dict[str, Any]],
    sources: set[str],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    coverage_by_id = {
        item["id"]: item
        for item in coverage_points
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    check_duplicates(coverage_points, "id", "coverage point ID", errors)

    covered_requirements: set[str] = set()
    for coverage_point in coverage_points:
        if not isinstance(coverage_point, dict):
            continue
        cp_id = coverage_point.get("id", "coverage point")
        requirement_ref = coverage_point.get("requirement_ref")
        disposition = coverage_point.get("disposition")
        targets = coverage_point.get("target_refs", [])
        target_refs = string_set(targets)

        if isinstance(requirement_ref, str):
            covered_requirements.add(requirement_ref)
            if requirement_ref not in requirement_ids:
                errors.append(f"{cp_id} references unknown requirement: {requirement_ref}")
        check_source_refs(coverage_point.get("source_refs", []), sources, cp_id, errors)

        destination_valid = False
        if disposition == "TEST_CASE":
            destination_valid = bool(target_refs) and all(target in entries_by_id for target in target_refs)
            check_refs(targets, set(entries_by_id), "test case", cp_id, errors)
            for tc_id in target_refs & set(entries_by_id):
                if cp_id not in string_set(entries_by_id[tc_id].get("coverage_point_refs", [])):
                    errors.append(f"{cp_id} targets {tc_id}, but {tc_id} does not reference {cp_id}")
        elif disposition == "QUESTION":
            destination_valid = bool(target_refs) and all(target in questions_by_id for target in target_refs)
            check_refs(targets, set(questions_by_id), "question", cp_id, errors)
            for question_id in target_refs & set(questions_by_id):
                question_requirements = string_set(questions_by_id[question_id].get("requirement_refs", []))
                if isinstance(requirement_ref, str) and requirement_ref not in question_requirements:
                    errors.append(
                        f"{cp_id} targets {question_id}, but {question_id} does not reference {requirement_ref}"
                    )
        elif disposition == "OUT_OF_SCOPE":
            reason = coverage_point.get("reason")
            destination_valid = not target_refs and isinstance(reason, str) and bool(reason.strip())

        if not destination_valid:
            errors.append(f"{cp_id} has no valid destination")

    for requirement in requirements:
        if not isinstance(requirement, dict) or requirement.get("status") != "TESTABLE":
            continue
        req_id = requirement.get("id")
        if isinstance(req_id, str) and req_id not in covered_requirements:
            errors.append(f"{req_id} is TESTABLE but has no coverage point")

    return coverage_by_id


def validate(output_dir: Path) -> list[str]:
    errors: list[str] = []
    index_path = output_dir / "test-cases.json"
    questions_path = output_dir / "questions.json"
    index = load_json(index_path, errors)
    questions_doc = load_json(questions_path, errors)
    if index is None or questions_doc is None:
        return errors

    validate_schema(index, "test-case-index.schema.json", str(index_path), errors)
    validate_schema(questions_doc, "questions.schema.json", str(questions_path), errors)
    if not isinstance(index, dict) or not isinstance(questions_doc, dict):
        return errors

    requirements = index.get("requirements", [])
    coverage_points = index.get("coverage_points", [])
    scenarios = index.get("scenarios", [])
    entries = index.get("test_cases", [])
    questions = questions_doc.get("questions", [])
    collections = (requirements, coverage_points, scenarios, entries, questions)
    if not all(isinstance(value, list) for value in collections):
        return errors

    check_duplicates(requirements, "id", "requirement ID", errors)
    check_duplicates(scenarios, "id", "scenario ID", errors)
    check_duplicates(entries, "id", "test case ID", errors)
    check_duplicates(entries, "file", "test case file", errors)
    check_duplicates(questions, "id", "question ID", errors)

    normalized_questions = []
    for question in questions:
        text = question.get("question") if isinstance(question, dict) else None
        if isinstance(text, str) and text.strip():
            normalized_questions.append(text.strip().casefold())
    for text, count in Counter(normalized_questions).items():
        if count > 1:
            errors.append(f"duplicate question text: {text}")

    requirement_ids = {
        item["id"]
        for item in requirements
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    scenario_ids = {
        item["id"]
        for item in scenarios
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    entries_by_id = {
        item["id"]: item
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    questions_by_id = {
        item["id"]: item
        for item in questions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    sources = string_set(index.get("sources", []))

    for requirement in requirements:
        if isinstance(requirement, dict):
            check_source_refs(
                requirement.get("source_refs", []), sources, requirement.get("id", "requirement"), errors
            )

    scenario_requirements: dict[str, set[str]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("id", "scenario")
        refs = scenario.get("requirement_refs", [])
        check_refs(refs, requirement_ids, "requirement", scenario_id, errors)
        if isinstance(scenario_id, str):
            scenario_requirements[scenario_id] = string_set(refs)

    questioned_case_ids: set[str] = set()
    blocking_case_ids: set[str] = set()
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = question.get("id", "question")
        requirement_refs = question.get("requirement_refs", [])
        tc_refs = question.get("related_test_cases", [])
        check_refs(requirement_refs, requirement_ids, "requirement", question_id, errors)
        check_refs(tc_refs, set(entries_by_id), "test case", question_id, errors)
        check_source_refs(question.get("source_refs", []), sources, question_id, errors)
        questioned_case_ids.update(string_set(tc_refs))
        if question.get("blocking"):
            blocking_case_ids.update(string_set(tc_refs))
            for tc_id in string_set(tc_refs) & set(entries_by_id):
                if entries_by_id[tc_id].get("status") != "BLOCKED":
                    errors.append(f"{question_id} is blocking but {tc_id} status is not BLOCKED")

    coverage_by_id = validate_coverage_points(
        coverage_points,
        requirements,
        requirement_ids,
        entries_by_id,
        questions_by_id,
        sources,
        errors,
    )
    coverage_ids = set(coverage_by_id)

    indexed_files: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tc_id = entry.get("id", "test case")
        expected_relative = f"test-cases/{tc_id}.json"
        relative = entry.get("file", "")
        if relative != expected_relative:
            errors.append(f"{tc_id} file must be {expected_relative}, got {relative!r}")
        case_path = safe_case_path(output_dir, relative, tc_id, errors)
        if case_path is None:
            continue
        indexed_files.add(case_path.resolve())
        case = load_json(case_path, errors)
        if case is None:
            continue

        validate_schema(case, "test-case.schema.json", str(case_path), errors)
        if not isinstance(case, dict):
            continue
        if case.get("id") != tc_id:
            errors.append(f"{tc_id} index ID does not match file ID {case.get('id')!r}")
        compared_fields = ("title", "status", "requirement_refs", "scenario_refs", "coverage_point_refs")
        for field in compared_fields:
            if case.get(field) != entry.get(field):
                errors.append(f"{tc_id} field {field!r} differs between index and case file")

        case_requirement_refs = string_set(case.get("requirement_refs", []))
        case_scenario_refs = string_set(case.get("scenario_refs", []))
        case_coverage_refs = string_set(case.get("coverage_point_refs", []))
        check_refs(case_requirement_refs, requirement_ids, "requirement", tc_id, errors)
        check_refs(case_scenario_refs, scenario_ids, "scenario", tc_id, errors)
        check_refs(case_coverage_refs, coverage_ids, "coverage point", tc_id, errors)
        check_source_refs(case.get("source_refs", []), sources, tc_id, errors)

        scenario_requirement_refs: set[str] = set()
        for scenario_id in case_scenario_refs:
            scenario_requirement_refs.update(scenario_requirements.get(scenario_id, set()))
        for req_id in sorted(case_requirement_refs - scenario_requirement_refs):
            errors.append(f"{tc_id} requirement {req_id} is not covered by its referenced scenarios")

        for cp_id in case_coverage_refs & coverage_ids:
            coverage_point = coverage_by_id[cp_id]
            if coverage_point.get("disposition") != "TEST_CASE" or tc_id not in string_set(
                coverage_point.get("target_refs", [])
            ):
                errors.append(f"{tc_id} references {cp_id}, but {cp_id} does not target {tc_id}")
            cp_requirement = coverage_point.get("requirement_ref")
            if isinstance(cp_requirement, str) and cp_requirement not in case_requirement_refs:
                errors.append(f"{tc_id} references {cp_id} without requirement {cp_requirement}")

        steps = case.get("steps", [])
        step_numbers = [step.get("step") for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []
        if step_numbers != list(range(1, len(step_numbers) + 1)):
            errors.append(f"{tc_id} step numbers must be ordered consecutively from 1")
        pending_steps = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("needs_clarification") is True
        ] if isinstance(steps, list) else []
        if pending_steps and tc_id not in questioned_case_ids:
            errors.append(f"{tc_id} has clarification-pending steps but no related question")
        if case.get("status") == "BLOCKED" and tc_id not in blocking_case_ids:
            errors.append(f"{tc_id} is BLOCKED but has no related blocking question")

    case_dir = output_dir / "test-cases"
    actual_files = {path.resolve() for path in case_dir.glob("*.json")} if case_dir.is_dir() else set()
    for path in sorted(actual_files - indexed_files):
        errors.append(f"unindexed test case file: {path}")
    for path in sorted(indexed_files - actual_files):
        errors.append(f"indexed test case file is absent: {path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="output", type=Path, help="output directory")
    args = parser.parse_args()
    errors = validate(args.output.resolve())
    if errors:
        print(f"FAIL: {len(errors)} validation error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: output matches schemas and cross-file invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
