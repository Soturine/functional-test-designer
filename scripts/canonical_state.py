#!/usr/bin/env python3
"""Persist a private canonical suite and render only requested public projections."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from render_markdown import render_markdown
from render_operational_scenarios import render_operational_scenarios
from render_report import render_report
from semantic_regression import fingerprint
from validate_output import validate


PUBLIC_FORMATS = {"HTML", "JSON", "MARKDOWN", "DIAGNOSTICS", "OPERATIONAL"}


@dataclass(frozen=True)
class OutputSelection:
    formats: frozenset[str]
    persist_internal_state: bool = True

    @classmethod
    def normalize(
        cls, formats: Iterable[str] | None = None, *, persist_internal_state: bool = True
    ) -> "OutputSelection":
        selected = frozenset(value.strip().upper() for value in (formats or ("HTML", "JSON", "MARKDOWN")))
        unsupported = sorted(selected - PUBLIC_FORMATS)
        if unsupported:
            raise ValueError("Unsupported public output formats: " + ", ".join(unsupported))
        if not selected:
            raise ValueError("At least one public output format is required")
        return cls(selected, persist_internal_state)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def persist_canonical_suite(
    artifact_root: Path,
    run_id: str,
    *,
    index: dict[str, Any],
    questions: dict[str, Any],
    cases: list[dict[str, Any]],
    operational_catalog: dict[str, Any] | None = None,
) -> Path:
    run_dir = artifact_root.resolve() / ".ftd" / "runs" / run_id
    catalog = operational_catalog or {"families": [], "family_count": 0}
    document = {
        "internal_schema_version": "1",
        "public_schema_version": "1.2",
        "semantic_fingerprint": fingerprint({"index": index, "questions": questions, "cases": cases}),
        "index": index,
        "questions": questions,
        "cases": cases,
        "operational_catalog": catalog,
    }
    path = run_dir / "canonical-suite.json"
    _write_json(path, document)
    return path


def read_canonical_suite(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("internal_schema_version") != "1" or document.get("public_schema_version") != "1.2":
        raise ValueError("Unsupported canonical suite version")
    expected = fingerprint({
        "index": document["index"],
        "questions": document["questions"],
        "cases": document["cases"],
    })
    if document.get("semantic_fingerprint") != expected:
        raise ValueError("Canonical suite fingerprint mismatch")
    return document


def _materialize_contract(workspace: Path, canonical: dict[str, Any]) -> None:
    _write_json(workspace / "test-cases.json", canonical["index"])
    _write_json(workspace / "questions.json", canonical["questions"])
    cases_by_id = {case["id"]: case for case in canonical["cases"]}
    for entry in canonical["index"]["test_cases"]:
        _write_json(workspace / entry["file"], cases_by_id[entry["id"]])


def render_selected_outputs(
    canonical_path: Path,
    artifact_root: Path,
    selection: OutputSelection,
) -> dict[str, Any]:
    """Render from canonical state only; project source reads are structurally zero."""
    canonical = read_canonical_suite(canonical_path)
    run_dir = canonical_path.parent
    workspace = run_dir / "render-work"
    workspace.mkdir(parents=True, exist_ok=True)
    _materialize_contract(workspace, canonical)
    errors = validate(workspace)
    if errors:
        raise ValueError("Canonical suite validation failed:\n- " + "\n- ".join(errors))
    markdown = render_markdown(workspace)
    report = render_report(
        workspace,
        artifact_formats=set(selection.formats).intersection({"JSON", "MARKDOWN"}),
    )

    output = artifact_root.resolve() / "output"
    output.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    if "JSON" in selection.formats:
        for relative in ("test-cases.json", "questions.json"):
            shutil.copy2(workspace / relative, output / relative)
        for entry in canonical["index"]["test_cases"]:
            destination = output / entry["file"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace / entry["file"], destination)
        rendered.append("JSON")
    if "MARKDOWN" in selection.formats:
        for source in markdown:
            destination = output / "test-cases-md" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        rendered.append("MARKDOWN")
    if "HTML" in selection.formats:
        shutil.copy2(report, output / "report.html")
        rendered.append("HTML")
    if "OPERATIONAL" in selection.formats:
        catalog = canonical.get("operational_catalog", {"families": []})
        destination = output / "operational-scenarios.md"
        destination.write_text(render_operational_scenarios(catalog), encoding="utf-8")
        rendered.append("OPERATIONAL")
    return {
        "requested_public_formats": sorted(selection.formats),
        "rendered_public_formats": sorted(rendered),
        "canonical_state_written": True,
        "source_reads_during_render": 0,
        "output_path": str(output),
        "semantic_fingerprint": canonical["semantic_fingerprint"],
    }
