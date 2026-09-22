#!/usr/bin/env python3
"""Small shared helpers: JSON I/O, digests, text normalization, similarity and language."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "2.3.0"
GENERATOR = f"functional-test-designer/{VERSION}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Write UTF-8 JSON atomically so an interrupted run never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize(value: Any) -> str:
    """Casefolded, accent-free, whitespace-collapsed text used for comparisons."""
    text = strip_accents(unicodedata.normalize("NFKC", str(value or ""))).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "")).upper()


# Function words only: they signal language and carry no domain meaning.
_PT = {
    "de", "da", "do", "das", "dos", "que", "nao", "para", "com", "uma", "um", "os", "as",
    "no", "na", "nos", "nas", "ao", "aos", "a", "e", "o", "sao", "esta", "estao", "pelo",
    "pela", "pelos", "pelas", "deve", "devem", "sem", "seu", "sua", "seus", "suas", "ou",
    "quando", "entao", "tambem", "ja", "foi", "ser", "ter", "isso", "este", "essa", "esse",
    "apos", "ate", "mas", "como", "sobre", "entre", "cada", "em", "se", "ainda", "outro",
    "outra", "mesmo", "mesma", "pode", "podem", "nenhum", "nenhuma", "todos", "todas",
}
_EN = {
    "the", "and", "of", "to", "is", "are", "be", "with", "for", "on", "in", "that", "this",
    "it", "an", "a", "as", "by", "from", "at", "or", "not", "when", "then", "should", "must",
    "after", "before", "into", "its", "was", "were", "has", "have", "which", "each", "without",
    "only", "no", "does", "do", "other", "same", "can", "all", "any", "been", "their", "there",
}
_ES = {
    "el", "la", "los", "las", "del", "que", "y", "para", "con", "una", "un", "por", "es",
    "son", "esta", "debe", "deben", "cuando", "sin", "su", "sus", "al", "se", "lo", "como",
    "pero", "tambien", "ya", "fue", "ser", "este", "ese", "esa", "despues", "hasta", "otro",
    "otra", "mismo", "misma", "puede", "pueden", "ningun", "ninguna", "todos", "todas",
}
# Words shared by two languages do not discriminate between them.
STOPWORDS = {"pt": _PT, "en": _EN, "es": _ES}
_DISCRIMINATIVE = {
    language: words - set().union(*(other for key, other in STOPWORDS.items() if key != language))
    for language, words in STOPWORDS.items()
}
_TECHNICAL = re.compile(
    r"`[^`]*`|\"[^\"]*\"|“[^”]*”|'[^']*'|‘[^’]*’|https?://\S+|\S+/\S+|"
    r"\b\w*_\w*\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][A-Z0-9]{1,}\b|\b\w*\d\w*\b"
)


def detect_language(text: Any) -> str | None:
    """Return 'pt', 'en', 'es' when function words make the language clear, else None.

    Quoted labels, code symbols, identifiers, constants and paths are removed first:
    technical identifiers keep their original spelling and never count as language.
    """
    cleaned = _TECHNICAL.sub(" ", str(text or ""))
    words = normalize(cleaned).split()
    scores = {
        language: sum(word in vocabulary for word in words)
        for language, vocabulary in _DISCRIMINATIVE.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    second = ranked[1][1]
    if best_score >= 2 and best_score > 2 * second:
        return best
    return None


def locale_language(locale: str) -> str:
    return str(locale or "").split("-", 1)[0].casefold()


def _stem(word: str) -> str:
    return word[:5]


def content_tokens(text: Any) -> set[str]:
    """Meaningful stemmed tokens; function words of every supported language are removed."""
    stop = set().union(*STOPWORDS.values())
    return {
        _stem(word) for word in normalize(text).split()
        if len(word) >= 3 and word not in stop and not word.isdigit()
    }


def similarity(left: Any, right: Any) -> float:
    """Containment similarity: shared meaningful tokens over the smaller token set."""
    a, b = content_tokens(left), content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


class StageError(ValueError):
    """A stage payload violates a framework invariant; the message lists every problem."""

    def __init__(self, stage: str, errors: list[str]):
        self.stage = stage
        self.errors = list(errors)
        preview = "\n- ".join(self.errors[:60])
        more = f"\n- ... {len(self.errors) - 60} more" if len(self.errors) > 60 else ""
        super().__init__(f"{stage} rejected ({len(self.errors)} problem(s)):\n- {preview}{more}")


def raise_if(stage: str, errors: list[str]) -> None:
    if errors:
        raise StageError(stage, errors)
