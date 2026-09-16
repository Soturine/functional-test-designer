#!/usr/bin/env python3
"""Render validated test case JSON files as deterministic Markdown artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_output import validate  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def inline(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def bullet_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- None"


def joined(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def mermaid_label(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.replace("&", " and ")
    text = re.sub(r'["`\\\[\]{}|<>]', " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Not specified"


def wrap_mermaid_label(value: Any, width: int = 60) -> str:
    words = mermaid_label(value).split()
    lines: list[str] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        candidate_length = current_length + (1 if current else 0) + len(word)
        if current and candidate_length > width:
            lines.append(" ".join(current))
            current = [word]
            current_length = len(word)
        else:
            current.append(word)
            current_length = candidate_length
    if current:
        lines.append(" ".join(current))
    return "<br/>".join(lines)


def mermaid_source(case: dict[str, Any]) -> str:
    lines = ["flowchart TD", "    S([Start])"]
    chain = ["S"]
    expected_nodes: list[str] = []
    clarification_nodes: list[str] = []
    for step in case["steps"]:
        number = step["step"]
        action_id = f"A{number}"
        expected = step["expected_result"]
        result_id = f"R{number}" if expected is not None else f"C{number}"
        action = wrap_mermaid_label(step["action"])
        result = wrap_mermaid_label(expected or "Result needs clarification")
        lines.append(f'    {action_id}["{number} - Action<br/>{action}"]')
        if expected is None:
            lines.append(f'    {result_id}["Clarification required<br/>{result}"]')
            clarification_nodes.append(result_id)
        else:
            lines.append(f'    {result_id}["Expected result<br/>{result}"]')
            expected_nodes.append(result_id)
        chain.extend((action_id, result_id))
    lines.append("    F([End])")
    chain.append("F")
    lines.extend(
        [
            "",
            "    " + " --> ".join(chain),
            "",
            "    classDef startEnd fill:#f8fafc,stroke:#475569,stroke-width:1.5px,color:#0f172a;",
            "    classDef action fill:#eff6ff,stroke:#2563eb,stroke-width:1.5px,color:#0f172a;",
            "    classDef expected fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px,color:#14532d;",
            "    classDef clarification fill:#fff7ed,stroke:#ea580c,stroke-width:1.5px,color:#7c2d12,stroke-dasharray:4 3;",
            "",
            "    class S,F startEnd;",
            "    class " + ",".join(f"A{step['step']}" for step in case["steps"]) + " action;",
        ]
    )
    if expected_nodes:
        lines.append("    class " + ",".join(expected_nodes) + " expected;")
    if clarification_nodes:
        lines.append("    class " + ",".join(clarification_nodes) + " clarification;")
    return "\n".join(lines)


def extract_mermaid(markdown: str) -> str:
    match = re.search(r"## Fluxo do Teste\s*\n```mermaid\n(.*?)\n```\s*\Z", markdown, re.DOTALL)
    if not match:
        raise ValueError("Markdown must end with a Fluxo do Teste Mermaid block")
    return match.group(1)


def render_case(case: dict[str, Any], json_path: str) -> str:
    test_data = [f"- **{item['name']}:** {item['description']}" for item in case["test_data"]]
    steps = ["| # | Action | Expected result | Clarification |", "|---:|---|---|:---:|"]
    for step in case["steps"]:
        expected = step["expected_result"] or "Clarification required"
        clarification = "Yes" if step["needs_clarification"] else "No"
        steps.append(
            f"| {step['step']} | {inline(step['action'])} | {inline(expected)} | {clarification} |"
        )
    sources = [f"`{item['source']}` ({item['reference']})" for item in case["source_refs"]]
    sections = [
        f"# {case['id']} - {case['title']}",
        f"**Status:** {case['status']}  \n**Priority:** {case['priority']}  \n**Type:** {case['type']}",
        "## Objective\n" + case["objective"],
        "## Preconditions\n" + bullet_list(case["preconditions"]),
        "## Test Data\n" + ("\n".join(test_data) if test_data else "- None"),
        "## Steps\n" + "\n".join(steps),
        "## Postconditions\n" + bullet_list(case["postconditions"]),
        "## Cleanup\n" + bullet_list(case["cleanup"]),
        "## Traceability\n"
        f"- Requirements: {joined(case['requirement_refs'])}\n"
        f"- Scenarios: {joined(case['scenario_refs'])}\n"
        f"- Coverage points: {joined(case['coverage_point_refs'])}\n"
        f"- Sources: {', '.join(sources)}",
        f"## JSON Artifact\n`{json_path}`",
        "## Fluxo do Teste\n```mermaid\n" + mermaid_source(case) + "\n```",
    ]
    return "\n\n".join(sections) + "\n"


def render_markdown(output_dir: Path) -> list[Path]:
    output_dir = output_dir.resolve()
    errors = validate(output_dir)
    if errors:
        raise ValueError("Output validation failed:\n- " + "\n- ".join(errors))

    index = read_json(output_dir / "test-cases.json")
    markdown_dir = output_dir / "test-cases-md"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    expected_paths: set[Path] = set()
    rendered: list[Path] = []
    for entry in index["test_cases"]:
        case = read_json(output_dir / entry["file"])
        destination = (output_dir / entry["markdown_file"]).resolve()
        try:
            destination.relative_to(markdown_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Markdown path escapes test-cases-md: {entry['markdown_file']}") from exc
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_case(case, entry["file"]))
        expected_paths.add(destination)
        rendered.append(destination)

    for stale in markdown_dir.glob("*.md"):
        if stale.resolve() not in expected_paths:
            stale.unlink()
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="output", type=Path)
    args = parser.parse_args()
    try:
        rendered = render_markdown(args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: generated {len(rendered)} Markdown test case file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
