#!/usr/bin/env python3
"""Record lightweight, privacy-safe execution diagnostics for a skill run."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE_NAMES = (
    "scope_resolution",
    "source_read",
    "evidence_normalization",
    "coverage_point_extraction",
    "coverage_extraction_audit",
    "testability_and_questions",
    "test_design_and_scenarios",
    "early_deduplication",
    "test_case_generation",
    "json_write",
    "validation",
    "validation_fixes",
    "markdown_render",
    "html_render",
    "final_summary",
)

SCOPE_PROOF_METRICS = (
    "selected_scope_roots",
    "resolved_scope_paths",
    "files_opened",
    "files_opened_outside_scope",
    "files_skipped_out_of_scope",
    "source_reads",
    "source_rereads",
    "temporary_files_created",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def elapsed(started_at: str, finished_at: str) -> float:
    seconds = (parse_timestamp(finished_at) - parse_timestamp(started_at)).total_seconds()
    return round(max(0.0, seconds), 6)


def read_document(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage(document: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAGE_NAMES:
        raise ValueError(f"Unknown stage {name!r}; expected one of: {', '.join(STAGE_NAMES)}")
    for item in document.get("stages", []):
        if item.get("name") == name:
            return item
    raise ValueError(f"Stage {name!r} is absent from the diagnostics document")


def start_run(path: Path) -> dict[str, Any]:
    if path.exists():
        raise ValueError(f"Diagnostics file already exists: {path}")
    started_at = timestamp()
    document = {
        "schema_version": "1.2",
        "run": {
            "diagnostic": True,
            "started_at": started_at,
            "finished_at": None,
            "total_elapsed_seconds": None,
            "timing_available": True,
        },
        "stages": [
            {
                "name": name,
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": None,
                "timing_available": False,
                "status": "pending",
                "what_was_done": [],
                "metrics": {},
                "notes": [],
            }
            for name in STAGE_NAMES
        ],
        "totals": {},
        "scope_proof": {},
        "warnings": [],
        "observed_bottlenecks": [],
        "optimization_candidates": [],
    }
    write_document(path, document)
    return document


def begin_stage(path: Path, name: str) -> dict[str, Any]:
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "pending":
        raise ValueError(f"Stage {name!r} cannot begin from status {item['status']!r}")
    item["started_at"] = timestamp()
    item["status"] = "running"
    write_document(path, document)
    return document


def parse_metric(raw: str) -> tuple[str, Any]:
    if "=" not in raw:
        raise ValueError(f"Metric must use key=value syntax: {raw!r}")
    key, value = raw.split("=", 1)
    if not key.strip():
        raise ValueError("Metric key cannot be empty")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key.strip(), parsed


def end_stage(
    path: Path,
    name: str,
    done: list[str],
    metrics: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    if not 1 <= len(done) <= 5:
        raise ValueError("what_was_done requires between 1 and 5 short entries")
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "running" or not item.get("started_at"):
        raise ValueError(f"Stage {name!r} must be running before it can end")
    finished_at = timestamp()
    item.update(
        {
            "finished_at": finished_at,
            "elapsed_seconds": elapsed(item["started_at"], finished_at),
            "timing_available": True,
            "status": status,
            "what_was_done": done,
            "metrics": metrics or {},
            "notes": notes or [],
        }
    )
    write_document(path, document)
    return document


def skip_stage(path: Path, name: str, done: list[str], notes: list[str] | None = None) -> dict[str, Any]:
    if not 1 <= len(done) <= 5:
        raise ValueError("what_was_done requires between 1 and 5 short entries")
    document = read_document(path)
    item = stage(document, name)
    if item["status"] != "pending":
        raise ValueError(f"Stage {name!r} cannot be skipped from status {item['status']!r}")
    item.update(
        {
            "status": "skipped",
            "what_was_done": done,
            "notes": notes or [],
        }
    )
    write_document(path, document)
    return document


def output_totals(output_dir: Path | None) -> dict[str, Any]:
    if output_dir is None:
        return {}
    index = read_document(output_dir / "test-cases.json")
    questions = read_document(output_dir / "questions.json").get("questions", [])
    cases = [read_document(output_dir / entry["file"]) for entry in index.get("test_cases", [])]
    statuses = Counter(case.get("status") for case in cases)
    return {
        "requirements": len(index.get("requirements", [])),
        "coverage_points": len(index.get("coverage_points", [])),
        "scenarios": len(index.get("scenarios", [])),
        "test_cases": len(cases),
        "steps": sum(len(case.get("steps", [])) for case in cases),
        "ready": statuses["READY"],
        "needs_review": statuses["NEEDS_REVIEW"],
        "blocked": statuses["BLOCKED"],
        "questions": len(questions),
        "markdown_files": len(list((output_dir / "test-cases-md").glob("*.md"))),
    }


def observed_metrics(document: dict[str, Any]) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    for item in document["stages"]:
        for key, value in item.get("metrics", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                observed[key] = observed.get(key, 0) + value
            elif isinstance(value, list):
                current = observed.setdefault(key, [])
                for entry in value:
                    if entry not in current:
                        current.append(entry)
            else:
                observed[key] = value
    return observed


def finish_run(
    path: Path,
    output_dir: Path | None = None,
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    document = read_document(path)
    unfinished = [item["name"] for item in document["stages"] if item["status"] in {"pending", "running"}]
    if unfinished:
        raise ValueError("Finish or skip every diagnostic stage first: " + ", ".join(unfinished))
    if candidates and len(candidates) > 3:
        raise ValueError("At most 3 optimization candidates are allowed")

    finished_at = timestamp()
    run = document["run"]
    run["finished_at"] = finished_at
    run["total_elapsed_seconds"] = elapsed(run["started_at"], finished_at)
    document["totals"] = output_totals(output_dir)
    observed = observed_metrics(document)
    document["totals"].update(observed)
    measured = [
        item
        for item in document["stages"]
        if item.get("timing_available") and isinstance(item.get("elapsed_seconds"), (int, float))
    ]
    known_stage_time = sum(item["elapsed_seconds"] for item in measured)
    total_elapsed = run["total_elapsed_seconds"]
    unattributed = round(max(0.0, total_elapsed - known_stage_time), 6)
    run["unattributed_seconds"] = unattributed
    run["unattributed_percent"] = round(100 * unattributed / total_elapsed, 2) if total_elapsed else 0.0
    if run["unattributed_percent"] > 20:
        document["warnings"].append(
            {
                "code": "HIGH_UNATTRIBUTED_TIME",
                "message": "More than 20% of elapsed time was outside measured stages; start timers before stage reasoning.",
                "unattributed_percent": run["unattributed_percent"],
            }
        )
    document["scope_proof"] = {
        key: observed.get(key, [] if key in {"selected_scope_roots", "resolved_scope_paths"} else 0)
        for key in SCOPE_PROOF_METRICS
    }
    document["scope_proof"]["scope_violation"] = bool(
        document["scope_proof"]["files_opened_outside_scope"]
    )
    if measured and known_stage_time > 0:
        slowest = max(measured, key=lambda item: item["elapsed_seconds"])
        document["observed_bottlenecks"] = [
            {
                "stage": slowest["name"],
                "elapsed_seconds": slowest["elapsed_seconds"],
                "percent_of_known_stage_time": round(100 * slowest["elapsed_seconds"] / known_stage_time, 2),
            }
        ]
    else:
        document["observed_bottlenecks"] = []
    document["optimization_candidates"] = candidates or []
    write_document(path, document)
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create a new diagnostic run")
    start.add_argument("file", type=Path)

    begin = subparsers.add_parser("begin", help="start timing one stage")
    begin.add_argument("file", type=Path)
    begin.add_argument("stage", choices=STAGE_NAMES)

    end = subparsers.add_parser("end", help="finish one timed stage")
    end.add_argument("file", type=Path)
    end.add_argument("stage", choices=STAGE_NAMES)
    end.add_argument("--done", action="append", required=True)
    end.add_argument("--metric", action="append", default=[])
    end.add_argument("--note", action="append", default=[])
    end.add_argument("--status", choices=("completed", "failed"), default="completed")

    skip = subparsers.add_parser("skip", help="record an intentionally skipped stage")
    skip.add_argument("file", type=Path)
    skip.add_argument("stage", choices=STAGE_NAMES)
    skip.add_argument("--done", action="append", required=True)
    skip.add_argument("--note", action="append", default=[])

    finish = subparsers.add_parser("finish", help="finish the run and derive totals")
    finish.add_argument("file", type=Path)
    finish.add_argument("--output", type=Path)
    finish.add_argument("--candidate", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            start_run(args.file)
        elif args.command == "begin":
            begin_stage(args.file, args.stage)
        elif args.command == "end":
            metrics = dict(parse_metric(raw) for raw in args.metric)
            end_stage(args.file, args.stage, args.done, metrics, args.note, args.status)
        elif args.command == "skip":
            skip_stage(args.file, args.stage, args.done, args.note)
        else:
            finish_run(args.file, args.output, args.candidate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: diagnostics updated at {args.file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
