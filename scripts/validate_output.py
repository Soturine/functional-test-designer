#!/usr/bin/env python3
"""Validate functional-test-designer JSON output and cross-file invariants."""

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
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
            errors.append(f"{label} {json_path(error.absolute_path)}: {error.message}")
    except Exception as exc:  # Invalid schemas should fail with a useful message.
        errors.append(f"cannot apply schema {schema_path}: {exc}")


def duplicate_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values = [item.get(field) for item in items if isinstance(item, dict) and item.get(field) is not None]
    return sorted(value for value, count in Counter(values).items() if count > 1)


def check_duplicates(items: list[dict[str, Any]], field: str, label: str, errors: list[str]) -> None:
    for value in duplicate_values(items, field):
        errors.append(f"duplicate {label}: {value}")


def check_refs(values: Any, known: set[str], label: str, owner: str, errors: list[str]) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        if isinstance(value, str) and value not in known:
            errors.append(f"{owner} references unknown {label}: {value}")


def safe_case_path(output_dir: Path, relative: str, owner: str, errors: list[str]) -> Path | None:
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
    scenarios = index.get("scenarios", [])
    entries = index.get("test_cases", [])
    questions = questions_doc.get("questions", [])
    if not all(isinstance(value, list) for value in (requirements, scenarios, entries, questions)):
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
        item.get("id") for item in requirements if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    scenario_ids = {
        item.get("id") for item in scenarios if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    entry_by_id = {
        item.get("id"): item
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    raw_sources = index.get("sources", [])
    sources = {source for source in raw_sources if isinstance(source, str)} if isinstance(raw_sources, list) else set()

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        owner = requirement.get("id", "requirement")
        for source_ref in requirement.get("source_refs", []):
            source = source_ref.get("source") if isinstance(source_ref, dict) else None
            if source and source not in sources:
                errors.append(f"{owner} references source absent from index sources: {source}")

    mapped_requirements: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        owner = scenario.get("id", "scenario")
        refs = scenario.get("requirement_refs", [])
        check_refs(refs, requirement_ids, "requirement", owner, errors)
        if isinstance(refs, list):
            mapped_requirements.update(ref for ref in refs if isinstance(ref, str))

    questioned_requirements: set[str] = set()
    for question in questions:
        if not isinstance(question, dict):
            continue
        owner = question.get("id", "question")
        requirement_refs = question.get("requirement_refs", [])
        tc_refs = question.get("related_test_cases", [])
        check_refs(requirement_refs, requirement_ids, "requirement", owner, errors)
        check_refs(tc_refs, set(entry_by_id), "test case", owner, errors)
        if isinstance(requirement_refs, list):
            questioned_requirements.update(ref for ref in requirement_refs if isinstance(ref, str))
        if question.get("blocking"):
            for tc_id in tc_refs if isinstance(tc_refs, list) else []:
                entry = entry_by_id.get(tc_id)
                if entry and entry.get("status") != "BLOCKED":
                    errors.append(f"{owner} is blocking but {tc_id} status is not BLOCKED")

    for req_id in sorted(requirement_ids - mapped_requirements - questioned_requirements):
        errors.append(f"{req_id} has neither a scenario nor a clarification question")

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
        for field in ("title", "status", "requirement_refs", "scenario_refs"):
            if case.get(field) != entry.get(field):
                errors.append(f"{tc_id} field {field!r} differs between index and case file")

        check_refs(case.get("requirement_refs", []), requirement_ids, "requirement", tc_id, errors)
        check_refs(case.get("scenario_refs", []), scenario_ids, "scenario", tc_id, errors)
        step_numbers = [step.get("step") for step in case.get("steps", []) if isinstance(step, dict)]
        if step_numbers != list(range(1, len(step_numbers) + 1)):
            errors.append(f"{tc_id} step numbers must be ordered consecutively from 1")
        check_duplicates(case.get("subtests", []), "id", f"subtest ID in {tc_id}", errors)

    case_dir = output_dir / "test-cases"
    actual_files = {path.resolve() for path in case_dir.glob("TC-*.json")} if case_dir.is_dir() else set()
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
