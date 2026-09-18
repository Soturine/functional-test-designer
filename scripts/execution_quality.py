#!/usr/bin/env python3
"""Derive non-destructive execution-step quality signals from materialized cases."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


ACTION_VERB = re.compile(
    r"\b(?:access|open|search|locate|select|enter|provide|scan|read|confirm|submit|"
    r"consult|click|verify|review|choose|cancel|finalize|save|filter|export|"
    r"acessar|abrir|pesquisar|localizar|selecionar|informar|fornecer|ler|confirmar|"
    r"enviar|consultar|clicar|verificar|revisar|escolher|cancelar|finalizar|salvar|"
    r"filtrar|exportar)\w*\b",
    re.IGNORECASE,
)
SEQUENCE_MARKER = re.compile(
    r"(?:,|;|(?:\s(?:>|→)\s)|\b(?:then|and then|next|after that|depois|e depois|em seguida|e então)\b)",
    re.IGNORECASE,
)
INDEPENDENT_VARIANTS = re.compile(
    r"\b(?:separately|valid and invalid|each variant|cada variante|válido e inválido|separadamente)\b",
    re.IGNORECASE,
)


def multi_action_step_warnings(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for case in cases:
        for step in case.get("steps", []):
            action = str(step.get("action", ""))
            verbs = ACTION_VERB.findall(action)
            markers = SEQUENCE_MARKER.findall(action)
            compressed_sequence = (
                (len(verbs) >= 4 and len(markers) >= 1)
                or (len(verbs) >= 3 and len(markers) >= 2)
            )
            if compressed_sequence or INDEPENDENT_VARIANTS.search(action):
                warnings.append(
                    {
                        "code": "POSSIBLE_MULTI_ACTION_STEP",
                        "test_case_id": case.get("id"),
                        "step": step.get("step"),
                    }
                )
    return warnings


def step_underspecification_warnings(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**warning, "code": "POSSIBLE_STEP_UNDERSPECIFICATION"}
        for warning in multi_action_step_warnings(cases)
    ]


def step_distribution(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [len(case.get("steps", [])) for case in cases]
    histogram = Counter(counts)
    return {
        "step_count_histogram": {str(key): histogram[key] for key in sorted(histogram)},
        "multi_action_step_warnings": len(multi_action_step_warnings(cases)),
        "possible_step_underspecification_warnings": len(
            step_underspecification_warnings(cases)
        ),
    }
