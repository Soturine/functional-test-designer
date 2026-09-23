#!/usr/bin/env python3
"""Shared intent dispatcher behind natural language and the optional ftd-* aliases.

ftd-gen starts the staged pipeline from selected sources; ftd-clarify ranks open
Questions; ftd-check audits a published suite read-only; ftd-render re-renders from
canonical state; ftd-mcp previews a Test Management export and writes nothing
without explicit approval.
"""

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pipeline  # noqa: E402
import challenge as challenge_stage  # noqa: E402
import azure_export  # noqa: E402
from integrations.azure_devops import build_preview, build_suite_mapping, write_fallback_export  # noqa: E402
from procedures import audit_case  # noqa: E402


INTENTS = ("ftd-gen", "ftd-clarify", "ftd-check", "ftd-render", "ftd-mcp", "ftd-challenge", "ftd-azure")
# Pre-v2.3 callers sent the whole semantic answer up front; that entry point is gone.
LEGACY_REQUEST_FIELDS = {
    "source_items", "source_units", "opportunities", "risk_conditions", "use_case_flows",
    "test_asset_inventory", "scenario_profiles", "evidence_packs", "selected_evidence",
}
VALID_FOCI = {"everything", "procedure", "automation", "coverage", "outputs"}


GENERATION_VERB = re.compile(
    r"(?:generate|create|design|gere|gerar|crie|criar|genera|generar).*"
    r"(?:test ?cases?|tcs|casos de (?:teste|prueba))"
)
# Ambiguous words like "physical device" or "real-world" also show up in ordinary
# generation requests ("generate test cases for this physical device"); a clear
# generation verb always wins over those. Challenge phrasing must unambiguously name
# challenging an already-generated/finalized suite, not merely mention a domain.
def normalize_intent(request: str) -> str:
    text = " ".join(request.strip().casefold().split())
    alias = (text.split(maxsplit=1)[0] if text else "").lstrip("/$")
    if alias in INTENTS:
        return alias
    if GENERATION_VERB.search(text):
        return "ftd-gen"
    # ftd-azure's phrases are specific enough (package/input/grouping language) that they
    # never collide with ftd-mcp's own narrower, backward-compatible phrasing below.
    signals = (
        ("ftd-challenge", (
            "challenge the finalized", "challenge the final", "challenge this finalized suite",
            "challenge this final suite", "challenge the suite", "challenge this suite",
            "post-suite challenge", "post suite challenge",
            "desafie a suíte finalizada", "desafie a suíte final", "desafie a suíte já gerada",
        )),
        ("ftd-azure", ("azure export package", "azure devops package", "azure package",
                       "prepare this run for azure", "prepare this finalized", "azure devops input",
                       "test plans input", "grouped by requirement")),
        ("ftd-mcp", ("azure devops", "test plans", "preview before writing",
                    "prepare the last suite", "mcp preview")),
        ("ftd-render", ("render", "renderize", "last run as", "última execução como")),
        ("ftd-check", ("audit", "check", "audite", "verifique se", "executable by")),
        ("ftd-clarify", ("ask me", "important questions", "pergunte", "ambiguous", "ambígu")),
        ("ftd-gen", ("generate test cases", "generate tcs", "gere os test cases", "gere tcs", "gerar casos de teste")),
    )
    for intent, phrases in signals:
        if any(phrase in text for phrase in phrases):
            return intent
    raise ValueError("Could not determine a functional-test-designer intent from the request")


FORMAT_WORDS = {"HTML": r"\bhtml\b", "JSON": r"\bjson\b", "MARKDOWN": r"\b(?:markdown|md)\b",
                "OPERATIONAL": r"\boperational\b|\bcat[aá]logo operacional\b"}
DIAGNOSTIC_WORDS = r"\bdiagnostics?\b|\bdiagn[oó]sticos?\b"


def requested_formats(text: str) -> tuple[list[str] | None, bool]:
    """Formats and the diagnostics option stated in a natural request, if any."""
    lowered = text.casefold()
    formats = [name for name, pattern in FORMAT_WORDS.items() if re.search(pattern, lowered)]
    return (formats or None), bool(re.search(DIAGNOSTIC_WORDS, lowered))


def dispatch_request(request_text: str, **request: Any) -> Any:
    """Natural language and command aliases enter the exact same dispatcher."""
    request.setdefault("request_text", request_text)
    formats, diagnostics = requested_formats(request_text)
    if formats and "formats" not in request:
        request["formats"] = formats
    if diagnostics and "diagnostics" not in request and "diagnostic" not in request:
        request["diagnostics"] = True
    return dispatch(normalize_intent(request_text), **request)


def selected_sources(request: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept every public way of naming the selection: role-tagged entries, or
    selectors plus a role per selector (the pre-v2.3 request shape)."""
    roles = {str(key): str(value) for key, value in (request.get("roles") or {}).items()}
    entries = []
    for item in request.get("sources") or []:
        if isinstance(item, dict):
            entries.append({"path": str(item.get("path", "")), "role": item.get("role") or roles.get(str(item.get("path")))})
        else:
            entries.append({"path": str(item), "role": roles.get(str(item))})
    known = {entry["path"] for entry in entries}
    for selector in request.get("selectors") or []:
        if str(selector) not in known:
            entries.append({"path": str(selector), "role": roles.get(str(selector))})
    missing = [entry["path"] for entry in entries if not entry["role"]]
    if missing:
        raise ValueError(
            "each selected source needs a role (FUNCTIONAL_AUTHORITY, IMPLEMENTATION_EVIDENCE, "
            "TECHNICAL_CONTEXT, TEST_ASSET): " + ", ".join(missing)
        )
    return entries


def _canonical(request: dict[str, Any]) -> dict[str, Any]:
    path = Path(request.get("canonical_path") or Path(request["run_dir"]) / "canonical-suite.json")
    return pipeline.read_canonical(path)


def _run_dir(request: dict[str, Any]) -> Path:
    if request.get("run_dir"):
        return Path(request["run_dir"])
    return Path(request["canonical_path"]).parent


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
        missing = [key for key in ("workspace", "artifact_root", "run_id") if key not in request]
        if missing or not (request.get("sources") or request.get("selectors")):
            raise ValueError("ftd-gen requires selected sources: " + ", ".join(missing or ["sources"]))
        return pipeline.start_run(
            workspace=request["workspace"], sources_selected=selected_sources(request),
            artifact_root=request["artifact_root"], run_id=request["run_id"],
            locale=request.get("locale"), request_text=request.get("request_text", ""),
            transcriptions=request.get("transcriptions"), id_pattern=request.get("id_pattern"),
            formats=request.get("formats"),
            diagnostics=bool(request.get("diagnostics", request.get("diagnostic", False))),
            source_order=request.get("source_order"), clarifications=request.get("clarifications"),
        )
    if intent == "ftd-clarify":
        questions = request.get("questions")
        if questions is None:
            questions = _canonical(request)["questions"]["questions"]
        return rank_questions(questions, request.get("limit", 5))
    if intent == "ftd-check":
        cases = request.get("cases")
        if cases is None:
            cases = _canonical(request)["cases"]
        return check_suite(cases, focus=request.get("focus", "everything"))
    if intent == "ftd-render":
        return pipeline.render_run(_run_dir(request), request.get("formats"))
    if intent == "ftd-challenge":
        if not request.get("challenge_id"):
            raise ValueError("ftd-challenge requires a challenge_id for this run")
        return challenge_stage.start_challenge(
            _run_dir(request), request["challenge_id"],
            seeds=[Path(p) for p in request.get("seeds", []) or []], focus=request.get("focus", ""),
        )
    if intent == "ftd-azure":
        run_dir = _run_dir(request)
        package = azure_export.build_export_package(
            run_dir, challenge_ids=request.get("challenge_ids"),
            requirement_mapping=request.get("requirement_mapping"),
        )
        if not request.get("project"):
            return package
        state = azure_export.load_integration_state(run_dir)
        preview = azure_export.preview_export(
            package, project=request["project"], plan=request["plan"], suite=request["suite"],
            mapping={"test_cases": state.get("test_cases", {})},
            include_needs_review=request.get("include_needs_review", True),
        )
        if not request.get("mcp_available", True):
            preview["fallback_exports"] = [str(p) for p in write_fallback_export(request.get("artifact_root", run_dir), preview)]
        return {"package": package, "preview": preview}
    cases = request.get("cases")
    if cases is None:
        cases = _canonical(request)["cases"]
    suite_mapping = None
    if request.get("risk_suites") is not None or request.get("map_risk_suites"):
        suite_mapping = build_suite_mapping(
            cases, requirement_suite=request["suite"], risk_suites=request.get("risk_suites"),
        )
    preview = build_preview(
        cases, request.get("mapping", {}), project=request["project"], plan=request["plan"],
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
