#!/usr/bin/env python3
"""Resolve explicitly selected source paths without reading source content."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".cache",
}


class ScopeResolutionError(ValueError):
    """Raised when a requested scope cannot be resolved safely and uniquely."""


def relative_display(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def ignored(path: Path, workspace: Path) -> bool:
    try:
        parts = path.relative_to(workspace).parts
    except ValueError:
        return False
    return any(part in IGNORED_DIRECTORIES for part in parts)


def safe_path(path: Path, boundary: Path, label: str) -> Path:
    resolved = path.resolve()
    if not within(resolved, boundary):
        raise ScopeResolutionError(f"{label} escapes the allowed boundary: {path}")
    return resolved


def files_in_directory(directory: Path, workspace: Path) -> list[Path]:
    directory_real = safe_path(directory, workspace, "selected directory")
    files: list[Path] = []
    for candidate in directory.rglob("*"):
        if ignored(candidate, workspace) or not candidate.is_file():
            continue
        resolved = safe_path(candidate, workspace, "discovered path")
        if not within(resolved, directory_real):
            raise ScopeResolutionError(f"discovered path escapes selected directory: {candidate}")
        files.append(candidate)
    return files


def expand_match(path: Path, workspace: Path) -> list[Path]:
    safe_path(path, workspace, "selected path")
    if path.is_file():
        return [path]
    if path.is_dir():
        return files_in_directory(path, workspace)
    return []


def metadata_matches(workspace: Path, basename: str) -> list[Path]:
    matches: list[Path] = []
    for candidate in workspace.rglob(basename):
        if not ignored(candidate, workspace):
            matches.append(candidate)
    return matches


def resolve_selected_scope(workspace: Path, selectors: list[str]) -> dict[str, list[str]]:
    """Resolve file, directory, basename, and explicit-glob selectors inside workspace."""
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ScopeResolutionError(f"workspace is not a directory: {workspace}")
    if not selectors:
        raise ScopeResolutionError("at least one explicit source selector is required")

    roots: list[Path] = []
    files: list[Path] = []
    for raw in selectors:
        selector = raw.strip()
        if not selector:
            raise ScopeResolutionError("source selectors cannot be empty")
        has_glob = glob.has_magic(selector)
        requested = Path(selector) if Path(selector).is_absolute() else workspace / selector

        if has_glob:
            if Path(selector).is_absolute():
                raise ScopeResolutionError("absolute glob selectors are not supported")
            prefix = selector.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
            safe_path(workspace / (prefix or "."), workspace, "glob selector")
            matches = [Path(value) for value in glob.glob(str(workspace / selector), recursive=True)]
            matches = [path for path in matches if not ignored(path, workspace)]
        else:
            safe_path(requested, workspace, "selected path")
            if requested.exists():
                matches = [requested]
            elif len(Path(selector).parts) == 1:
                matches = metadata_matches(workspace, selector)
                if len(matches) > 1:
                    options = ", ".join(sorted(relative_display(path, workspace) for path in matches))
                    raise ScopeResolutionError(f"ambiguous source name {selector!r}; choose one of: {options}")
            else:
                matches = []

        if not matches:
            raise ScopeResolutionError(f"selected source was not found: {selector}")
        for match in matches:
            safe_path(match, workspace, "selected path")
            roots.append(match)
            files.extend(expand_match(match, workspace))

    unique_roots = sorted({path.resolve() for path in roots}, key=str)
    unique_files = sorted({path.resolve() for path in files}, key=str)
    return {
        "selected_scope_roots": [relative_display(path, workspace) for path in unique_roots],
        "resolved_scope_paths": [relative_display(path, workspace) for path in unique_files],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("selectors", nargs="+")
    args = parser.parse_args()
    try:
        result = resolve_selected_scope(args.workspace, args.selectors)
    except (OSError, ScopeResolutionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
