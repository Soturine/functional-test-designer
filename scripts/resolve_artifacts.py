#!/usr/bin/env python3
"""Resolve a run's artifact destination without coupling it to skill or source roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


class ArtifactResolutionError(ValueError):
    """Raised when no safe artifact root can be selected."""


def same_path(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def resolve_artifact_paths(
    *,
    skill_root: Path,
    source_root: Path,
    explicit_artifact_root: Path | None = None,
    workspace_root: Path | None = None,
    allow_source_root: bool = False,
    explicit_root_source: str = "explicit_user_path",
) -> dict[str, str]:
    """Return exact output paths, preferring an explicit root over a safe workspace."""
    skill_root = skill_root.resolve()
    source_root = source_root.resolve()
    if explicit_artifact_root is not None:
        artifact_root = explicit_artifact_root.resolve()
        if explicit_root_source not in {"explicit_user_path", "prompted"}:
            raise ArtifactResolutionError("explicit root source must be explicit_user_path or prompted")
        source = explicit_root_source
    elif workspace_root is not None:
        artifact_root = workspace_root.resolve()
        source = "workspace"
    else:
        raise ArtifactResolutionError(
            "artifact root is ambiguous; obtain an explicit user path before writing"
        )

    if same_path(artifact_root, skill_root):
        raise ArtifactResolutionError("artifact root must not be the skill root")
    if same_path(artifact_root, source_root) and not allow_source_root:
        raise ArtifactResolutionError(
            "artifact root must not be the source root unless the user explicitly requests it"
        )

    return {
        "artifact_root": str(artifact_root),
        "output_path": str(artifact_root / "output"),
        "diagnostics_path": str(artifact_root / "diagnostics"),
        "artifact_root_source": source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--allow-source-root", action="store_true")
    parser.add_argument(
        "--artifact-root-source",
        choices=("explicit_user_path", "prompted"),
        default="explicit_user_path",
    )
    args = parser.parse_args()
    try:
        result = resolve_artifact_paths(
            skill_root=args.skill_root,
            source_root=args.source_root,
            explicit_artifact_root=args.artifact_root,
            workspace_root=args.workspace_root,
            allow_source_root=args.allow_source_root,
            explicit_root_source=args.artifact_root_source,
        )
    except (OSError, ArtifactResolutionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
