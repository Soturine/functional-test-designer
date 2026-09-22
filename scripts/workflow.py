#!/usr/bin/env python3
"""Shared intent dispatcher behind natural language and the optional ftd-* aliases.

ftd-gen starts the staged pipeline from selected sources; ftd-clarify ranks open
Questions; ftd-check audits a published suite read-only; ftd-render re-renders from
canonical state; ftd-mcp previews a Test Management export and writes nothing
without explicit approval.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pipeline  # noqa: E402
from integrations.azure_devops import build_preview, build_suite_mapping, write_fallback_export  # noqa: E402
from procedures import audit_case  # noqa: E402


INTENTS = ("ftd-gen", "ftd-clarify", "ftd-check", "ftd-render", "ftd-mcp")
# Pre-v2.3 callers sent the whole semantic answer up front; that entry point is gone.
LEGACY_REQUEST_FIELDS = {
    "source_items", "source_units", "opportunities", "risk_conditions", "use_case_flows",
    "test_asset_inventory", "scenario_profiles", "evidence_packs", "selected_evidence",
}
VALID_FOCI = {"everything", "procedure", "automation", "coverage", "outputs"}


def normalize_intent(request: str) -> str:
    text = " ".join(request.strip().casefold().split())
    alias = (text.split(maxsplit=1)[0] if text else "").lstrip("/$")
    if alias in INTENTS:
        return alias
    signals = (
        ("ftd-mcp", ("azure devops", "test plans", "preview before writing", "prepare the last suite")),
        ("ftd-render", ("render", "renderize", "last run as", "última execução como")),
        ("ftd-check", ("audit", "check", "audite", "verifique se", "executable by")),
        ("ftd-clarify", ("ask me", "important questions", "pergunte", "ambiguous", "ambígu")),
        ("ftd-gen", ("generate test cases", "generate tcs", "gere os test cases", "gere tcs", "gerar casos de teste")),
    )
    for intent, phrases in signals:
        if any(phrase in text for phrase in phrases):
            return intent
    raise ValueError("Could not determine a functional-test-designer intent from the request")


def dispatch_request(request_text: str, **request: Any) -> Any:
    """Natural language and command aliases enter the exact same dispatcher."""
    request.setdefault("request_text", request_text)
    return dispatch(normalize_intent(request_text), **request)


def dispatch(intent: str, **request: Any) -> Any:
    if intent not in INTENTS:
        raise ValueError(f"Unknown workflow intent: {intent}")
    if intent == "ftd-gen":
        legacy = sorted(LEGACY_REQUEST_FIELDS & set(request))
        if legacy:
            raise ValueError(
                "v2.3 no longer accepts a pre-authored semantic request (" + ", ".join(legacy)
                + "); start the pipeline from selected sources and submit stage outputs"
            )
        missing = [key for key in ("workspace", "sources", "artifact_root", "run_id") if key not in request]
        if missing:
            raise ValueError("ftd-gen requires selected sources: " + ", ".join(missing))
        return pipeline.start_run(
            workspace=request["workspace"], sources_selected=request["sources"],
            artifact_root=request["artifact_root"], run_id=request["run_id"],
            locale=request.get("locale"), request_text=request.get("request_text", ""),
            transcriptions=request.get("transcriptions"), id_pattern=request.get("id_pattern"),
        )
    if intent == "ftd-clarify":
        return rank_questions(request.get("questions", []), request.get("limit", 5))
    if intent == "ftd-check":
        return check_suite(request["cases"], focus=request.get("focus", "everything"))
    if intent == "ftd-render":
        return pipeline.render_run(request["run_dir"], request.get("formats"))
    suite_mapping = None
    if request.get("risk_suites") is not None or request.get("map_risk_suites"):
        suite_mapping = build_suite_mapping(
            request["cases"], requirement_suite=request["suite"], risk_suites=request.get("risk_suites"),
        )
    preview = build_preview(
        request["cases"], request.get("mapping", {}), project=request["project"], plan=request["plan"],
        suite=request["suite"], include_needs_review=request.get("include_needs_review", False),
        external_versions=request.get("external_versions"), suite_mapping=suite_mapping,
    )
    if not request.get("mcp_available", False):
        preview["fallback_exports"] = [str(path) for path in write_fallback_export(request["artifact_root"], preview)]
    return preview


def check_suite(cases: list[dict[str, Any]], *, focus: str = "everything") -> dict[str, Any]:
    """Audit without mutation, regeneration, splitting or source reads."""
    focus = focus.casefold().strip()
    if focus not in VALID_FOCI:
        raise ValueError(f"Unsupported check focus: {focus}")
    before = deepcopy(cases)
    findings = []
    for case in cases:
        reasons = audit_case(case)
        if focus == "automation" and case.get("automation_readiness") not in {None, "READY"}:
            reasons.append(f"AUTOMATION_{case['automation_readiness']}")
        if reasons and focus in {"everything", "procedure", "automation"}:
            findings.append({
                "test_case_id": case.get("id"), "reason_codes": reasons,
                "evidence": "Existing canonical Test Case fields",
                "recommended_next_action": "Clarify or enrich only the unsupported procedural details.",
            })
    if cases != before:
        raise AssertionError("Read-only suite audit mutated the canonical cases")
    return {"focus": focus, "findings": findings, "source_reads": 0, "suite_mutated": False}


IMPACT_ORDER = {
    "oracle": 0, "actor_permission": 1, "starting_state": 2, "trigger": 3,
    "input_partition": 4, "execution_boundary": 5, "side_effect": 6,
    "procedure": 7, "test_data": 8, "environment": 9,
    "observability": 10, "automation_feasibility": 11,
}
STOP_WORDS = {"stop", "done", "proceed", "skip"}


def rank_questions(questions: Iterable[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Return the highest-impact unique questions without inventing missing context."""
    unique: dict[str, dict[str, Any]] = {}
    for question in questions:
        key = str(question.get("id") or question.get("question", "")).strip()
        if key:
            unique.setdefault(key, dict(question))
    ranked = sorted(
        unique.values(),
        key=lambda item: (
            IMPACT_ORDER.get(str(item.get("category", "")).casefold(), 99),
            str(item.get("id", "")),
        ),
    )
    return ranked[: max(0, min(limit, 5))]


def record_answer(
    question: dict[str, Any], answer: str, *, authoritative_correction: bool = False
) -> dict[str, Any]:
    normalized = answer.strip()
    return {
        "question_id": question.get("id"),
        "question": question.get("question"),
        "answer": normalized,
        "affected_refs": list(question.get("affected_refs", [])),
        "source_role": "USER_CLARIFICATION",
        "authority_interpretation": (
            "AUTHORITATIVE_CORRECTION" if authoritative_correction else "SUPPLEMENTAL_EVIDENCE"
        ),
        "conflict_requires_review": bool(
            question.get("approved_authority_answer")
            and normalized != question.get("approved_authority_answer")
            and not authoritative_correction
        ),
    }


def should_stop(answer: str) -> bool:
    return answer.strip().casefold() in STOP_WORDS


def persist_clarifications(run_dir: Path, answers: list[dict[str, Any]]) -> Path:
    path = run_dir / "clarifications.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"answers": answers}, indent=2) + "\n", encoding="utf-8")
    return path


def privacy_safe_metrics(answers: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "clarifications_applied": len(answers),
        "clarification_conflicts": sum(bool(item.get("conflict_requires_review")) for item in answers),
    }
