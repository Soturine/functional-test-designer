#!/usr/bin/env python3
"""Small run-local cache for selected-source evidence and reusable scenario-family packs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class EvidenceMap:
    def __init__(self, allowed_source_keys: set[str]) -> None:
        self._allowed_source_keys = set(allowed_source_keys)
        self._sources: dict[str, Any] = {}
        self._packs: dict[str, Any] = {}
        self.evidence_map_hits = 0
        self.evidence_map_misses = 0
        self.source_files_reopened = 0
        self.source_reread_reasons: list[str] = []
        self.tc_generation_reuse_hits = 0

    def source(
        self,
        key: str,
        loader: Callable[[], Any],
        *,
        reopen: bool = False,
        reread_reason: str | None = None,
    ) -> Any:
        if key not in self._allowed_source_keys:
            raise ValueError(f"Evidence source is outside the resolved selected scope: {key}")
        if key in self._sources and not reopen:
            self.evidence_map_hits += 1
            return self._sources[key]
        if key in self._sources:
            if not reread_reason or not reread_reason.strip():
                raise ValueError("A raw source reread requires an explicit reason")
            self.source_files_reopened += 1
            self.source_reread_reasons.append(reread_reason.strip())
        else:
            self.evidence_map_misses += 1
        self._sources[key] = loader()
        return self._sources[key]

    def pack(self, family_key: str, builder: Callable[[], Any]) -> Any:
        if family_key in self._packs:
            self.tc_generation_reuse_hits += 1
            return self._packs[family_key]
        self._packs[family_key] = builder()
        return self._packs[family_key]

    def metrics(self) -> dict[str, Any]:
        return {
            "evidence_map_hits": self.evidence_map_hits,
            "evidence_map_misses": self.evidence_map_misses,
            "source_files_opened_once": len(self._sources),
            "source_files_reopened": self.source_files_reopened,
            "source_reread_reasons": list(self.source_reread_reasons),
            "evidence_records_reused": self.evidence_map_hits,
            "tc_generation_reuse_hits": self.tc_generation_reuse_hits,
        }
