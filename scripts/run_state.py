#!/usr/bin/env python3
"""Privacy-safe internal checkpoints and diagnostics compatibility checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CHECKPOINTS = (
    "SCOPE_RESOLVED",
    "EVIDENCE_BARRIER_COMPLETE",
    "SOURCE_ATOMICITY_COMPLETE",
    "SCENARIOS_FROZEN",
    "PROCEDURAL_COMPLETE",
    "VALIDATED",
)
FORBIDDEN_STATE_KEYS = {"token", "credential", "authorization", "auth_header", "raw_source"}


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_manifest(paths: list[Path], root: Path) -> dict[str, str]:
    return {
        path.resolve().relative_to(root.resolve()).as_posix(): content_hash(path)
        for path in sorted(paths, key=lambda value: str(value))
    }


def _reject_sensitive(value: Any, path: str = "state") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in FORBIDDEN_STATE_KEYS:
                raise ValueError(f"Internal run state cannot persist sensitive field {path}.{key}")
            _reject_sensitive(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive(item, f"{path}[{index}]")


@dataclass(frozen=True)
class CheckpointLoad:
    checkpoint: str
    payload: dict[str, Any]
    reusable: bool
    invalidation_reason: str = ""


class RunStateStore:
    def __init__(self, artifact_root: Path, run_id: str) -> None:
        if not run_id or any(part in run_id for part in ("/", "\\", "..")):
            raise ValueError("run_id must be a safe local identifier")
        self.run_dir = artifact_root.resolve() / ".ftd" / "runs" / run_id
        self.path = self.run_dir / "run-state.json"

    def save(
        self,
        checkpoint: str,
        payload: dict[str, Any],
        source_hashes: dict[str, str],
    ) -> Path:
        if checkpoint not in CHECKPOINTS:
            raise ValueError(f"Unknown checkpoint {checkpoint}")
        _reject_sensitive(payload)
        document = {
            "internal_schema_version": "1",
            "checkpoint": checkpoint,
            "source_hashes": dict(sorted(source_hashes.items())),
            "payload": payload,
        }
        encoded = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(self.path)
        return self.path

    def load(self, current_source_hashes: dict[str, str]) -> CheckpointLoad | None:
        if not self.path.is_file():
            return None
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("source_hashes") != dict(sorted(current_source_hashes.items())):
            return CheckpointLoad(
                checkpoint=str(document.get("checkpoint", "")),
                payload={},
                reusable=False,
                invalidation_reason="SOURCE_HASH_CHANGED",
            )
        return CheckpointLoad(
            checkpoint=str(document["checkpoint"]),
            payload=document.get("payload", {}),
            reusable=True,
        )


def diagnostics_compatibility_self_check(
    stage_names: tuple[str, ...], aggregation_strategies: dict[str, str]
) -> dict[str, Any]:
    """Fail cheaply before expensive work when diagnostics contracts are invalid."""
    if len(stage_names) != len(set(stage_names)) or not stage_names:
        raise ValueError("Diagnostics stage names must be unique and non-empty")
    allowed = {"sum", "last", "first", "set", "max", "derived"}
    invalid = sorted(set(aggregation_strategies.values()) - allowed)
    if invalid:
        raise ValueError("Unsupported diagnostics aggregation strategies: " + ", ".join(invalid))
    probe = {"stages": list(stage_names), "strategies": aggregation_strategies}
    json.dumps(probe)
    return {
        "diagnostics_compatibility_checked": True,
        "diagnostics_stage_count": len(stage_names),
        "diagnostics_metric_count": len(aggregation_strategies),
    }
