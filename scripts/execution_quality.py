#!/usr/bin/env python3
"""Derive non-destructive execution-step quality signals from materialized cases."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


ACTION_VERB = re.compile(
    r"\b(?:open|select|enter|scan|read|confirm|submit|consult|click|"
    r"abrir|selecionar|informar|ler|confirmar|enviar|consultar|clicar)\w*\b",
    re.IGNORECASE,
)
SEQUENCE_MARKER = re.compile(r"(?:,|;|\b(?:then|and then|depois|em seguida|e então)\b)", re.IGNORECASE)


def multi_action_step_warnings(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for case in cases:
        for step in case.get("steps", []):
            action = str(step.get("action", ""))
            if len(ACTION_VERB.findall(action)) >= 3 and len(SEQUENCE_MARKER.findall(action)) >= 2:
                warnings.append(
                    {
                        "code": "POSSIBLE_MULTI_ACTION_STEP",
                        "test_case_id": case.get("id"),
                        "step": step.get("step"),
                    }
                )
    return warnings


def step_distribution(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [len(case.get("steps", [])) for case in cases]
    histogram = Counter(counts)
    return {
        "step_count_histogram": {str(key): histogram[key] for key in sorted(histogram)},
        "multi_action_step_warnings": len(multi_action_step_warnings(cases)),
    }
