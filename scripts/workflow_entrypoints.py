#!/usr/bin/env python3
"""Shared intent dispatcher used by every host-specific thin entrypoint."""

from __future__ import annotations

from typing import Any

from azure_devops_adapter import build_preview, write_fallback_export
from canonical_state import OutputSelection, render_selected_outputs
from clarification import rank_questions
from suite_check import check_suite
from generation_orchestrator import run_generation


INTENTS = ("ftd-gen", "ftd-clarify", "ftd-check", "ftd-render", "ftd-mcp")


def normalize_intent(request: str) -> str:
    """Normalize an optional command alias or ordinary request to one shared intent."""
    text = " ".join(request.strip().casefold().split())
    first = text.split(maxsplit=1)[0] if text else ""
    alias = first.lstrip("/$")
    if alias in INTENTS:
        return alias
    signals = (
        ("ftd-mcp", ("azure devops", "test plans", "preview before writing", "prepare the last suite")),
        ("ftd-render", ("render", "renderize", "last run as", "última execução como")),
        ("ftd-check", ("audit", "check", "audite", "verifique se", "executable by")),
        ("ftd-clarify", ("ask me", "important questions", "pergunte", "ambiguous", "ambígu")),
        ("ftd-gen", ("generate test cases", "generate tcs", "gere os test cases", "gere tcs")),
    )
    for intent, phrases in signals:
        if any(phrase in text for phrase in phrases):
            return intent
    raise ValueError("Could not determine a functional-test-designer intent from the request")


def dispatch_request(request_text: str, **request: Any) -> Any:
    """Natural language and command aliases enter the exact same dispatcher."""
    return dispatch(normalize_intent(request_text), **request)


def dispatch(intent: str, **request: Any) -> Any:
    if intent not in INTENTS:
        raise ValueError(f"Unknown workflow intent: {intent}")
    if intent == "ftd-gen":
        return run_generation(request)
    if intent == "ftd-clarify":
        return rank_questions(request.get("questions", []), request.get("limit", 5))
    if intent == "ftd-check":
        return check_suite(
            request["cases"], focus=request.get("focus", "everything"),
            cohesion_decisions=request.get("cohesion_decisions"),
        )
    if intent == "ftd-render":
        selection = OutputSelection.normalize(request.get("formats"))
        return render_selected_outputs(request["canonical_path"], request["artifact_root"], selection)
    preview = build_preview(
        request["cases"], request.get("mapping", {}), project=request["project"],
        plan=request["plan"], suite=request["suite"],
        include_needs_review=request.get("include_needs_review", False),
        external_versions=request.get("external_versions"),
    )
    if not request.get("mcp_available", False):
        preview["fallback_exports"] = [
            str(path) for path in write_fallback_export(request["artifact_root"], preview)
        ]
    return preview
