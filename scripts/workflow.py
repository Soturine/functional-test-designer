#!/usr/bin/env python3
"""Exact-intent dispatcher behind the public ftd-* commands and natural language.

Public commands: /ftd-gen, /ftd-chaos, /ftd-azure, /ftd-azure-publish, /ftd-clarify, /ftd-check, /ftd-render.
/ftd-azure is local only; /ftd-azure-publish is the only command that can write to Azure DevOps,
and only after an explicit target, a prepared plan and explicit approval.

Natural language is understood by the host model, not here: the host resolves what the
user means in context (a new generation vs. challenging an already-finalized suite vs.
preparing Azure input) and hands off `resolved_intent`. This module only recognizes
exact aliases, validates arguments deterministically and dispatches. It deliberately
holds no phrase catalog — it never tries to enumerate human language.

CLI (the explicit form of the three primary commands):

  workflow.py gen   [--input-file PATH] [--output json,md,html] [--diagnostics] [--after chaos,azure|none]
                    [--output-dir DIR] [--locale L] [--normalized FILE] [--run-id ID]
  workflow.py chaos --run RUN [--input-file PATH] [--output json,md,html]
                    [--chaos-id ID] [--normalized FILE] [--focus TEXT]
  workflow.py azure --run RUN [--output json] [--chaos-id ID ...]
  workflow.py azure-publish --prepare --run RUN --organization URL --project P --plan PLAN [--auth ...]
  workflow.py azure-publish --apply PLAN.json [--approved] [--auth ...]

`gen`/`chaos` with an instructions file (.md/.txt) are two-phase: without --normalized they print the
normalization order (the file's text plus the handoff contract) for the host model;
with --normalized they validate the host's request and start the run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pipeline  # noqa: E402
import challenge as challenge_stage  # noqa: E402
import azure_export  # noqa: E402
import azure_publish  # noqa: E402
import instructions  # noqa: E402
from common import normalize_post_generation, read_json  # noqa: E402
from procedures import audit_case  # noqa: E402


INTENTS = ("ftd-gen", "ftd-chaos", "ftd-azure", "ftd-azure-publish", "ftd-clarify", "ftd-check", "ftd-render")
# Retired public names: they only explain where the behavior moved.
RETIRED = {
    "ftd-challenge": "ftd-challenge was renamed: use /ftd-chaos --run <run> [--input-file instructions.md]",
    "ftd-mcp": "ftd-mcp was replaced: use /ftd-azure --run <run> --output json (local JSON; no live Azure)",
}
# Pre-v2.3 callers sent the whole semantic answer up front; that entry point is gone.
LEGACY_REQUEST_FIELDS = {
    "source_items", "source_units", "opportunities", "risk_conditions", "use_case_flows",
    "test_asset_inventory", "scenario_profiles", "evidence_packs", "selected_evidence",
}
VALID_FOCI = {"everything", "procedure", "automation", "coverage", "outputs"}


# `--after` tokens: a command-line contract (the instructions file is read semantically by
# the host). Remote publication is deliberately absent: it is never a follow-up action.
AFTER_TOKENS = {"chaos": "CHAOS", "azure": "AZURE_LOCAL_EXPORT"}


def parse_after(value: Any) -> list[str] | None:
    """`--after chaos,azure` / `--after none`; None when the option was not given."""
    if value in (None, ""):
        return None
    tokens = [t.strip().casefold() for t in (value.split(",") if isinstance(value, str) else value) if str(t).strip()]
    if tokens == ["none"]:
        return []
    unknown = [t for t in tokens if t not in AFTER_TOKENS]
    if unknown:
        raise ValueError(f"--after accepts chaos, azure or none (got {unknown}); remote publication is never "
                         "automatic — use /ftd-azure-publish explicitly")
    return normalize_post_generation(AFTER_TOKENS[t] for t in tokens)


class IntentUnresolved(ValueError):
    """No exact alias and no host-resolved intent: the host model must decide."""


def exact_alias(request_text: str) -> str | None:
    """`/ftd-gen ...`, `$ftd-gen ...` or `ftd-gen ...` — only the leading token, exactly."""
    token = request_text.strip().split(maxsplit=1)[0] if request_text.strip() else ""
    alias = token.lstrip("/$").casefold()
    if alias in RETIRED:
        raise ValueError(RETIRED[alias])
    return alias if alias in INTENTS else None


def resolve_intent(request_text: str = "", resolved_intent: str | None = None) -> str:
    """An exact alias always wins; otherwise the host's semantic decision is validated.
    Nothing here interprets free text."""
    alias = exact_alias(request_text)
    if alias:
        return alias
    if resolved_intent:
        intent = str(resolved_intent).strip().lstrip("/$").casefold()
        if intent in RETIRED:
            raise ValueError(RETIRED[intent])
        if intent not in INTENTS:
            raise ValueError(f"resolved_intent {resolved_intent!r} is not one of {list(INTENTS)}")
        return intent
    raise IntentUnresolved(
        "no exact ftd-* alias in the request; the host model must resolve the intent semantically "
        f"(from the request and the current run state) and pass resolved_intent, one of {list(INTENTS)}"
    )


def dispatch_request(request_text: str, resolved_intent: str | None = None, **request: Any) -> Any:
    """Natural language and command aliases enter the exact same dispatcher. Formats come
    from explicit arguments (`output`/`formats`), never from sniffing the free text."""
    request.setdefault("request_text", request_text)
    return dispatch(resolve_intent(request_text, resolved_intent), **request)


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
    path = Path(request["canonical_path"]) if request.get("canonical_path") else _run_dir(request) / "canonical-suite.json"
    return pipeline.read_canonical(path)


def _run_dir(request: dict[str, Any]) -> Path:
    """explicit run (run_dir or canonical_path) > the current validated run > a clear error."""
    explicit = request.get("run_dir") or (Path(request["canonical_path"]).parent if request.get("canonical_path") else None)
    return pipeline.resolve_run(explicit, request.get("output_dir") or request.get("artifact_root"))


def _formats(request: dict[str, Any]) -> list[str] | None:
    if request.get("output") is not None:
        return instructions.parse_output(request["output"])
    return request.get("formats")


# --- /ftd-gen ---------------------------------------------------------------------------

def generate(
    *, input_file: str | Path | None = None, normalized: dict[str, Any] | None = None,
    explicit: dict[str, Any] | None = None, workspace: Path | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    """/ftd-gen from the instructions file (instructions.md/.txt). Without `normalized`, return the normalization
    order for the host model. With it, validate, merge precedence (explicit > file >
    defaults), start the canonical pipeline and persist normalized-request.json."""
    workspace = Path(workspace or Path.cwd()).resolve()
    explicit = dict(explicit or {})
    path = instructions.resolve_input_file(input_file, workspace=workspace, skill_root=SKILL_ROOT)
    document = instructions.load_input(path)
    if normalized is None:
        return instructions.normalization_order(document, explicit, command="gen")
    errors = instructions.validate_request(normalized, document)
    if errors:
        raise instructions.InstructionsError("; ".join(errors))
    effective = instructions.effective_request(normalized, explicit, default_output_dir=workspace / "ftd-output")
    scope_root, sources, order = instructions.resolve_sources(normalized, path)
    record = {
        "schema_version": instructions.SCHEMA_VERSION, "command": "ftd-gen",
        "input_file": {"name": path.name, "digest": document["digest"]},
        "sources": sources, "source_order": order, "effective": effective,
        "guidance": normalized.get("guidance", []), "seeds": instructions.seed_items(normalized, path.name),
        "ambiguities": normalized.get("ambiguities", []),
    }
    result = pipeline.start_run(
        workspace=scope_root, sources_selected=sources, artifact_root=Path(effective["output_dir"]),
        run_id=run_id or time.strftime("ftd-%Y%m%d-%H%M%S"), locale=effective["locale"],
        request_text=document["text"], transcriptions=normalized.get("transcriptions"),
        formats=effective["formats"], diagnostics=effective["diagnostics"], source_order=order or None,
        reading=effective["reading"], normalized_request=record,
    )
    return {**result, "normalized_request": str(Path(result["run_dir"]) / "normalized-request.json"),
            "provenance": effective["provenance"]}


# --- /ftd-chaos -------------------------------------------------------------------------

def _next_chaos_id(run_dir: Path) -> str:
    existing = {p.name for p in (run_dir / "challenges").iterdir()} if (run_dir / "challenges").is_dir() else set()
    number = 1
    while f"chaos-{number:03d}" in existing:
        number += 1
    return f"chaos-{number:03d}"


def chaos(
    run_dir: Path, *, input_file: str | Path | None = None, normalized: dict[str, Any] | None = None,
    output: Any = None, chaos_id: str | None = None, focus: str = "", seeds: list[Path] | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """/ftd-chaos over a frozen run. Seeds come from an explicit instructions file
    (normalized by the host) or, when none is given, from the parent run's own saved
    normalized request. Seeds are inspiration only; the canonical suite is never touched."""
    run_dir = Path(run_dir).resolve()
    seed_items, seed_source = [], None
    if input_file is not None:
        path = instructions.resolve_input_file(input_file, workspace=Path(workspace or Path.cwd()), skill_root=SKILL_ROOT)
        document = instructions.load_input(path)
        if normalized is None:
            return instructions.normalization_order(document, {"output": output, "focus": focus}, command="chaos")
        errors = instructions.validate_request(normalized, document)
        if errors:
            raise instructions.InstructionsError("; ".join(errors))
        seed_items = instructions.seed_items(normalized, path.name)
        seed_source = {"path": path.name, "digest": document["digest"]}
    elif (run_dir / "normalized-request.json").is_file():
        saved = read_json(run_dir / "normalized-request.json")
        seed_items = saved.get("seeds", [])
        seed_source = saved.get("input_file")
    formats = instructions.parse_output(output) or list(instructions.DEFAULT_OUTPUT)
    return challenge_stage.start_challenge(
        run_dir, chaos_id or _next_chaos_id(run_dir), seeds=seeds, focus=focus,
        seed_items=seed_items, seed_source=seed_source, formats=formats,
    )


# --- dispatch ---------------------------------------------------------------------------

def dispatch(intent: str, **request: Any) -> Any:
    intent = str(intent).lstrip("/$").casefold()
    if intent in RETIRED:
        raise ValueError(RETIRED[intent])
    if intent not in INTENTS:
        raise ValueError(f"Unknown workflow intent: {intent}")
    if intent == "ftd-gen":
        legacy = sorted(LEGACY_REQUEST_FIELDS & set(request))
        if legacy:
            raise ValueError(
                "v2.3 no longer accepts a pre-authored semantic request (" + ", ".join(legacy)
                + "); start the pipeline from selected sources and submit stage outputs"
            )
        if "input_file" in request or "normalized" in request:
            return generate(
                input_file=request.get("input_file"), normalized=request.get("normalized"),
                explicit={"output": request.get("output"), "diagnostics": request.get("diagnostics"),
                          "locale": request.get("locale"), "output_dir": request.get("output_dir"),
                          "post_generation": parse_after(request.get("after")),
                          **{f"reading_{k}": v for k, v in (request.get("reading") or {}).items()}},
                workspace=request.get("workspace"), run_id=request.get("run_id"),
            )
        missing = [key for key in ("workspace", "artifact_root", "run_id") if key not in request]
        if missing or not (request.get("sources") or request.get("selectors")):
            raise ValueError("ftd-gen requires an instructions file (input_file) or selected sources: "
                             + ", ".join(missing or ["sources"]))
        return pipeline.start_run(
            workspace=request["workspace"], sources_selected=selected_sources(request),
            artifact_root=request["artifact_root"], run_id=request["run_id"],
            locale=request.get("locale"), request_text=request.get("request_text", ""),
            transcriptions=request.get("transcriptions"), id_pattern=request.get("id_pattern"),
            formats=_formats(request),
            diagnostics=bool(request.get("diagnostics", request.get("diagnostic", False))),
            source_order=request.get("source_order"), clarifications=request.get("clarifications"),
            reading=request.get("reading"),
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
        return pipeline.render_run(_run_dir(request), _formats(request))
    if intent == "ftd-chaos":
        return chaos(
            _run_dir(request), input_file=request.get("input_file"), normalized=request.get("normalized"),
            output=request.get("output"), chaos_id=request.get("chaos_id"), focus=request.get("focus", ""),
            seeds=[Path(p) for p in request.get("seeds", []) or []], workspace=request.get("workspace"),
        )
    if intent == "ftd-azure-publish":
        # Never reached implicitly: the host dispatches it only on an explicit publication request.
        phase = request.get("phase")
        if phase == "prepare":
            target = {key: request.get(key) for key in ("organization", "project", "plan", "root_suite")}
            remote = request.get("remote") or azure_publish.remote_for(str(target["organization"] or ""), request.get("auth", ""))
            return azure_publish.prepare(_run_dir(request), target, remote)
        if phase == "apply":
            plan = read_json(Path(request["plan_file"]))
            remote = request.get("remote") or azure_publish.remote_for(plan["target"]["organization"]["url"], request.get("auth", ""))
            return azure_publish.apply(Path(request["plan_file"]), remote, confirmation=request.get("confirmation"),
                                       approved=bool(request.get("approved")))
        raise ValueError("ftd-azure-publish needs phase 'prepare' or 'apply'; /ftd-azure alone never publishes")
    return azure_export.convert_run(
        _run_dir(request), chaos_ids=request.get("chaos_ids"), output=request.get("output", "json"),
        requirement_mapping=request.get("requirement_mapping"),
        target={key: request.get(key) for key in ("project", "plan", "suite")},
    )


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


# --- CLI --------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["azure-publish"]:
        return azure_publish.main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("gen", help="/ftd-gen: canonical suite from instructions.md/.txt")
    gen.add_argument("--input-file")
    gen.add_argument("--output", help="json,md,html (any case; default json,md,html)")
    gen.add_argument("--diagnostics", action="store_true")
    gen.add_argument("--output-dir")
    gen.add_argument("--locale")
    gen.add_argument("--normalized", type=Path, help="the host model's normalized request JSON")
    gen.add_argument("--run-id")
    gen.add_argument("--after", help="follow-up after the run: chaos,azure (local export) or none; overrides the file")
    gen.add_argument("--workspace", type=Path, help="current workspace (default: cwd)")
    gen.add_argument("--reading-strategy", choices=instructions.STRATEGIES)
    gen.add_argument("--reading-worker-model")
    gen.add_argument("--reading-concurrency", type=int)
    chaos_cmd = commands.add_parser("chaos", help="/ftd-chaos: post-suite pass over a finalized run")
    chaos_cmd.add_argument("--run", type=Path, help="default: the current validated run of --output-dir")
    chaos_cmd.add_argument("--output-dir", type=Path, help="artifact root holding .ftd/current-run.json (default ./ftd-output)")
    chaos_cmd.add_argument("--input-file")
    chaos_cmd.add_argument("--output", help="json,md,html (default json,md,html)")
    chaos_cmd.add_argument("--chaos-id")
    chaos_cmd.add_argument("--normalized", type=Path)
    chaos_cmd.add_argument("--focus", default="")
    chaos_cmd.add_argument("--workspace", type=Path)
    azure = commands.add_parser("azure", help="/ftd-azure: local Azure DevOps input JSON")
    azure.add_argument("--run", type=Path, help="default: the current validated run of --output-dir")
    azure.add_argument("--output-dir", type=Path, help="artifact root holding .ftd/current-run.json (default ./ftd-output)")
    for name, text in (("check", "/ftd-check: read-only audit of a validated suite"),
                       ("render", "/ftd-render: re-render a validated run from persisted state")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--run", type=Path, help="default: the current validated run of --output-dir")
        sub.add_argument("--output-dir", type=Path, help="artifact root holding .ftd/current-run.json (default ./ftd-output)")
        if name == "check":
            sub.add_argument("--focus", default="everything")
        else:
            sub.add_argument("--output", help="json,md,html (default: the run's formats)")
    azure.add_argument("--output", default="json")
    azure.add_argument("--chaos-id", action="append", default=None)
    azure.add_argument("--canonical-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "gen":
            result = generate(
                input_file=args.input_file, normalized=read_json(args.normalized) if args.normalized else None,
                explicit={"output": args.output, "diagnostics": args.diagnostics or None, "locale": args.locale,
                          "output_dir": args.output_dir, "post_generation": parse_after(args.after),
                          "reading_strategy": args.reading_strategy,
                          "reading_worker_model": args.reading_worker_model,
                          "reading_concurrency": args.reading_concurrency},
                workspace=args.workspace, run_id=args.run_id,
            )
        elif args.command == "chaos":
            result = chaos(
                pipeline.resolve_run(args.run, args.output_dir), input_file=args.input_file,
                normalized=read_json(args.normalized) if args.normalized else None,
                output=args.output, chaos_id=args.chaos_id, focus=args.focus, workspace=args.workspace,
            )
        elif args.command == "check":
            result = dispatch("ftd-check", run_dir=args.run, output_dir=args.output_dir, focus=args.focus)
        elif args.command == "render":
            result = dispatch("ftd-render", run_dir=args.run, output_dir=args.output_dir, output=args.output)
            result.pop("files", None)
        else:
            result = azure_export.convert_run(
                pipeline.resolve_run(args.run, args.output_dir), chaos_ids=[] if args.canonical_only else args.chaos_id,
                output=args.output,
            )
    except (ValueError, OSError) as exc:
        errors = getattr(exc, "errors", None) or [str(exc)]
        print(json.dumps({"errors": errors}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
