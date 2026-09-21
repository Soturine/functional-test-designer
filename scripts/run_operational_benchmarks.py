#!/usr/bin/env python3
"""Execute synthetic benchmark packs through the enforced shared generation path.

The packs are deliberately messier than the unit fixtures: compound acceptance
bullets, alternative flows, a divergence, an ambiguous oracle, existing tests and
an operator-error path. Their expectations are semantic invariants and
dispositions, not a memorized Test Case count.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from generation_orchestrator import run_generation


PACK_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "operational-workflows"


def load_pack(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text(encoding="utf-8"))
    for field in ("id", "title", "files", "request", "expected_invariants"):
        if field not in pack:
            raise ValueError(f"Benchmark pack {path.name} is missing {field}")
    # Packs created before the v2.2 schema remain explicit compatibility fixtures.
    pack["request"].setdefault("schema_version", "1.2")
    return pack


def available_packs() -> list[Path]:
    return sorted(PACK_ROOT.glob("*.json"))


def materialize(pack: dict[str, Any], workspace: Path) -> None:
    for relative, content in pack["files"].items():
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def run_pack(pack: dict[str, Any], workspace: Path, artifact_root: Path) -> dict[str, Any]:
    """Materialize the synthetic sources and run the pack through the real gates."""
    materialize(pack, workspace)
    request = {
        **pack["request"],
        "workspace": workspace,
        "artifact_root": artifact_root,
        "run_id": pack["request"].get("run_id", f"benchmark-{pack['id']}"),
    }
    return run_generation(request)


def evaluate(pack: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Compare observed semantics with the pack's invariants and report violations."""
    diagnostics = json.loads(Path(result["diagnostics"]).read_text(encoding="utf-8"))
    observed: dict[str, Any] = {
        **diagnostics,
        "test_cases": len(result["cases"]),
        "coverage_points": len(result["chain"]["coverage_points"]),
        "normative_clauses": len(result["chain"]["normative_clauses"]),
    }
    violations: list[str] = []
    for name, expected in pack["expected_invariants"].items():
        metric = name.removesuffix("_min").removesuffix("_max").removesuffix("_exact")
        if metric not in observed:
            violations.append(f"{pack['id']}: metric {metric} was never reported")
            continue
        value = observed[metric]
        if name.endswith("_min") and value < expected:
            violations.append(f"{pack['id']}: {metric} is {value}, expected at least {expected}")
        elif name.endswith("_max") and value > expected:
            violations.append(f"{pack['id']}: {metric} is {value}, expected at most {expected}")
        elif name.endswith("_exact") and value != expected:
            violations.append(f"{pack['id']}: {metric} is {value}, expected exactly {expected}")
    return {"pack": pack["id"], "observed": observed, "violations": violations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--pack", type=Path, action="append")
    args = parser.parse_args()
    packs = args.pack or available_packs()
    failures = 0
    for path in packs:
        pack = load_pack(path)
        root = args.workspace / pack["id"]
        root.mkdir(parents=True, exist_ok=True)
        report = evaluate(pack, run_pack(pack, root, root / "artifacts"))
        failures += bool(report["violations"])
        print(json.dumps({"pack": report["pack"], "violations": report["violations"]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
