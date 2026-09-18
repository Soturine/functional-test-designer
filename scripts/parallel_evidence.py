#!/usr/bin/env python3
"""Bounded fan-out/fan-in for selected-source evidence collection."""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any


SOURCE_ROLES = {
    "FUNCTIONAL_AUTHORITY",
    "IMPLEMENTATION_EVIDENCE",
    "TECHNICAL_CONTEXT",
    "TEST_ASSET",
    "OTHER_SELECTED",
}
FORBIDDEN_WORKER_FIELDS = {
    "final_normative_authority",
    "normative_clause",
    "coverage_point",
    "scenario",
    "test_case",
    "test_case_count",
    "normative_oracle",
    "scenario_cohesion",
}


@dataclass(frozen=True)
class SourceAssignment:
    source: str
    source_role: str
    source_ref: str


@dataclass(frozen=True)
class EvidenceRecord:
    source: str
    source_role: str
    source_ref: str
    source_excerpt_ref: str
    observation_or_claim: str
    actor: str = ""
    state: str = ""
    trigger: str = ""
    input: str = ""
    output: str = ""
    constraint: str = ""
    timing: str = ""
    navigation: tuple[str, ...] = ()
    visible_labels: tuple[str, ...] = ()
    uncertainty: str = ""
    possible_conflict: str = ""


@dataclass(frozen=True)
class EvidenceAnalysisResult:
    records: tuple[EvidenceRecord, ...]
    metrics: dict[str, Any]
    source_owners: dict[str, int]
    barrier_complete: bool

    def records_by_role(self) -> dict[str, tuple[EvidenceRecord, ...]]:
        if not self.barrier_complete:
            raise ValueError("Evidence fan-in is unavailable before the completion barrier")
        return {
            role: tuple(record for record in self.records if record.source_role == role)
            for role in SOURCE_ROLES
            if any(record.source_role == role for record in self.records)
        }


def _record(value: EvidenceRecord | dict[str, Any], assignment: SourceAssignment) -> EvidenceRecord:
    if isinstance(value, EvidenceRecord):
        record = value
    elif isinstance(value, dict):
        forbidden = FORBIDDEN_WORKER_FIELDS.intersection(value)
        if forbidden:
            raise ValueError(
                "Source workers cannot decide final semantic fields: "
                + ", ".join(sorted(forbidden))
            )
        record = EvidenceRecord(**value)
    else:
        raise ValueError("Source analyzer must return EvidenceRecord values")
    if record.source != assignment.source or record.source_role != assignment.source_role:
        raise ValueError("Evidence Record source ownership differs from its assignment")
    if not record.source_ref or not record.observation_or_claim:
        raise ValueError("Evidence Record requires provenance and an observation")
    return record


def analyze_selected_sources(
    assignments: list[SourceAssignment],
    selected_sources: set[str],
    analyzer: Callable[[SourceAssignment], list[EvidenceRecord | dict[str, Any]]],
    *,
    max_workers: int = 4,
) -> EvidenceAnalysisResult:
    """Analyze each selected file once and return only after the fan-in barrier."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least one")
    paths = [assignment.source for assignment in assignments]
    duplicates = [path for path, count in Counter(paths).items() if count > 1]
    if duplicates:
        raise ValueError("Each selected source requires one analysis owner: " + ", ".join(duplicates))
    outside = sorted(set(paths) - set(selected_sources))
    if outside:
        raise ValueError("Source assignment is outside selected scope: " + ", ".join(outside))
    for assignment in assignments:
        if assignment.source_role not in SOURCE_ROLES:
            raise ValueError(f"Unsupported source role {assignment.source_role}")

    lock = threading.Lock()
    active = 0
    maximum = 0
    started = 0
    completed = 0
    durations: dict[int, float] = {}
    results: dict[int, list[EvidenceRecord]] = {}

    def work(index: int, assignment: SourceAssignment) -> tuple[int, list[EvidenceRecord], float]:
        nonlocal active, maximum, started, completed
        began = time.perf_counter()
        with lock:
            active += 1
            started += 1
            maximum = max(maximum, active)
        try:
            values = analyzer(assignment)
            if not isinstance(values, list):
                raise ValueError("Source analyzer must return a list")
            records = [_record(value, assignment) for value in values]
            return index, records, time.perf_counter() - began
        finally:
            with lock:
                active -= 1
                completed += 1

    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(assignments)))) as executor:
        futures = {
            executor.submit(work, index, assignment): index
            for index, assignment in enumerate(assignments)
        }
        for future in as_completed(futures):
            index, records, duration = future.result()
            results[index] = records
            durations[index] = duration
    wall_clock = time.perf_counter() - wall_started

    ordered = tuple(
        record
        for index in range(len(assignments))
        for record in results.get(index, [])
    )
    by_role = Counter(record.source_role for record in ordered)
    barrier_complete = started == completed == len(assignments) == len(results)
    if not barrier_complete:
        raise ValueError("Selected-source analysis did not reach the fan-in barrier")
    shortest = min(durations.values(), default=0.0)
    metrics = {
        "source_analysis_workers_started": started,
        "source_analysis_workers_completed": completed,
        "source_analysis_max_concurrency": maximum,
        "source_files_assigned": len(assignments),
        "source_files_reused_from_evidence_map": 0,
        "duplicate_source_reads": 0,
        "evidence_records_generated": len(ordered),
        "evidence_records_by_role": dict(sorted(by_role.items())),
        "source_analysis_barrier_wait_seconds": round(max(0.0, wall_clock - shortest), 6),
        "stage_wall_clock_seconds": round(wall_clock, 6),
        "aggregate_worker_seconds": round(sum(durations.values()), 6),
    }
    return EvidenceAnalysisResult(
        records=ordered,
        metrics=metrics,
        source_owners={assignment.source: index for index, assignment in enumerate(assignments)},
        barrier_complete=True,
    )


def evidence_record_dict(record: EvidenceRecord) -> dict[str, Any]:
    return asdict(record)
