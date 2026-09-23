"""Shared helpers: drive synthetic domain packs through the official pipeline."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402

PACKS = ROOT / "benchmarks" / "domains"


def load_pack(name: str) -> dict[str, Any]:
    return json.loads((PACKS / f"{name}.json").read_text(encoding="utf-8"))


class PackRun:
    """A pack materialized in a temporary workspace, advanced stage by stage."""

    def __init__(self, name: str, mutate: Callable[[dict[str, Any]], None] | None = None):
        self.pack = copy.deepcopy(load_pack(name))
        if mutate:
            mutate(self.pack)
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.workspace = self.root / "workspace"
        for relative, source in self.pack["sources"].items():
            target = self.workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source["text"], encoding="utf-8")
        self.artifacts = self.root / "artifacts"
        self.run_dir: Path | None = None

    def start(self) -> dict[str, Any]:
        result = pipeline.start_run(
            workspace=self.workspace,
            sources_selected=[{"path": path, "role": item["role"]} for path, item in self.pack["sources"].items()],
            artifact_root=self.artifacts, run_id=self.pack["name"], locale=self.pack.get("locale"),
            request_text=self.pack.get("request", ""), reading={"strategy": "SEQUENTIAL"},
        )
        self.run_dir = Path(result["run_dir"])
        return result

    def submit(self, stage: str) -> dict[str, Any]:
        return pipeline.submit_stage(self.run_dir, stage, self.pack["stages"][stage])

    def through(self, last: str) -> None:
        self.start()
        for stage in ("design", "expansion", "procedures"):
            self.submit(stage)
            if stage == last:
                return

    def finalize(self, formats: tuple[str, ...] = ("HTML", "JSON", "MARKDOWN")) -> dict[str, Any]:
        self.through("procedures")
        return pipeline.finalize_run(self.run_dir, list(formats))

    def output(self, relative: str) -> Any:
        return json.loads((self.artifacts / "output" / relative).read_text(encoding="utf-8"))

    def close(self) -> None:
        self._temp.cleanup()


def by_key(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(item for item in items if item.get("key") == key)


def candidate(pack: dict[str, Any], dimension: str, key: str) -> dict[str, Any]:
    record = next(item for item in pack["stages"]["expansion"]["dimensions"] if item["dimension"] == dimension)
    return by_key(record["candidates"], key)


def procedure(pack: dict[str, Any], test: str) -> dict[str, Any]:
    return next(item for item in pack["stages"]["procedures"]["procedures"] if item["test"] == test)
