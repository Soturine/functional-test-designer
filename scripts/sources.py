#!/usr/bin/env python3
"""Selected-source handling: scope lock, one record per physical source, text reading,
authority identifier/title index, static Test Asset discovery and evidence references.

Scope rules: a selected file authorizes only that file; a selected directory is
recursive only below itself; nothing outside the selection is followed or read.
"""

from __future__ import annotations

import ast
import glob
import json
import re
from pathlib import Path
from typing import Any, Iterable

from common import detect_language, file_digest, normalize, normalize_identifier


IGNORED_DIRECTORIES = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "coverage", "__pycache__",
    ".cache", ".ftd",
}
TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sql", ".xml", ".csv", ".feature", ".java",
    ".cs", ".go", ".rb", ".php", ".kt", ".swift", ".sh", ".css", ".scss", ".vue",
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".gz", ".zip", ".exe", ".dll", ".pyc",
    ".woff", ".woff2", ".ttf", ".mp4", ".mp3",
}
ROLES = {
    "FUNCTIONAL_AUTHORITY": "NORMATIVE",
    "IMPLEMENTATION_EVIDENCE": "IMPLEMENTATION",
    "TECHNICAL_CONTEXT": "SUPPORTING",
    "TEST_ASSET": "QA_ASSET",
}
IDENTIFIER_KINDS = (
    (("RNF", "NFR"), "NON_FUNCTIONAL"),
    (("RF", "FR", "REQ", "UR", "US"), "FUNCTIONAL_REQUIREMENT"),
    (("RN", "BR", "RB"), "BUSINESS_RULE"),
    (("CU", "UC"), "USE_CASE"),
    (("FA", "AF"), "ALTERNATIVE_FLOW"),
    (("FE", "EF", "EX"), "EXCEPTION_FLOW"),
    (("CA", "AC"), "ACCEPTANCE_CRITERION"),
)
DEFAULT_IDENTIFIER = r"[A-Z]{2,5}[-_]?\d{1,4}(?:\.\d+)*"
_DEFINITION_PREFIX = r"^\s*(?:[#>*\-•●▪◦·]+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?"
_TITLE_SEPARATOR = r"\s*(?:[-–—:|)]\s*|\s+)"
_STRUCTURAL_ITEM = re.compile(r"^\s*(?:[•●▪◦·*\-]\s+|\d{1,2}[.)]\s+\S)")


class ScopeError(ValueError):
    """A selection cannot be resolved safely and uniquely."""


# --- scope --------------------------------------------------------------------------

def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _ignored(path: Path, workspace: Path) -> bool:
    try:
        parts = path.relative_to(workspace).parts
    except ValueError:
        return False
    return any(part in IGNORED_DIRECTORIES for part in parts)


def _safe(path: Path, boundary: Path, label: str) -> Path:
    resolved = path.resolve()
    if not _within(resolved, boundary):
        raise ScopeError(f"{label} escapes the allowed boundary: {path}")
    return resolved


def _expand(path: Path, workspace: Path) -> list[Path]:
    _safe(path, workspace, "selected path")
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    root = _safe(path, workspace, "selected directory")
    files = []
    for candidate in path.rglob("*"):
        if _ignored(candidate, workspace) or not candidate.is_file():
            continue
        resolved = _safe(candidate, workspace, "discovered path")
        if not _within(resolved, root):
            raise ScopeError(f"discovered path escapes selected directory: {candidate}")
        files.append(candidate)
    return files


def resolve_selected_scope(workspace: Path, selectors: list[str]) -> dict[str, list[str]]:
    """Resolve file, directory, unique basename and explicit-glob selectors inside workspace."""
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ScopeError(f"workspace is not a directory: {workspace}")
    if not selectors:
        raise ScopeError("at least one explicit source selector is required")
    roots: list[Path] = []
    files: list[Path] = []
    for raw in selectors:
        selector = str(raw).strip()
        if not selector:
            raise ScopeError("source selectors cannot be empty")
        requested = Path(selector) if Path(selector).is_absolute() else workspace / selector
        if glob.has_magic(selector):
            if Path(selector).is_absolute():
                raise ScopeError("absolute glob selectors are not supported")
            prefix = selector.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
            _safe(workspace / (prefix or "."), workspace, "glob selector")
            matches = [Path(value) for value in glob.glob(str(workspace / selector), recursive=True)]
            matches = [path for path in matches if not _ignored(path, workspace)]
        else:
            _safe(requested, workspace, "selected path")
            if requested.exists():
                matches = [requested]
            elif len(Path(selector).parts) == 1:
                matches = [
                    path for path in workspace.rglob(selector) if not _ignored(path, workspace)
                ]
                if len(matches) > 1:
                    options = ", ".join(sorted(path.relative_to(workspace).as_posix() for path in matches))
                    raise ScopeError(f"ambiguous source name {selector!r}; choose one of: {options}")
            else:
                matches = []
        if not matches:
            raise ScopeError(f"selected source was not found: {selector}")
        for match in matches:
            _safe(match, workspace, "selected path")
            roots.append(match)
            files.extend(_expand(match, workspace))
    unique_roots = sorted({path.resolve() for path in roots}, key=str)
    unique_files = sorted({path.resolve() for path in files}, key=str)
    return {
        "selected_scope_roots": [path.relative_to(workspace).as_posix() for path in unique_roots],
        "resolved_scope_paths": [path.relative_to(workspace).as_posix() for path in unique_files],
    }


def resolve_artifact_root(
    *, skill_root: Path, source_root: Path, artifact_root: Path | None,
    allow_source_root: bool = False,
) -> Path:
    """Require an explicit destination that is neither the skill root nor the source root."""
    if artifact_root is None:
        raise ScopeError("artifact root is ambiguous; obtain an explicit user path before writing")
    resolved = Path(artifact_root).resolve()
    if resolved == Path(skill_root).resolve():
        raise ScopeError("artifact root must not be the skill root")
    if resolved == Path(source_root).resolve() and not allow_source_root:
        raise ScopeError(
            "artifact root must not be the source root unless the user explicitly requests it"
        )
    return resolved


def selector_ownership(workspace: Path, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each user-declared selector with the physical files it owns. One physical file has
    exactly one owner: when selectors overlap, the most specific (deepest) root wins, then
    the first declared; a file is never owned — or read — twice."""
    workspace = Path(workspace).resolve()
    declared = []
    for order, item in enumerate(sources):
        selector = str(item.get("path", "")).strip()
        scope = resolve_selected_scope(workspace, [selector])
        depth = max((len(Path(root).parts) for root in scope["selected_scope_roots"]), default=0)
        declared.append({"order": order, "path": selector, "role": str(item.get("role", "")).strip().upper(),
                         "depth": depth, "candidates": scope["resolved_scope_paths"]})
    owner: dict[str, dict[str, Any]] = {}
    for entry in sorted(declared, key=lambda e: (-e["depth"], e["order"])):
        for path in entry["candidates"]:
            owner.setdefault(path, entry)
    return [{"path": e["path"], "role": e["role"], "order": e["order"],
             "files": sorted(p for p, o in owner.items() if o is e)} for e in declared]


def assign_roles(workspace: Path, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve each role-tagged selector; one physical file keeps exactly one role."""
    if not sources:
        raise ScopeError("at least one selected source with an explicit role is required")
    roles: dict[str, str] = {}
    selectors: list[str] = []
    for item in sources:
        selector = str(item.get("path", "")).strip()
        role = str(item.get("role", "")).strip().upper()
        if role not in ROLES:
            raise ScopeError(f"selected source {selector or '<missing>'} requires a role in {sorted(ROLES)}")
        selectors.append(selector)
        for path in resolve_selected_scope(workspace, [selector])["resolved_scope_paths"]:
            if roles.get(path, role) != role:
                raise ScopeError(f"{path} was selected with two roles: {roles[path]} and {role}")
            roles[path] = role
    scope = resolve_selected_scope(workspace, selectors)
    if not any(role == "FUNCTIONAL_AUTHORITY" for role in roles.values()):
        raise ScopeError("at least one selected source must be FUNCTIONAL_AUTHORITY")
    return {**scope, "roles": roles}


# --- reading ------------------------------------------------------------------------

def read_text(path: Path) -> tuple[str | None, str, str]:
    """Return (text, status, reason) without executing or importing anything."""
    suffix = path.suffix.casefold()
    if suffix in BINARY_EXTENSIONS:
        return None, "METADATA_ONLY", "binary media is not text evidence"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional dependency
        except ImportError:
            return None, "NEEDS_TRANSCRIPTION", "pypdf is not installed; supply a transcription"
        try:
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # malformed PDFs must be reported, not guessed
            return None, "FAILED", f"PDF text extraction failed: {type(exc).__name__}"
        if not text.strip():
            return None, "NEEDS_TRANSCRIPTION", "PDF has no extractable text layer"
        return text, "READ", "text extracted with pypdf"
    if suffix in TEXT_EXTENSIONS or not suffix:
        try:
            return path.read_text(encoding="utf-8"), "READ", "UTF-8 text"
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1"), "READ", "Latin-1 text"
        except OSError as exc:
            return None, "FAILED", f"read failed: {type(exc).__name__}"
    return None, "UNSUPPORTED", f"unsupported format {suffix}"


def _extract(path: Path, digest: str, text_cache: Path | None) -> tuple[str | None, str, str]:
    """Text extraction keyed by content digest: an unchanged source (e.g. a large PDF)
    is never re-extracted for a new run; a changed one always is."""
    cached = text_cache / f"{digest}.json" if text_cache else None
    if cached and cached.is_file():
        entry = json.loads(cached.read_text(encoding="utf-8"))
        return entry["text"], entry["status"], entry["reason"]
    text, status, reason = read_text(path)
    if cached and status == "READ":
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"text": text, "status": status, "reason": reason}), encoding="utf-8")
    return text, status, reason


def build_source_records(
    workspace: Path, roles: dict[str, str], transcriptions: dict[str, Path] | None = None,
    text_cache: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """One record per physical source plus the readable text of every source.

    A transcription supplied for a source the runtime cannot read is recorded as such;
    it never replaces a source the runtime could read itself.
    """
    transcriptions = transcriptions or {}
    records: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    for relative, role in sorted(roles.items()):
        path = (Path(workspace) / relative).resolve()
        digest = file_digest(path)
        text, status, reason = _extract(path, digest, text_cache)
        record: dict[str, Any] = {
            "path": relative, "role": role, "authority": ROLES[role], "status": status,
            "reason": reason, "content_digest": digest,
            "size_bytes": path.stat().st_size,
        }
        if text is None and relative in transcriptions:
            transcript = Path(transcriptions[relative])
            text = transcript.read_text(encoding="utf-8")
            record.update({
                "status": "TRANSCRIBED", "reason": "model-supplied transcription of unreadable source",
                "transcription_digest": file_digest(transcript),
            })
        if text is not None:
            texts[relative] = text
        records.append(record)
    unused = sorted(set(transcriptions) - set(roles))
    if unused:
        raise ScopeError("transcriptions reference unselected sources: " + ", ".join(unused))
    authority_unreadable = [
        item["path"] for item in records
        if item["role"] == "FUNCTIONAL_AUTHORITY" and item["status"] in {"NEEDS_TRANSCRIPTION", "FAILED"}
    ]
    if authority_unreadable:
        raise ScopeError(
            "Functional authority must be readable or transcribed before design: "
            + ", ".join(authority_unreadable)
        )
    if not any(item["role"] == "FUNCTIONAL_AUTHORITY" and item["path"] in texts for item in records):
        raise ScopeError("no selected Functional Authority source contains readable text")
    return records, texts


# --- authority identifiers ----------------------------------------------------------

def identifier_kind(identifier: str) -> str:
    prefix = re.match(r"[A-Za-z]+", identifier)
    head = prefix.group(0).upper() if prefix else ""
    for prefixes, kind in IDENTIFIER_KINDS:
        if head in prefixes:
            return kind
    return "GENERIC"


def _clean_title(raw: str) -> str:
    title = raw.strip().strip("*_#").strip()
    head, colon, _ = title.partition(":")
    if colon and len(head.split()) <= 10:
        title = head
    return re.sub(r"\s+", " ", title).strip(" .;-–—")


def extract_identifiers(text: str, path: str, pattern: str | None = None) -> list[dict[str, Any]]:
    """Index identifier definitions (`REQ-12 - Title`) with official titles and excerpts.

    Only a line that starts with the identifier followed by a title is a definition; an
    identifier merely mentioned inside prose (`... (REQ-4)`) is a reference, not a unit.
    """
    identifier = pattern or DEFAULT_IDENTIFIER
    definition = re.compile(
        _DEFINITION_PREFIX + rf"(?P<id>{identifier})(?![\w.]*\w)" + _TITLE_SEPARATOR
        + r"(?P<title>[^\W\d_][^\n]{1,200})$"
    )
    lines = text.splitlines()
    starts: list[tuple[int, str, str]] = []
    for number, line in enumerate(lines):
        match = definition.match(line)
        if match and not re.match(r"^[,;]", match.group("title")):
            starts.append((number, match.group("id"), _clean_title(match.group("title"))))
    by_key: dict[str, list[dict[str, Any]]] = {}
    for position, (number, raw_id, title) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else min(len(lines), number + 40)
        body = " ".join(value.strip() for value in lines[number:end] if value.strip())
        # A definition packed between other definitions (a table of contents) names the
        # title; the occurrence that stands alone carries the content.
        neighbours = [
            starts[index][0] for index in (position - 1, position + 1) if 0 <= index < len(starts)
        ]
        listing = any(
            not any(value.strip() for value in lines[min(other, number) + 1:max(other, number)])
            for other in neighbours
        )
        # Bullets and numbered items inside a definition are structural units the
        # design must reconcile; they are counted, never interpreted.
        items = sum(bool(_STRUCTURAL_ITEM.match(value)) for value in lines[number + 1:end])
        prose = " ".join(value.strip() for value in lines[number + 1:end] if value.strip())
        sentences = sum(len(part.split()) >= 6 for part in re.split(r"(?<=[.;!?])\s+", prose))
        items = max(items, sentences)
        by_key.setdefault(normalize_identifier(raw_id), []).append({
            "identifier": raw_id, "kind": identifier_kind(raw_id), "title": title,
            "source": path, "line": number + 1, "excerpt": body[:1200], "structural_items": items,
            "_listing": listing,
        })
    chosen = []
    for occurrences in by_key.values():
        entry = next((item for item in occurrences if not item["_listing"]), occurrences[0])
        entry["title"] = entry["title"] or occurrences[0]["title"]
        chosen.append({key: value for key, value in entry.items() if key != "_listing"})
    return sorted(chosen, key=lambda item: (item["source"], item["line"]))


def index_authority(
    records: list[dict[str, Any]], texts: dict[str, str], pattern: str | None = None,
) -> list[dict[str, Any]]:
    """Identifiers defined in functional authority; duplicates across files are errors."""
    entries: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["role"] != "FUNCTIONAL_AUTHORITY" or record["path"] not in texts:
            continue
        for entry in extract_identifiers(texts[record["path"]], record["path"], pattern):
            key = normalize_identifier(entry["identifier"])
            if key in entries and entries[key]["source"] != entry["source"]:
                raise ScopeError(
                    f"identifier {entry['identifier']} is defined in two authority sources: "
                    f"{entries[key]['source']} and {entry['source']}"
                )
            entries.setdefault(key, entry)
    return list(entries.values())


def infer_locale(explicit: str | None, authority_texts: Iterable[str], request_text: str = "") -> dict[str, str]:
    """Explicit language wins; then Functional Authority; then the user's request."""
    names = {"pt": "pt-BR", "en": "en", "es": "es"}
    if explicit:
        return {"output_locale": explicit, "locale_source": "EXPLICIT"}
    votes: dict[str, int] = {}
    for text in authority_texts:
        for paragraph in re.split(r"\n\s*\n|\n", text):
            language = detect_language(paragraph)
            if language:
                votes[language] = votes.get(language, 0) + 1
    if votes:
        best = max(votes.items(), key=lambda item: item[1])
        total = sum(votes.values())
        if best[1] / total >= 0.6:
            return {"output_locale": names[best[0]], "locale_source": "FUNCTIONAL_AUTHORITY"}
    language = detect_language(request_text)
    if language:
        return {"output_locale": names[language], "locale_source": "USER_REQUEST"}
    return {"output_locale": "en", "locale_source": "FALLBACK_AMBIGUOUS"}


# --- test assets --------------------------------------------------------------------

_TEST_NAME = re.compile(r"^test[_A-Z0-9]", re.IGNORECASE)
_JS_TEST = re.compile(r"""\b(?:it|test)\s*\(\s*(['"`])(?P<name>.+?)\1""")
_RUBY_TEST = re.compile(r"""^\s*(?:it|scenario|specify)\s+(['"])(?P<name>.+?)\1""")
_GO_TEST = re.compile(r"^func\s+(?P<name>Test\w*)\s*\(")
_GHERKIN = re.compile(r"^\s*Scenario(?: Outline| Template)?:\s*(?P<name>\S.*?)\s*$")
_ANNOTATION = re.compile(r"^\s*(?:@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b|\[(?:Test|Fact|Theory|TestMethod|TestCase)\b)")
_METHOD = re.compile(r"\b(?:fun|void|def|function|Task|async\s+Task)\s+(?P<name>\w+)\s*\(|\b(?P<bare>\w+)\s*\([^)]*\)\s*(?:\{|throws|=>)")
_PREFIXED_METHOD = re.compile(r"\bfunction\s+(?P<name>test\w+)\s*\(")
# Ecosystem naming conventions for test files, independent of any project vocabulary.
_TEST_FILE = re.compile(
    r"(?:^|/)test_[^/]+\.py$|_test\.(?:py|go)$|\.(?:test|spec)\.(?:[cm]?js|jsx|ts|tsx)$|"
    r"(?:Test|Tests|IT|Spec)\.(?:java|kt|cs|php|groovy|scala|swift)$|_spec\.rb$|\.feature$",
    re.IGNORECASE,
)
_TEST_DIRECTORY = re.compile(r"(?:^|/)(?:tests?|__tests__|specs?)/", re.IGNORECASE)
_CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".cs", ".php",
                    ".rb", ".feature", ".groovy", ".scala", ".swift"}


def is_test_file(path: str) -> bool:
    """A physical file that is an existing test by common ecosystem conventions (file
    name, or a code file below a conventional test directory). This is a facet of the
    file, never a role: it does not change the file's authority."""
    normalized = str(path).replace("\\", "/")
    if Path(normalized).suffix.lower() not in _CODE_EXTENSIONS:
        return False
    return bool(_TEST_FILE.search(normalized) or _TEST_DIRECTORY.search(normalized))


def discover_test_assets(text: str, source: str) -> list[dict[str, Any]]:
    """Statically list test behaviors; the inspected code is never imported or executed."""
    found: list[dict[str, Any]] = []

    def add(reference: str, line: int | None, docstring: str = "") -> None:
        found.append({"asset": f"{source}::{reference}", "source": source, "reference": reference,
                      "line": line, "docstring": docstring})

    suffix = Path(source).suffix.lower()
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            raise ScopeError(f"selected test asset {source} could not be parsed: {exc.msg}")

        def record(node: ast.AST, owner: str | None) -> None:
            name = getattr(node, "name")
            add(f"{owner}::{name}" if owner else name, getattr(node, "lineno", None),
                (ast.get_docstring(node) or "").strip()[:300])

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _TEST_NAME.match(node.name):
                record(node, None)
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _TEST_NAME.match(child.name):
                        record(child, node.name)
        return found
    lines = text.splitlines()
    annotated = False
    for number, line in enumerate(lines, 1):
        if suffix == ".go":
            match = _GO_TEST.search(line)
        elif suffix == ".feature":
            match = _GHERKIN.search(line)
        elif suffix == ".rb":
            match = _RUBY_TEST.search(line)
        elif suffix in {".java", ".kt", ".cs", ".php", ".groovy", ".scala", ".swift"}:
            annotation = _ANNOTATION.search(line)
            if annotation:
                annotated = True
                line = line[annotation.end():]
            method = _METHOD.search(line)
            match = None
            if method and (annotated or _TEST_NAME.match(method.group("name") or method.group("bare") or "")):
                name = method.group("name") or method.group("bare")
                add(name, number)
                annotated = False
            elif suffix == ".php":
                match = _PREFIXED_METHOD.search(line)
            if match is None:
                continue
        else:
            match = _JS_TEST.search(line)
        if match:
            add(match.group("name"), number)
    return found


def discover_all_test_assets(
    records: list[dict[str, Any]], texts: dict[str, str], warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Existing tests that challenge the suite: every file of an explicit TEST_ASSET
    selection, plus conventional test files found inside IMPLEMENTATION_EVIDENCE
    selections. The source keeps its role; `source_role` records it and existing tests
    are never authority. An implementation-side test file that cannot be parsed stays
    ordinary implementation evidence and is reported in `warnings`."""
    assets: list[dict[str, Any]] = []
    for record in records:
        if record["path"] not in texts:
            continue
        if record["role"] == "TEST_ASSET":
            found = discover_test_assets(texts[record["path"]], record["path"])
        elif record["role"] == "IMPLEMENTATION_EVIDENCE" and is_test_file(record["path"]):
            try:
                found = discover_test_assets(texts[record["path"]], record["path"])
            except ScopeError as exc:
                if warnings is not None:
                    warnings.append(f"TEST_ASSET_NOT_PARSED: {exc}")
                continue
        else:
            continue
        assets.extend({**item, "source_role": record["role"]} for item in found)
    return assets


# --- evidence references ------------------------------------------------------------

def walk_refs(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "source" in value and "reference" in value:
            yield value
        for child in value.values():
            yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def check_source_refs(
    workspace: Path, records: list[dict[str, Any]], texts: dict[str, str], documents: list[Any],
) -> tuple[list[str], int]:
    """Every evidence reference must point at a selected, existing source with valid lines."""
    known = {item["path"]: item for item in records}
    errors: list[str] = []
    checked = 0
    for document in documents:
        for ref in walk_refs(document):
            checked += 1
            source = str(ref.get("source", ""))
            if source not in known:
                errors.append(f"reference {source!r} is outside the selected scope")
                continue
            if not str(ref.get("reference", "")).strip():
                errors.append(f"reference to {source} has no locator")
            start, end = ref.get("line_start"), ref.get("line_end", ref.get("line_start"))
            if start is not None:
                total = len(texts.get(source, "").splitlines())
                if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= total):
                    errors.append(f"reference {source}:{start}-{end} is not a valid line range")
    return sorted(set(errors)), checked


def identifier_mentioned(identifier: str, texts: Iterable[str]) -> bool:
    key = normalize_identifier(identifier)
    pattern = re.compile(r"[A-Za-z]{2,5}[-_ ]?\d{1,4}(?:\.\d+)*")
    for text in texts:
        if any(normalize_identifier(match.group(0)) == key for match in pattern.finditer(text)):
            return True
    return False


def titles_match(left: str, right: str) -> bool:
    return normalize(left) == normalize(right)
