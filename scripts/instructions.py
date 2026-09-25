#!/usr/bin/env python3
"""The instructions file: the one user-authored input behind /ftd-gen and /ftd-chaos.

It is `instructions.md` or `instructions.txt` (plain Markdown/text, read as written);
`instructions.html` is accepted only as a converted form of the same content.

The file is human guidance, source-selection intent and exploration seeds. It is never
authority, never a DSL and has no fixed sections: the user may add, remove or rename
headings freely. Meaning is the host model's job. This module owns only the
deterministic shell around that interpretation:

- resolving *which* file is the input (explicit path > workspace docs > skill docs);
- reading its text as written (an HTML conversion is reduced to text, headings uninterpreted);
- validating the host's normalized request (the internal handoff, not a user burden);
- merging explicit CLI/user overrides > the instructions file > skill defaults, with
  provenance, so the run records who decided each setting.
"""

from __future__ import annotations

import hashlib
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import USER_POST_GENERATION_ACTIONS, normalize_post_generation

INPUT_NAMES = ("instructions.md", "instructions.txt", "instructions.html")  # preference order
INPUT_BASENAME = INPUT_NAMES[0]
SCHEMA_VERSION = "1"
ROLES = ("FUNCTIONAL_AUTHORITY", "IMPLEMENTATION_EVIDENCE", "TECHNICAL_CONTEXT", "TEST_ASSET")
OUTPUT_TOKENS = {"json": "JSON", "md": "MARKDOWN", "markdown": "MARKDOWN", "html": "HTML"}
DEFAULT_OUTPUT = ("JSON", "MARKDOWN", "HTML")
STRATEGIES = ("MULTI_AGENT_PER_SOURCE", "MULTI_AGENT_BATCHED", "SEQUENTIAL")
REQUEST_KEYS = {
    "schema_version", "input_file", "scope_root", "sources", "source_order", "output", "reading",
    "guidance", "seeds", "ambiguities", "transcriptions", "post_generation",
}

OUTPUT_KEYS = {"formats", "diagnostics", "locale", "output_dir"}
READING_KEYS = {"strategy", "worker_model", "concurrency"}


class InstructionsError(ValueError):
    """The input file could not be resolved, or the normalized request is invalid."""


# --- resolution -------------------------------------------------------------------------

def _single_in(directory: Path) -> Path | None:
    """The one instructions file in a directory; two different ones are ambiguous."""
    found = [directory / name for name in INPUT_NAMES if (directory / name).is_file()]
    if len(found) > 1:
        raise InstructionsError(
            f"{directory} contains several instructions files ({', '.join(p.name for p in found)}); "
            "pass --input-file with the one to use"
        )
    return found[0] if found else None


def resolve_input_file(explicit: str | Path | None, *, workspace: Path, skill_root: Path) -> Path:
    """Explicit file > explicit directory's instructions file > <workspace>/docs >
    <skill>/docs. Never a recursive search, never a silent substitute."""
    names = " / ".join(INPUT_NAMES[:2])
    if explicit is not None and str(explicit).strip():
        path = Path(explicit)
        if not path.is_absolute():
            path = Path(workspace) / path
        if path.is_dir():
            candidate = _single_in(path)
            if candidate is None:
                raise InstructionsError(f"{path} is a directory without {names}")
            return candidate.resolve()
        if path.name.casefold() not in INPUT_NAMES:
            raise InstructionsError(
                f"--input-file must point to a file named {names} (or a directory containing one); "
                f"got {path.name!r}. Rename your guidance file to instructions.md or instructions.txt."
            )
        if not path.is_file():
            raise InstructionsError(f"input file not found: {path}")
        return path.resolve()
    for directory in (Path(workspace) / "docs", Path(skill_root) / "docs"):
        candidate = _single_in(directory) if directory.is_dir() else None
        if candidate is not None:
            return candidate.resolve()
    raise InstructionsError(
        f"an instructions file is required: pass --input-file, or create {Path(workspace) / 'docs' / INPUT_BASENAME}"
    )


# --- text extraction (structure only, no meaning) ------------------------------------------

class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "section", "article", "br", "tr", "table", "ul", "ol", "pre", "blockquote",
             "header", "footer", "main", "details", "summary"}
    HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip = 0

    def _flush(self) -> None:
        text = " ".join("".join(self.current).split())
        if text:
            self.lines.append(text)
        self.current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "template"}:
            self.skip += 1
        elif tag in self.HEADINGS:
            self._flush()
            self.current.append("#" * self.HEADINGS[tag] + " ")
        elif tag == "li":
            self._flush()
            self.current.append("- ")
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"}:
            self.skip = max(0, self.skip - 1)
        elif tag in self.HEADINGS or tag == "li" or tag in self.BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.current.append(data)

    def text(self) -> str:
        self._flush()
        return "\n".join(self.lines) + ("\n" if self.lines else "")


def extract_text(html: str) -> str:
    """Readable text with headings/list items kept as plain markers. No heading is
    recognized, required or interpreted — any section name is as good as any other."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def load_input(path: Path) -> dict[str, Any]:
    """Markdown/text is read as written; an HTML conversion is reduced to its text."""
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    if Path(path).suffix.casefold() == ".html":
        text = extract_text(text)
    return {"path": str(Path(path).resolve()), "digest": hashlib.sha256(raw).hexdigest(), "text": text}


# --- output tokens -----------------------------------------------------------------------

def parse_output(value: Any) -> list[str] | None:
    """`json,md,html` (any case, any order) -> ["JSON", "MARKDOWN", "HTML"]; None when absent."""
    if value is None:
        return None
    tokens = value.split(",") if isinstance(value, str) else list(value)
    formats: list[str] = []
    for token in tokens:
        key = str(token).strip().casefold()
        if not key:
            continue
        canonical = OUTPUT_TOKENS.get(key) or (key.upper() if key.upper() in OUTPUT_TOKENS.values() else None)
        if canonical is None:
            raise InstructionsError(f"unsupported output {token!r}; use json, md/markdown or html")
        if canonical not in formats:
            formats.append(canonical)
    if not formats:
        raise InstructionsError("--output names no format; use json, md/markdown or html")
    return formats


# --- normalized request ------------------------------------------------------------------

def normalization_order(input_doc: dict[str, Any], explicit: dict[str, Any], *, command: str) -> dict[str, Any]:
    """What the host model receives to interpret the file semantically."""
    return {
        "phase": "NORMALIZE_INSTRUCTIONS",
        "command": command,
        "input_file": {"path": input_doc["path"], "digest": input_doc["digest"]},
        "instructions_text": input_doc["text"],
        "explicit_overrides": {k: v for k, v in explicit.items() if v not in (None, [], {})},
        "contract": {
            "schema_version": SCHEMA_VERSION,
            "keys": sorted(REQUEST_KEYS),
            "sources": "[{path, role (one of %s), purpose?}] — absolute paths, or relative to scope_root" % "/".join(ROLES),
            "source_order": "optional [[path, ...], ...] reading/reconciliation priority; never changes authority",
            "output": "{formats?, diagnostics?, locale?, output_dir?} — only what the file actually asks for",
            "reading": "{strategy? (%s), worker_model?, concurrency?} — only when the file states a preference" % "/".join(STRATEGIES),
            "guidance": "[text] — any other user guidance, in the user's words",
            "seeds": "[{text, section?}] — one entry per idea; section is the user's own heading, verbatim",
            "ambiguities": "[text] — what you could not resolve; ask the user when it blocks source roles",
            "post_generation": "optional [CHAOS | AZURE_LOCAL_EXPORT] — follow-up actions the user asks for after the "
                               "run, in any wording or heading ('depois da run: fazer chaos, converter azure', "
                               "'no final quero chaos + Azure local'). Any Azure wording means AZURE_LOCAL_EXPORT; "
                               "remote publication is never a post-generation action",
        },
        "rules": [
            "Interpret every section by meaning; headings are free-form and may be anything.",
            "Seeds and guidance provoke reasoning, never limit it, and are never FUNCTIONAL_AUTHORITY.",
            "Assign roles from the user's wording and the real files, not from extensions or path names.",
            "Do not widen the source universe beyond what the file (or the user) selects.",
            "Explicit overrides above win over anything the file says; do not copy file hints over them.",
        ],
        "next": f"Write the normalized request JSON and rerun `workflow.py {command} ... --normalized <file>`.",
    }


def validate_request(request: dict[str, Any], input_doc: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(request, dict):
        return ["normalized request must be a JSON object"]
    unknown = sorted(set(request) - REQUEST_KEYS)
    if unknown:
        errors.append(f"normalized request has unknown keys {unknown}; put free text under guidance")
    if input_doc is not None:
        declared = (request.get("input_file") or {}).get("digest")
        if declared != input_doc["digest"]:
            errors.append("normalized request was produced for a different revision of the instructions file "
                          "(input_file.digest mismatch); normalize the current file again")
    for index, source in enumerate(request.get("sources") or []):
        if not isinstance(source, dict) or not str(source.get("path", "")).strip():
            errors.append(f"sources[{index}] requires a path")
            continue
        if str(source.get("role", "")).upper() not in ROLES:
            errors.append(f"sources[{index}] ({source['path']}) requires a role in {list(ROLES)}")
        extra = sorted(set(source) - {"path", "role", "purpose"})
        if extra:
            errors.append(f"sources[{index}] has unknown fields {extra}")
    post = request.get("post_generation")
    if post is not None:
        values = [str(v).upper() for v in post] if isinstance(post, list) else None
        if values is None:
            errors.append("post_generation must be a list of actions")
        else:
            remote = [v for v in values if "PUBLISH" in v or "REMOTE" in v]
            if remote:
                errors.append(f"post_generation cannot contain {remote}: remote publication is never automatic; "
                              "/ftd-azure-publish runs only when the user explicitly asks for it")
            unknown = sorted(set(values) - set(USER_POST_GENERATION_ACTIONS) - set(remote))
            if unknown:
                errors.append(f"post_generation accepts only {list(USER_POST_GENERATION_ACTIONS)} (got {unknown}); "
                              "refreshing the publication is derived automatically after a chaos pass")
    output = request.get("output") or {}
    if not isinstance(output, dict) or set(output) - OUTPUT_KEYS:
        errors.append(f"output accepts only {sorted(OUTPUT_KEYS)}")
    elif output.get("formats") is not None:
        try:
            parse_output(output["formats"])
        except InstructionsError as exc:
            errors.append(f"output.formats: {exc}")
    reading = request.get("reading") or {}
    if not isinstance(reading, dict) or set(reading) - READING_KEYS:
        errors.append(f"reading accepts only {sorted(READING_KEYS)}")
    elif reading.get("strategy") not in (None, *STRATEGIES):
        errors.append(f"reading.strategy must be one of {list(STRATEGIES)}")
    for index, seed in enumerate(request.get("seeds") or []):
        if not isinstance(seed, dict) or not str(seed.get("text", "")).strip():
            errors.append(f"seeds[{index}] requires text")
        elif set(seed) - {"text", "section"}:
            errors.append(f"seeds[{index}] accepts only text and section")
    for key in ("guidance", "ambiguities"):
        if not all(isinstance(item, str) for item in request.get(key) or []):
            errors.append(f"{key} must be a list of strings")
    return errors


def _layer(explicit: Any, from_file: Any, default: Any) -> tuple[Any, str]:
    if explicit not in (None, [], ""):
        return explicit, "EXPLICIT"
    if from_file not in (None, [], ""):
        return from_file, "INSTRUCTIONS"
    return default, "DEFAULT"


def effective_request(
    request: dict[str, Any], explicit: dict[str, Any], *, default_output_dir: Path,
) -> dict[str, Any]:
    """Explicit current CLI/user request > instructions file > skill defaults, per setting."""
    output = request.get("output") or {}
    reading = request.get("reading") or {}
    provenance: dict[str, str] = {}
    formats, provenance["formats"] = _layer(parse_output(explicit.get("output")), parse_output(output.get("formats")),
                                            list(DEFAULT_OUTPUT))
    diagnostics, provenance["diagnostics"] = _layer(True if explicit.get("diagnostics") else None,
                                                    output.get("diagnostics"), False)
    locale, provenance["locale"] = _layer(explicit.get("locale"), output.get("locale"), None)
    output_dir, provenance["output_dir"] = _layer(explicit.get("output_dir"), output.get("output_dir"),
                                                  str(default_output_dir))
    effective_reading = {}
    for key in sorted(READING_KEYS):
        value, provenance[f"reading.{key}"] = _layer(explicit.get(f"reading_{key}"), reading.get(key), None)
        effective_reading[key] = value
    if explicit.get("post_generation") is not None:  # an explicit "none" ([]) still wins over the file
        after, provenance["post_generation"] = explicit["post_generation"], "EXPLICIT"
    else:
        after, provenance["post_generation"] = _layer(None, request.get("post_generation"), [])
    return {
        "formats": formats, "diagnostics": bool(diagnostics), "locale": locale,
        "output_dir": str(output_dir), "reading": effective_reading,
        "post_generation": normalize_post_generation(after), "provenance": provenance,
    }


def resolve_sources(request: dict[str, Any], input_path: Path | None) -> tuple[Path, list[dict[str, str]], list[list[str]]]:
    """Workspace plus workspace-relative role-tagged selectors. The instructions file itself
    can never be selected as a source: guidance is not evidence, let alone authority."""
    sources = request.get("sources") or []
    if not sources:
        raise InstructionsError("the normalized request selects no sources; the instructions file (or the user) "
                                "must name what to read")
    scope_root = request.get("scope_root")
    absolute = [Path(s["path"]) for s in sources if Path(s["path"]).is_absolute()]
    if scope_root:
        workspace = Path(scope_root).resolve()
    elif len(absolute) == len(sources):
        workspace = Path(os.path.commonpath([str(p.resolve()) for p in absolute]))
        if workspace.is_file():
            workspace = workspace.parent
    else:
        raise InstructionsError("relative source paths need scope_root in the normalized request")
    if input_path is not None:
        blocked = Path(input_path).resolve()
    selected, mapping = [], {}
    for source in sources:
        path = Path(source["path"])
        resolved = (path if path.is_absolute() else workspace / path).resolve()
        if input_path is not None and resolved == blocked:
            raise InstructionsError("the instructions file cannot select itself as a source; it is guidance, not evidence")
        try:
            relative = resolved.relative_to(workspace).as_posix() or "."
        except ValueError as exc:
            raise InstructionsError(f"{source['path']} is outside scope_root {workspace}") from exc
        mapping[str(source["path"])] = relative
        selected.append({"path": relative, "role": str(source["role"]).upper()})
    order = [[mapping.get(str(item), str(item)) for item in group] for group in request.get("source_order") or []]
    return workspace, selected, order


def guidance_items(request: dict[str, Any], input_name: str = INPUT_BASENAME) -> list[dict[str, Any]]:
    """Every meaningful guidance and seed item, stably anchored, that the canonical generation
    must account for with an explicit disposition (never necessarily a Test Case)."""
    guidance = [{"anchor": f"{input_name}#guidance-{n:03d}", "text": str(text).strip(), "section": None}
                for n, text in enumerate(request.get("guidance") or [], 1) if str(text).strip()]
    return guidance + seed_items(request, input_name)


def seed_items(request: dict[str, Any], input_name: str = INPUT_BASENAME) -> list[dict[str, Any]]:
    """Item-level, stably anchored seeds in the order the host listed them."""
    return [{"anchor": f"{input_name}#seed-{n:03d}", "text": str(seed["text"]).strip(),
             "section": seed.get("section")}
            for n, seed in enumerate(request.get("seeds") or [], 1)]
