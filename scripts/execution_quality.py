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
    r"\b(?:separately|execute separately|valid and invalid|valid, invalid|invalid and unknown|"
    r"each variant|desktop,? tablet|tablet and handheld|completion,? reversal|reversal and cancellation|"
    r"cada variante|válido e inválido|separadamente|conclusão,? reversão|reversão e cancelamento)\b",
    re.IGNORECASE,
)
PATH_COMPRESSION = re.compile(
    r"\b(?:perform|execute|complete|validate|process|run|carry out|"
    r"realizar|executar|completar|validar|processar)\b[^.]{0,80}\b"
    r"(?:flow|process|operation|scenario|workflow|fluxo|processo|opera[cç][aã]o|cen[aá]rio)\b|"
    r"\b(?:both platforms|other portal|ambas as plataformas|outro portal)\b",
    re.IGNORECASE,
)
GENERIC_SETUP = re.compile(
    r"\b(?:open the record and confirm the initial state|surface and test record are displayed|"
    r"observe the result|abrir o registro e confirmar o estado inicial|observar o resultado)\b",
    re.IGNORECASE,
)


def _normalized_template(value: Any) -> str:
    text = re.sub(r"\b[A-Z][A-Z0-9_-]{2,}\b", "<id>", str(value))
    text = re.sub(r"\b\d+\b", "<n>", text)
    return " ".join(text.casefold().split())


def procedure_template_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure repeated/generic procedural templates without forcing artificial steps."""
    actions = [str(step.get("action", "")) for case in cases for step in case.get("steps", [])]
    expected = [
        str(step.get("expected_result", ""))
        for case in cases for step in case.get("steps", [])
        if step.get("expected_result") is not None
    ]
    action_templates = Counter(_normalized_template(value) for value in actions)
    expected_templates = Counter(_normalized_template(value) for value in expected)
    repeated_actions = sum(count for count in action_templates.values() if count > 1)
    repeated_expected = sum(count for count in expected_templates.values() if count > 1)
    generic_setup = sum(bool(GENERIC_SETUP.search(value)) for value in [*actions, *expected])
    claim_oracles = {
        _normalized_template(case.get("objective", "")) for case in cases
    }
    copied = sum(_normalized_template(value) in claim_oracles for value in expected)
    return {
        "unique_action_ratio": round(len(action_templates) / len(actions), 4) if actions else 0.0,
        "unique_expected_result_ratio": round(len(expected_templates) / len(expected), 4) if expected else 0.0,
        "repeated_action_template_ratio": round(repeated_actions / len(actions), 4) if actions else 0.0,
        "repeated_expected_template_ratio": round(repeated_expected / len(expected), 4) if expected else 0.0,
        "generic_setup_step_count": generic_setup,
        "claim_copied_verbatim_as_oracle_count": copied,
    }


def hidden_subtest_signals(action: str) -> list[str]:
    """Detect independent executions compressed into one procedural action."""
    signals = []
    if INDEPENDENT_VARIANTS.search(action):
        signals.append("INDEPENDENT_VARIANTS_IN_ONE_ACTION")
    independent_verbs = re.findall(
        r"\b(?:complete|reverse|cancel|finalize|approve|reject|"
        r"concluir|reverter|cancelar|finalizar|aprovar|rejeitar)\w*\b",
        action,
        re.IGNORECASE,
    )
    if len({verb.casefold() for verb in independent_verbs}) >= 2:
        signals.append("MULTIPLE_INDEPENDENT_TRIGGERS")
    return signals


def hidden_subtest_warnings(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for case in cases:
        for step in case.get("steps", []):
            signals = hidden_subtest_signals(str(step.get("action", "")))
            if signals:
                warnings.append(
                    {
                        "code": "HIDDEN_SUBTEST",
                        "test_case_id": case.get("id"),
                        "step": step.get("step"),
                        "signals": signals,
                    }
                )
    return warnings


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
            if compressed_sequence or hidden_subtest_signals(action):
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


def path_compression_warnings(
    cases: list[dict[str, Any]], known_path_lengths: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    """Flag objective-like actions only when selected evidence has a richer path."""
    known_path_lengths = known_path_lengths or {}
    warnings = []
    for case in cases:
        case_id = str(case.get("id", ""))
        steps = case.get("steps", [])
        if known_path_lengths.get(case_id, 0) < 2:
            continue
        for step in steps:
            action = str(step.get("action", ""))
            if PATH_COMPRESSION.search(action) or (
                len(steps) == 1 and len(ACTION_VERB.findall(action)) >= 2
            ):
                warnings.append({
                    "code": "PATH_COMPRESSION", "test_case_id": case_id,
                    "step": step.get("step"), "known_path_actions": known_path_lengths[case_id],
                })
    return warnings


def step_distribution(
    cases: list[dict[str, Any]], known_path_lengths: dict[str, int] | None = None
) -> dict[str, Any]:
    counts = [len(case.get("steps", [])) for case in cases]
    histogram = Counter(counts)
    return {
        "step_count_histogram": {str(key): histogram[key] for key in sorted(histogram)},
        "multi_action_step_warnings": len(multi_action_step_warnings(cases)),
        "possible_step_underspecification_warnings": len(
            step_underspecification_warnings(cases)
        ),
        "hidden_subtest_warnings": len(hidden_subtest_warnings(cases)),
        "one_step_cases": sum(count == 1 for count in counts),
        "legitimate_one_step_cases": sum(
            count == 1 and (known_path_lengths or {}).get(str(case.get("id")), 1) <= 1
            for case, count in zip(cases, counts)
        ),
        "path_compression_warnings": len(path_compression_warnings(cases, known_path_lengths)),
    }
