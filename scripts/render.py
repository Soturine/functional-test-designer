#!/usr/bin/env python3
"""Render a validated suite as Markdown, one offline HTML report and the expansion
catalog. Rendering displays canonical state only: it never infers semantic truth, never
reads project sources and never reconstructs titles from reference strings.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validation import gap_summary, validate  # noqa: E402


LABELS = {
    "pt": {
        "objective": "Objetivo", "preconditions": "Pré-condições", "test_data": "Dados de teste",
        "steps": "Passos", "postconditions": "Pós-condições", "cleanup": "Limpeza",
        "traceability": "Rastreabilidade", "json_artifact": "Artefato JSON", "flow": "Fluxo do Teste",
        "action": "Ação", "expected": "Resultado esperado", "clarification": "Esclarecimento",
        "yes": "Sim", "no": "Não", "none": "Nenhum", "status": "Status", "priority": "Prioridade",
        "type": "Tipo", "basis": "Base do teste", "primary_type": "Tipo primário",
        "suitability": "Adequação à automação", "automation_readiness": "Prontidão para automação",
        "layer": "Camada", "blockers": "Pendências", "family": "Família de cenários",
        "requirements": "Requisitos", "coverage_points": "Coverage points", "sources": "Fontes",
        "composes": "Compõe", "findings": "Findings", "questions": "Perguntas",
        "summary": "Resumo", "test_cases": "Test Cases", "merge": "Merge Candidates",
        "coverage": "Cobertura", "expansion": "Expansão", "gates": "Quality gates",
        "search": "Buscar", "all": "Todos", "feature": "Característica", "start": "Início",
        "end": "Fim", "needs_answer": "A esclarecer", "identifiers": "Identificadores de autoridade",
        "dimension": "Dimensão", "report_title": "Relatório de Test Cases",
        "report_subtitle": "Casos derivados apenas das fontes explicitamente selecionadas.",
        "total": "Total de TCs", "normative": "Normativos", "derived": "Derivados",
        "characterization": "Caracterização", "exploratory": "Exploratórios", "e2e": "E2E",
        "operator_error": "Erro de operador", "chaos": "Caos / Recuperação",
        "concurrency": "Concorrência", "security": "Segurança / Autorização",
        "families": "Famílias", "gaps": "Lacunas", "locale": "Idioma", "baseline": "Baseline histórico",
        "blocking": "Bloqueante", "reason": "Motivo", "impacted": "TCs impactados",
        "no_results": "Nenhum Test Case corresponde aos filtros.", "expand_all": "Expandir todos",
        "collapse_all": "Recolher todos", "collapse": "Recolher", "expand": "Expandir",
        "identifier": "Identificador", "disposition": "Disposição", "kind": "Tipo",
        "candidates": "Candidatos", "materialized": "Materializados", "covered": "Já cobertos",
        "question_required": "Pergunta", "not_applicable": "Não aplicável",
        "automation_ready": "Automação pronta", "suitable": "Automatizáveis",
        "no_merge": "Nenhuma sugestão de compactação manual.", "no_findings": "Nenhum finding.",
        "no_questions": "Nenhuma pergunta pendente.", "artifacts": "Artefatos",
        "open_flow": "Ampliar fluxo", "close": "Fechar", "technical": "Detalhes técnicos",
        "single_step": "1 passo", "multi_step": "Vários passos", "catalog": "Catálogo de expansão",
        "catalog_intro": "Test Cases adicionados pela segunda passada obrigatória, agrupados por dimensão. Cada linha aponta para um Test Case canônico.",
        "evidence": "Evidência", "gap_metrics": "Métricas de lacunas", "authority_covered": "Identificadores cobertos",
    },
    "en": {
        "objective": "Objective", "preconditions": "Preconditions", "test_data": "Test Data",
        "steps": "Steps", "postconditions": "Postconditions", "cleanup": "Cleanup",
        "traceability": "Traceability", "json_artifact": "JSON Artifact", "flow": "Test Flow",
        "action": "Action", "expected": "Expected result", "clarification": "Clarification",
        "yes": "Yes", "no": "No", "none": "None", "status": "Status", "priority": "Priority",
        "type": "Type", "basis": "Test basis", "primary_type": "Primary type",
        "suitability": "Automation suitability", "automation_readiness": "Automation readiness",
        "layer": "Layer", "blockers": "Open items", "family": "Scenario Family",
        "requirements": "Requirements", "coverage_points": "Coverage points", "sources": "Sources",
        "composes": "Composes", "findings": "Findings", "questions": "Questions",
        "summary": "Summary", "test_cases": "Test Cases", "merge": "Merge Candidates",
        "coverage": "Coverage", "expansion": "Expansion", "gates": "Quality gates",
        "search": "Search", "all": "All", "feature": "Feature", "start": "Start", "end": "End",
        "needs_answer": "Needs clarification", "identifiers": "Authority identifiers",
        "dimension": "Dimension", "report_title": "Functional Test Report",
        "report_subtitle": "Test Cases derived only from explicitly selected sources.",
        "total": "Total TCs", "normative": "Normative", "derived": "Derived",
        "characterization": "Characterization", "exploratory": "Exploratory", "e2e": "E2E",
        "operator_error": "Operator Error", "chaos": "Chaos / Recovery",
        "concurrency": "Concurrency", "security": "Security / Authorization",
        "families": "Families", "gaps": "Gaps", "locale": "Locale", "baseline": "Historical baseline",
        "blocking": "Blocking", "reason": "Reason", "impacted": "Impacted TCs",
        "no_results": "No Test Case matches the filters.", "expand_all": "Expand all",
        "collapse_all": "Collapse all", "collapse": "Collapse", "expand": "Expand",
        "identifier": "Identifier", "disposition": "Disposition", "kind": "Kind",
        "candidates": "Candidates", "materialized": "Materialized", "covered": "Already covered",
        "question_required": "Question", "not_applicable": "Not applicable",
        "automation_ready": "Automation ready", "suitable": "Automatable",
        "no_merge": "No manual compaction suggestion.", "no_findings": "No findings.",
        "no_questions": "No pending questions.", "artifacts": "Artifacts",
        "open_flow": "Enlarge flow", "close": "Close", "technical": "Technical details",
        "single_step": "1 step", "multi_step": "Multiple steps", "catalog": "Expansion catalog",
        "catalog_intro": "Test Cases added by the mandatory second pass, grouped by dimension. Each row points at a canonical Test Case.",
        "evidence": "Evidence", "gap_metrics": "Gap metrics", "authority_covered": "Identifiers covered",
    },
}
OPERATOR_DIMENSIONS = {"OPERATOR_ERROR", "MISUSE"}
CHAOS_DIMENSIONS = {"CHAOS", "RECOVERY"}
CONCURRENCY_DIMENSIONS = {"CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY"}
SECURITY_DIMENSIONS = {"SECURITY", "AUTHORIZATION"}


def labels_for(index: dict[str, Any]) -> dict[str, str]:
    # Suites published before v2.3 carry no locale; they keep neutral English labels.
    language = str(index.get("output_locale", "en")).split("-", 1)[0].casefold()
    return LABELS.get(language, LABELS["en"])


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def requirement_label(requirement: dict[str, Any]) -> str:
    """Official identifier and title exactly as stored; never parsed from references."""
    identifier = requirement.get("source_identifier")
    title = requirement.get("source_title")
    if identifier and title:
        return f"{identifier} — {title}"
    if identifier:
        return str(identifier)
    return str(requirement["id"])


def _identifier_title(identifier: str, requirements: dict[str, dict[str, Any]]) -> str:
    for requirement in requirements.values():
        if requirement.get("source_identifier") == identifier:
            return requirement_label(requirement)
    return identifier


def is_operator_error(case: dict[str, Any]) -> bool:
    return case.get("expansion_dimension") in OPERATOR_DIMENSIONS or "operator-error" in {
        str(tag).casefold() for tag in case.get("tags", [])
    }


def is_chaos(case: dict[str, Any]) -> bool:
    return case.get("expansion_dimension") in CHAOS_DIMENSIONS or case.get("primary_type") in {
        "CHAOS", "RECOVERY", "RESILIENCE",
    }


# --- Markdown -----------------------------------------------------------------------

def _inline(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def _bullets(values: list[str], none: str) -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {none}"


def _mermaid_label(value: Any, width: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip().replace("&", " and ")
    text = re.sub(r'["`]', "", text)  # quoting marks vanish, so a quoted label keeps its punctuation
    text = re.sub(r'[\\\[\]{}|<>]', " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    words = re.sub(r"\s+", " ", text).strip().split() or ["-"]
    lines, current = [], []
    for word in words:
        if current and len(" ".join(current + [word])) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    lines.append(" ".join(current))
    return "<br/>".join(lines)


def mermaid_source(case: dict[str, Any], labels: dict[str, str] | None = None) -> str:
    labels = labels or LABELS["pt"]
    lines = ["flowchart TD", f"    S([{labels['start']}])"]
    chain, expected_nodes, pending_nodes = ["S"], [], []
    for step in case["steps"]:
        number = step["step"]
        expected = step["expected_result"]
        result_id = f"R{number}" if expected is not None else f"C{number}"
        lines.append(f'    A{number}["{number} - {labels["action"]}<br/>{_mermaid_label(step["action"])}"]')
        if expected is None:
            lines.append(f'    {result_id}["{labels["needs_answer"]}<br/>{_mermaid_label(labels["needs_answer"])}"]')
            pending_nodes.append(result_id)
        else:
            lines.append(f'    {result_id}["{labels["expected"]}<br/>{_mermaid_label(expected)}"]')
            expected_nodes.append(result_id)
        chain.extend((f"A{number}", result_id))
    lines.append(f"    F([{labels['end']}])")
    chain.append("F")
    lines += [
        "", "    " + " --> ".join(chain), "",
        "    classDef startEnd fill:#f8fafc,stroke:#475569,stroke-width:1.5px,color:#0f172a;",
        "    classDef action fill:#eff6ff,stroke:#2563eb,stroke-width:1.5px,color:#0f172a;",
        "    classDef expected fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px,color:#14532d;",
        "    classDef clarification fill:#fff7ed,stroke:#ea580c,stroke-width:1.5px,color:#7c2d12,stroke-dasharray:4 3;",
        "", "    class S,F startEnd;",
        "    class " + ",".join(f"A{step['step']}" for step in case["steps"]) + " action;",
    ]
    if expected_nodes:
        lines.append("    class " + ",".join(expected_nodes) + " expected;")
    if pending_nodes:
        lines.append("    class " + ",".join(pending_nodes) + " clarification;")
    return "\n".join(lines)


def extract_mermaid(markdown: str) -> str:
    match = re.search(
        r"## (?:Fluxo do Teste|Test Flow)\s*\n```mermaid\n(.*?)\n```\s*\Z", markdown, re.DOTALL
    )
    if not match:
        raise ValueError("Markdown must end with a test-flow Mermaid block")
    return match.group(1)


def render_case_markdown(
    case: dict[str, Any], json_path: str, labels: dict[str, str],
    requirements: dict[str, dict[str, Any]], family: str | None,
) -> str:
    none = labels["none"]
    data = [f"- **{item['name']}:** {item['description']}" for item in case["test_data"]]
    steps = [
        f"| # | {labels['action']} | {labels['expected']} | {labels['clarification']} |",
        "|---:|---|---|:---:|",
    ]
    for step in case["steps"]:
        expected = step["expected_result"] or labels["needs_answer"]
        flag = labels["yes"] if step["needs_clarification"] else labels["no"]
        steps.append(f"| {step['step']} | {_inline(step['action'])} | {_inline(expected)} | {flag} |")
    requirement_names = [
        requirement_label(requirements[ref]) if ref in requirements else ref
        for ref in case["requirement_refs"]
    ]
    sources = [f"`{item['source']}` ({item['reference']})" for item in case["source_refs"]]
    header = [
        f"**{labels['status']}:** {case['status']}",
        f"**{labels['priority']}:** {case['priority']}",
        f"**{labels['type']}:** {case['type']}",
    ]
    if family:
        header.append(f"**{labels['family']}:** {family}")
    if case.get("source_identifiers"):
        header.append(f"**{labels['identifiers']}:** " + " ".join(f"`{value}`" for value in case["source_identifiers"]))
    sections = [f"# {case['id']} - {case['title']}", "  \n".join(header)]
    if case.get("schema_version") == "2.2":
        design = [f"**{labels['basis']}:** {case.get('test_basis')}"]
        design.append(f"**{labels['primary_type']}:** {case.get('primary_type')}")
        if case.get("expansion_dimension"):
            design.append(f"**{labels['dimension']}:** {case['expansion_dimension']}")
        if case.get("automation_suitability"):
            design.append(f"**{labels['suitability']}:** {case['automation_suitability']}")
            design.append(f"**{labels['automation_readiness']}:** {case.get('automation_readiness')}")
            design.append(f"**{labels['layer']}:** {case.get('automation_layer')}")
        if case.get("readiness_blockers"):
            design.append(f"**{labels['blockers']}:** " + ", ".join(case["readiness_blockers"]))
        if case.get("composes"):
            design.append(f"**{labels['composes']}:** " + ", ".join(case["composes"]))
        if case.get("finding_refs"):
            design.append(f"**{labels['findings']}:** " + ", ".join(case["finding_refs"]))
        if case.get("question_refs"):
            design.append(f"**{labels['questions']}:** " + ", ".join(case["question_refs"]))
        sections.append("  \n".join(design))
    sections += [
        f"## {labels['objective']}\n" + case["objective"],
        f"## {labels['preconditions']}\n" + _bullets(case["preconditions"], none),
        f"## {labels['test_data']}\n" + ("\n".join(data) if data else f"- {none}"),
        f"## {labels['steps']}\n" + "\n".join(steps),
        f"## {labels['postconditions']}\n" + _bullets(case["postconditions"], none),
        f"## {labels['cleanup']}\n" + _bullets(case["cleanup"], none),
        f"## {labels['traceability']}\n"
        f"- {labels['requirements']}: {', '.join(requirement_names) or none}\n"
        f"- {labels['coverage_points']}: {', '.join(case['coverage_point_refs'])}\n"
        f"- {labels['sources']}: {', '.join(sources)}",
        f"## {labels['json_artifact']}\n`{json_path}`",
        f"## {labels['flow']}\n```mermaid\n" + mermaid_source(case, labels) + "\n```",
    ]
    return "\n\n".join(sections) + "\n"


def family_titles(index: dict[str, Any]) -> dict[str, str]:
    return {
        item["id"]: item["title"] for item in index.get("scenarios", [])
        if item.get("type") == "SCENARIO_FAMILY"
    }


def render_markdown(output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir).resolve()
    errors = validate(output_dir)
    if errors:
        raise ValueError("Output validation failed:\n- " + "\n- ".join(errors))
    index = read_json(output_dir / "test-cases.json")
    labels = labels_for(index)
    requirements = {item["id"]: item for item in index["requirements"]}
    families = family_titles(index)
    markdown_dir = output_dir / "test-cases-md"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for entry in index["test_cases"]:
        case = read_json(output_dir / entry["file"])
        destination = (output_dir / entry["markdown_file"]).resolve()
        if markdown_dir.resolve() not in destination.parents:
            raise ValueError(f"Markdown path escapes test-cases-md: {entry['markdown_file']}")
        family = families.get((case.get("scenario_refs") or [""])[0])
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_case_markdown(case, entry["file"], labels, requirements, family))
        rendered.append(destination)
    for stale in markdown_dir.glob("*.md"):
        if stale.resolve() not in rendered:
            stale.unlink()
    return rendered


# --- expansion catalog ----------------------------------------------------------------

def render_expansion_catalog(index: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    """Review projection of the second pass: it links canonical Test Cases, nothing more."""
    labels = labels_for(index)
    lines = [f"# {labels['catalog']}", "", labels["catalog_intro"], ""]
    for item in index.get("expansion_summary", []):
        own = [case for case in cases if case.get("expansion_dimension") == item["dimension"]]
        lines.append(
            f"## {item['dimension']} — {labels['candidates']}: {item['candidates_considered']} · "
            f"{labels['materialized']}: {item['materialized']} · {labels['covered']}: {item['already_covered']} · "
            f"{labels['question_required']}: {item['question_required']} · {labels['not_applicable']}: {item['not_applicable']}"
        )
        lines.append("")
        for case in own:
            item_label = f" [{case['expansion_checklist_item']}]" if case.get("expansion_checklist_item") else ""
            lines.append(
                f"- {case['id']}{item_label} — {case['title']} ({case.get('test_basis')}, {case['status']})"
            )
        if not own:
            lines.append(f"- {labels['none']}")
        lines.append("")
    return "\n".join(lines)


# --- HTML ---------------------------------------------------------------------------

def _list(values: list[str], empty: str) -> str:
    if not values:
        return f'<p class="empty">{esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{esc(value)}</li>" for value in values) + "</ul>"


def _data(rows: list[dict[str, Any]], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    return "<ul>" + "".join(
        f'<li><strong>{esc(row["name"])}</strong>: {esc(row["description"])}</li>' for row in rows
    ) + "</ul>"


def _steps(steps: list[dict[str, Any]], labels: dict[str, str]) -> str:
    rows = []
    for step in steps:
        expected = step.get("expected_result")
        cell = esc(expected) if expected is not None else f'<span class="needs-answer">{esc(labels["needs_answer"])}</span>'
        rows.append(f'<tr><td class="step-number">{esc(step["step"])}</td><td>{esc(step["action"])}</td><td>{cell}</td></tr>')
    return (
        '<div class="table-wrap"><table class="steps"><thead><tr><th scope="col">#</th>'
        f'<th scope="col">{esc(labels["action"])}</th><th scope="col">{esc(labels["expected"])}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _flow_nodes(source: str) -> list[tuple[str, str]]:
    terminal = re.compile(r"^\s+(S|F)\(\[(.*)\]\)$")
    node = re.compile(r'^\s+([ARC][0-9]+)\["(.*)"\]$')
    nodes: dict[str, str] = {}
    chain: list[str] = []
    for line in source.splitlines():
        if match := terminal.match(line):
            nodes[match.group(1)] = match.group(2)
        elif match := node.match(line):
            nodes[match.group(1)] = match.group(2)
        elif line.strip().startswith("S -->"):
            chain = [part.strip() for part in line.strip().split("-->")]
    if not chain or chain[0] != "S" or chain[-1] != "F" or any(item not in nodes for item in chain):
        raise ValueError("Mermaid flow must contain one Start-to-End chain")
    return [(item, nodes[item]) for item in chain]


def _flow_svg(source: str, flow_id: str) -> str:
    width, regular, terminal_width, gap, y = 720, 600, 160, 34, 24
    layout = []
    for node_id, label in _flow_nodes(source):
        lines = label.split("<br/>")
        terminal = node_id in {"S", "F"}
        height = 50 if terminal else max(72, 30 + 20 * len(lines))
        box = terminal_width if terminal else regular
        layout.append({"id": node_id, "lines": lines, "x": (width - box) / 2, "y": y, "w": box, "h": height})
        y += height + gap
    marker = "arrow-" + re.sub(r"[^a-zA-Z0-9_-]", "-", flow_id)
    palette = {
        "terminal": ("#f8fafc", "#475569", "#0f172a"), "action": ("#eff6ff", "#2563eb", "#0f172a"),
        "expected": ("#f0fdf4", "#16a34a", "#14532d"), "clarification": ("#fff7ed", "#ea580c", "#7c2d12"),
    }
    parts = []
    for previous, current in zip(layout, layout[1:]):
        parts.append(
            f'<line x1="{width / 2:g}" y1="{previous["y"] + previous["h"]:g}" x2="{width / 2:g}" '
            f'y2="{current["y"] - 7:g}" stroke="#64748b" stroke-width="1.5" marker-end="url(#{marker})" />'
        )
    for item in layout:
        kind = ("terminal" if item["id"] in {"S", "F"} else "action" if item["id"].startswith("A")
                else "clarification" if item["id"].startswith("C") else "expected")
        fill, stroke, color = palette[kind]
        radius = item["h"] / 2 if kind == "terminal" else 8
        first = item["y"] + item["h"] / 2 - (len(item["lines"]) - 1) * 10
        spans = "".join(
            f'<tspan x="{width / 2:g}" dy="{0 if position == 0 else 20}"'
            f'{" class=\"node-label-title\"" if position == 0 and len(item["lines"]) > 1 else ""}>{esc(line)}</tspan>'
            for position, line in enumerate(item["lines"])
        )
        dash = ' stroke-dasharray="4 3"' if kind == "clarification" else ""
        parts.append(
            f'<g class="mermaid-node mermaid-{kind}" data-node-id="{esc(item["id"])}"><rect x="{item["x"]:g}" '
            f'y="{item["y"]:g}" width="{item["w"]:g}" height="{item["h"]:g}" rx="{radius:g}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.5"{dash} /><text x="{width / 2:g}" y="{first:g}" '
            f'text-anchor="middle" fill="{color}" font-family="system-ui, sans-serif" font-size="14">{spans}</text></g>'
        )
    return (
        f'<svg class="mermaid-svg" viewBox="0 0 {width} {y - gap + 24:g}" role="img" '
        f'aria-label="flow" xmlns="http://www.w3.org/2000/svg"><defs><marker id="{marker}" viewBox="0 0 10 10" '
        'refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" /></marker></defs>' + "".join(parts) + "</svg>"
    )


def _case_flags(case: dict[str, Any], merge_ids: set[str], question_ids: set[str]) -> set[str]:
    flags = {"single-step" if len(case.get("steps", [])) == 1 else "multi-step"}
    basis = case.get("test_basis", "ACCEPTANCE")
    flags.add({"ACCEPTANCE": "normative", "DERIVED": "derived", "CHARACTERIZATION": "characterization",
               "EXPLORATORY": "exploratory", "E2E": "e2e", "REGRESSION": "normative"}.get(basis, "normative"))
    if is_operator_error(case):
        flags.add("operator-error")
    if is_chaos(case):
        flags.add("chaos-recovery")
    if case["id"] in merge_ids:
        flags.add("merge-candidate")
    if case.get("finding_refs"):
        flags.add("findings")
    if case["id"] in question_ids or case.get("question_refs"):
        flags.add("questions")
    if case.get("automation_readiness") == "READY":
        flags.add("automation-ready")
    return flags


def render_case_html(
    case: dict[str, Any], entry: dict[str, Any], mermaid: str, labels: dict[str, str],
    requirements: dict[str, dict[str, Any]], family_id: str, family: str, flags: set[str],
    artifact_formats: set[str],
) -> str:
    none = labels["none"]
    search = " ".join([case["id"], case["title"], case["objective"], family, " ".join(case.get("tags", [])),
                       " ".join(case.get("source_identifiers", []))]).casefold()
    badges = [f'<span class="badge test-basis">{esc(case.get("test_basis", "ACCEPTANCE"))}</span>']
    if case.get("expansion_dimension"):
        badges.append(f'<span class="badge dimension">{esc(case["expansion_dimension"])}</span>')
    badges.append(f'<span class="badge status-{esc(case["status"].lower())}">{esc(case["status"])}</span>')
    badges.append(f'<span class="badge priority">{esc(case["priority"])}</span>')
    if case.get("automation_suitability"):
        badges.append(
            f'<span class="badge automation">{esc(case["automation_suitability"])} / '
            f'{esc(case.get("automation_readiness"))}</span>'
        )
    requirement_names = [
        requirement_label(requirements[ref]) if ref in requirements else ref for ref in case["requirement_refs"]
    ]
    # Every authoritative identifier recorded during design, visible without expanding.
    chips = "".join(
        f'<span class="chip" title="{esc(_identifier_title(value, requirements))}">{esc(value)}</span>'
        for value in case.get("source_identifiers", [])
    )
    chips = f'<span class="identifier-chips">{chips}</span>' if chips else ""
    automation = ""
    if case.get("automation_suitability"):
        rows = [
            (labels["suitability"], case["automation_suitability"]),
            (labels["automation_readiness"], case.get("automation_readiness")),
            (labels["layer"], case.get("automation_layer")),
            (labels["blockers"], ", ".join(case.get("readiness_blockers", [])) or none),
        ]
        automation = '<dl class="technical-grid">' + "".join(
            f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in rows
        ) + "</dl>"
    trace_rows = [
        (labels["requirements"], "; ".join(requirement_names) or none),
        (labels["identifiers"], ", ".join(case.get("source_identifiers", [])) or none),
        (labels["coverage_points"], ", ".join(case["coverage_point_refs"])),
        (labels["composes"], ", ".join(case.get("composes", [])) or none),
        (labels["findings"], ", ".join(case.get("finding_refs", [])) or none),
        (labels["questions"], ", ".join(case.get("question_refs", [])) or none),
        (labels["sources"], "; ".join(f"{ref['source']} ({ref['reference']})" for ref in case["source_refs"])),
    ]
    trace = '<dl class="technical-grid">' + "".join(
        f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in trace_rows
    ) + "</dl>"
    links = []
    if "JSON" in artifact_formats:
        links.append(f'<a href="{esc(entry["file"])}">JSON</a>')
    if "MARKDOWN" in artifact_formats:
        links.append(f'<a href="{esc(entry["markdown_file"])}">Markdown</a>')
    flow_id = f"flow-{case['id']}"
    try:
        flow = f'<div class="mermaid-container" id="{esc(flow_id)}">{_flow_svg(mermaid, flow_id)}</div>'
        expand = f'<button type="button" class="expand-flow" data-flow-target="{esc(flow_id)}">{esc(labels["open_flow"])}</button>'
    except ValueError:
        flow, expand = '<div class="flow-error" role="status">-</div>', ""
    flow += f'<pre class="mermaid-source" hidden>{esc(mermaid)}</pre>'
    return f"""
<details class="tc-card" data-status="{esc(case['status'])}" data-priority="{esc(case['priority'])}" data-family="{esc(family_id)}" data-features="{esc(' '.join(sorted(flags)))}" data-search="{esc(search)}">
  <summary><span class="tc-heading"><span class="tc-id">{esc(case['id'])}</span>{esc(case['title'])}{chips}</span><span class="badges">{''.join(badges)}</span></summary>
  <div class="tc-content">
    <section><h3>{esc(labels['objective'])}</h3><p>{esc(case['objective'])}</p></section>
    <p class="related-requirements"><strong>{esc(labels['requirements'])}:</strong> {esc('; '.join(requirement_names))}</p>
    <div class="two-column">
      <section><h3>{esc(labels['preconditions'])}</h3>{_list(case.get('preconditions', []), none)}</section>
      <section><h3>{esc(labels['test_data'])}</h3>{_data(case.get('test_data', []), none)}</section>
    </div>
    <section><h3>{esc(labels['steps'])}</h3>{_steps(case['steps'], labels)}</section>
    <section class="flow-section"><div class="flow-heading"><h3>{esc(labels['flow'])}</h3>{expand}</div>{flow}</section>
    {f'<section><h3>{esc(labels["suitability"])}</h3>{automation}</section>' if automation else ''}
    <section><h3>{esc(labels['artifacts'])}</h3><div class="artifact-links">{''.join(links) or esc(none)}</div></section>
    <details class="technical"><summary>{esc(labels['technical'])}</summary>{trace}</details>
  </div>
</details>"""


def render_report(output_dir: Path, destination: Path | None = None, artifact_formats: set[str] | None = None) -> Path:
    output_dir = Path(output_dir).resolve()
    errors = validate(output_dir)
    if errors:
        raise ValueError("Output validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    artifact_formats = {"JSON", "MARKDOWN"} if artifact_formats is None else set(artifact_formats)
    index = read_json(output_dir / "test-cases.json")
    labels = labels_for(index)
    questions = read_json(output_dir / "questions.json")["questions"]
    cases = [read_json(output_dir / entry["file"]) for entry in index["test_cases"]]
    requirements = {item["id"]: item for item in index["requirements"]}
    mermaid_by_id = {}
    for entry, case in zip(index["test_cases"], cases):
        markdown_path = output_dir / entry["markdown_file"]
        if not markdown_path.is_file():
            raise ValueError(f"Missing Markdown artifact for {entry['id']}: {entry['markdown_file']}")
        source = extract_mermaid(markdown_path.read_text(encoding="utf-8"))
        if source != mermaid_source(case, labels):
            raise ValueError(f"Markdown Mermaid flow differs from JSON steps for {entry['id']}")
        mermaid_by_id[case["id"]] = source

    families = family_titles(index)
    if families:
        group_of = {case["id"]: (case["scenario_refs"][0], families[case["scenario_refs"][0]]) for case in cases}
        group_order = list(families)
    else:  # legacy one-scenario-per-case suites group by primary requirement
        group_of = {}
        for case in cases:
            ref = case["requirement_refs"][0]
            group_of[case["id"]] = (ref, requirement_label(requirements[ref]) if ref in requirements else ref)
        group_order = list(dict.fromkeys(value[0] for value in group_of.values()))
    merge_ids = {tc for item in index.get("merge_candidates", []) for tc in item.get("test_case_ids", [])}
    question_case_ids = {tc for item in questions for tc in item.get("related_test_cases", [])}
    groups_html = []
    for group_id in group_order:
        members = [(entry, case) for entry, case in zip(index["test_cases"], cases) if group_of[case["id"]][0] == group_id]
        if not members:
            continue
        title = group_of[members[0][1]["id"]][1]
        member_requirements = list(dict.fromkeys(ref for _, case in members for ref in case["requirement_refs"]))
        req_line = "; ".join(requirement_label(requirements[ref]) for ref in member_requirements if ref in requirements)
        cards = "".join(
            render_case_html(case, entry, mermaid_by_id[case["id"]], labels, requirements, group_id, title,
                             _case_flags(case, merge_ids, question_case_ids), artifact_formats)
            for entry, case in members
        )
        body_id = f"family-body-{group_id}"
        groups_html.append(
            f'<section class="tc-group" id="family-{esc(group_id)}" data-family="{esc(group_id)}"><div class="tc-group-title">'
            f'<div><h3>{esc(title)}</h3><span>{len(members)} TCs &middot; {esc(req_line)}</span></div>'
            f'<button type="button" class="group-toggle" aria-expanded="true" aria-controls="{esc(body_id)}">{esc(labels["collapse"])}</button>'
            f'</div><div class="tc-group-body" id="{esc(body_id)}">{cards}</div></section>'
        )

    status = Counter(case["status"] for case in cases)
    basis = Counter(case.get("test_basis", "ACCEPTANCE") for case in cases)
    ledger = index.get("identifier_dispositions", [])
    covered = sum(str(item.get("disposition", "")).startswith("COVERED") for item in ledger)
    gaps = index.get("gap_metrics")
    baseline = (index.get("baseline_comparison") or {}).get("status", "NOT_APPLIED")
    metrics = [
        (len(cases), labels["total"]), (status["READY"], "READY"), (status["NEEDS_REVIEW"], "NEEDS_REVIEW"),
        (sum(value for key, value in status.items() if key.startswith("BLOCKED")), "BLOCKED"),
        (status["EXPLORATORY"], "EXPLORATORY"),
        (basis["ACCEPTANCE"] + basis["REGRESSION"], labels["normative"]), (basis["DERIVED"], labels["derived"]),
        (basis["CHARACTERIZATION"], labels["characterization"]), (basis["EXPLORATORY"], labels["exploratory"]),
        (basis["E2E"], labels["e2e"]), (sum(is_operator_error(c) for c in cases), labels["operator_error"]),
        (sum(is_chaos(c) for c in cases), labels["chaos"]),
        (sum(c.get("expansion_dimension") in CONCURRENCY_DIMENSIONS for c in cases), labels["concurrency"]),
        (sum(c.get("expansion_dimension") in SECURITY_DIMENSIONS or c.get("primary_type") in {"SECURITY", "AUTHORIZATION"} for c in cases), labels["security"]),
        (len(families) or len(index.get("scenarios", [])), labels["families"]),
        (len(index.get("merge_candidates", [])), labels["merge"]), (len(index.get("findings", [])), labels["findings"]),
        (len(questions), labels["questions"]),
        (f"{covered}/{len(ledger)}" if ledger else "-", labels["authority_covered"]),
        (sum(c.get("automation_suitability") in {"HIGH", "MEDIUM"} for c in cases), labels["suitable"]),
        (sum(c.get("automation_readiness") == "READY" for c in cases), labels["automation_ready"]),
    ]
    metric_html = "".join(f'<div class="metric"><strong>{esc(value)}</strong><span>{esc(name)}</span></div>' for value, name in metrics)
    info = [
        f"<strong>{esc(labels['locale'])}:</strong> {esc(index.get('output_locale', '-'))}",
        f"<strong>{esc(labels['gaps'])}:</strong> {esc(gap_summary(gaps) if gaps is not None else '-')}",
        f"<strong>{esc(labels['baseline'])}:</strong> {esc(baseline)}",
    ]
    finding_html = "".join(
        f'<article class="finding-item"><div class="finding-title"><span class="badge">{esc(item["type"])}</span>'
        f'<strong>{esc(item["id"])}</strong></div><p>{esc(item["statement"])}</p>'
        f'<p class="muted">{esc(labels["requirements"])}: {esc("; ".join(requirement_label(requirements[r]) for r in item["requirement_refs"] if r in requirements))}'
        f' &middot; TCs: {esc(", ".join(item.get("related_test_cases", [])) or labels["none"])}</p></article>'
        for item in index.get("findings", [])
    )
    question_html = "".join(
        f'<article class="question-item {"blocking" if item["blocking"] else ""}"><div class="question-title">'
        f'<span>{esc(item["id"])} &middot; {esc(item["question"])}</span><span class="badge">{esc(labels["blocking"])}: '
        f'{esc(labels["yes"] if item["blocking"] else labels["no"])}</span></div><p><strong>{esc(labels["reason"])}:</strong> '
        f'{esc(item["reason"])}</p><p><strong>{esc(labels["impacted"])}:</strong> {esc(", ".join(item["related_test_cases"]) or labels["none"])}</p></article>'
        for item in questions
    )
    merge_html = "".join(
        f'<article class="finding-item"><div class="finding-title"><strong>{esc(item.get("merge_candidate_id", ""))}</strong>'
        f'<span class="badge">{esc(item["confidence"])}</span></div><p>{esc(", ".join(item["test_case_ids"]))}</p>'
        f'<p class="muted">{esc(item["reason"])} &middot; {esc(item["automation_tradeoff"])}</p></article>'
        for item in index.get("merge_candidates", [])
    )
    coverage_rows = "".join(
        f'<tr><td>{esc(item["identifier"])} &mdash; {esc(item["title"])}</td><td>{esc(item["kind"])}</td>'
        f'<td>{esc(item["disposition"])}</td><td>{esc(", ".join(item.get("test_refs", [])) or item.get("reason") or "-")}</td></tr>'
        for item in ledger
    )
    requirement_rows = "".join(
        f'<tr><td>{esc(requirement_label(item))}</td><td>{esc(item["statement"])}</td><td>'
        f'{sum(item["id"] in case["requirement_refs"] for case in cases)}</td></tr>'
        for item in index["requirements"]
    )
    coverage_html = (
        (f'<div class="table-wrap"><table><thead><tr><th>{esc(labels["identifier"])}</th><th>{esc(labels["kind"])}</th>'
         f'<th>{esc(labels["disposition"])}</th><th>TCs</th></tr></thead><tbody>{coverage_rows}</tbody></table></div>'
         if ledger else "")
        + f'<div class="table-wrap"><table><thead><tr><th>{esc(labels["requirements"])}</th><th>{esc(labels["objective"])}</th>'
        f'<th>TCs</th></tr></thead><tbody>{requirement_rows}</tbody></table></div>'
    )
    expansion_rows = "".join(
        f'<tr><td>{esc(item["dimension"])}</td><td>{item["candidates_considered"]}</td><td>{item["materialized"]}</td>'
        f'<td>{item["already_covered"]}</td><td>{item["question_required"]}</td><td>{item["not_applicable"]}</td></tr>'
        for item in index.get("expansion_summary", [])
    )
    expansion_html = (
        f'<div class="table-wrap"><table><thead><tr><th>{esc(labels["dimension"])}</th><th>{esc(labels["candidates"])}</th>'
        f'<th>{esc(labels["materialized"])}</th><th>{esc(labels["covered"])}</th><th>{esc(labels["question_required"])}</th>'
        f'<th>{esc(labels["not_applicable"])}</th></tr></thead><tbody>{expansion_rows}</tbody></table></div>'
        if expansion_rows else f'<p class="empty">{esc(labels["none"])}</p>'
    )
    gate_html = "".join(
        f'<li><strong>{esc(item["gate"])}</strong> <span class="badge status-ready">{esc(item["status"])}</span> '
        f'<span class="muted">{esc(item["evidence"])}</span></li>'
        for item in index.get("quality_gates", [])
    )
    gap_html = "".join(f"<li>{esc(key)}: {esc(value)}</li>" for key, value in (gaps or {}).items())
    family_options = "".join(
        f'<option value="{esc(group_id)}">{esc(group_of[next(c["id"] for c in cases if group_of[c["id"]][0] == group_id)][1])}</option>'
        for group_id in group_order if any(group_of[c["id"]][0] == group_id for c in cases)
    )
    features = ["normative", "derived", "characterization", "exploratory", "e2e", "operator-error",
                "chaos-recovery", "merge-candidate", "findings", "questions", "automation-ready",
                "single-step", "multi-step"]
    feature_options = "".join(f'<option value="{value}">{value}</option>' for value in features)
    status_options = "".join(f"<option>{value}</option>" for value in (
        "READY", "NEEDS_REVIEW", "BLOCKED", "BLOCKED_REQUIREMENT", "BLOCKED_IMPLEMENTATION_GAP",
        "BLOCKED_ENVIRONMENT", "BLOCKED_TEST_DATA", "BLOCKED_EXTERNAL_DEPENDENCY", "EXPLORATORY",
    ))
    lang = esc(index.get("output_locale", "pt-BR"))
    report = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(labels['report_title'])}</title>
<style>
:root {{ --ink:#182027; --muted:#5f6b73; --line:#d7dfe3; --surface:#fff; --soft:#f3f6f7; --accent:#087f5b; --warning:#9a6700; --danger:#b42318; --shadow:0 8px 24px rgba(26,43,52,.07); }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:var(--soft); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
body.modal-open {{ overflow:hidden; }}
.shell {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; }}
header {{ position:sticky; top:0; z-index:20; background:rgba(255,255,255,.97); border-bottom:1px solid var(--line); padding:18px 0 10px; }}
h1 {{ margin:0 0 4px; font-size:28px; }} h2 {{ margin:0 0 16px; font-size:22px; }} h3 {{ margin:0 0 8px; font-size:15px; }}
.muted,.empty,.subtitle {{ color:var(--muted); }}
nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }} nav a {{ padding:6px 10px; text-decoration:none; font-weight:650; color:inherit; }}
main {{ padding:24px 0 56px; }} main>section {{ padding:18px 0; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }}
.metric {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; box-shadow:var(--shadow); }}
.metric strong {{ display:block; font-size:22px; }} .metric span {{ color:var(--muted); font-size:13px; }}
.run-info {{ margin-top:12px; display:flex; gap:18px; flex-wrap:wrap; }}
.filter-panel {{ padding:14px; border:1px solid var(--line); border-radius:10px; background:#fff; margin-bottom:18px; }}
.filters {{ display:grid; grid-template-columns:minmax(200px,1fr) repeat(4,minmax(130px,190px)); gap:10px; }}
.bulk-controls {{ display:flex; justify-content:flex-end; gap:8px; margin-bottom:10px; }}
button {{ border:1px solid #aeb7bc; border-radius:5px; background:#fff; padding:6px 10px; font:inherit; cursor:pointer; }}
input,select {{ width:100%; min-height:38px; border:1px solid #aeb7bc; border-radius:4px; padding:7px 9px; font:inherit; background:#fff; }}
.tc-group {{ margin:18px 0 24px; }}
.tc-group-title {{ display:flex; align-items:center; gap:12px; padding:12px 14px; border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:8px; background:#fff; margin-bottom:10px; }}
.tc-group-title h3 {{ margin:0; font-size:17px; }} .tc-group-title span {{ color:var(--muted); font-size:12px; }} .group-toggle {{ margin-left:auto; }}
.tc-card {{ margin-bottom:10px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
.tc-card>summary {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 16px; cursor:pointer; font-weight:700; }}
.tc-heading {{ display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
.identifier-chips {{ display:inline-flex; gap:4px; flex-wrap:wrap; }}
.chip {{ border:1px solid #9fd8c6; background:#eaf7f2; color:#075e47; border-radius:4px; padding:1px 6px; font-size:11px; font-weight:700; }} .tc-id {{ color:var(--muted); font-size:13px; white-space:nowrap; }}
.badges {{ display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }}
.badge {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-size:11px; font-weight:750; white-space:nowrap; }}
.status-ready {{ color:#08633f; background:#eaf7f0; border-color:#b8dfc9; }} .status-needs_review {{ color:#765500; background:#fff6dd; }}
.status-exploratory,.test-basis,.dimension,.automation {{ color:#3949ab; background:#f0f1ff; border-color:#c5cae9; }}
[class*="status-blocked"] {{ color:#8f1d14; background:#fff0ee; }}
.tc-content {{ border-top:1px solid var(--line); padding:16px; }} .two-column {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
.related-requirements {{ color:var(--muted); font-size:13px; }}
.table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; background:#fff; margin-bottom:14px; }}
th,td {{ border:1px solid var(--line); padding:9px 11px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }} th {{ background:#f0f3f2; font-size:13px; }}
.step-number {{ width:48px; text-align:center; font-weight:700; }}
.flow-section {{ margin-top:16px; border:1px solid var(--line); border-radius:6px; background:#fbfcfc; padding:12px; }}
.flow-heading {{ display:flex; align-items:center; justify-content:space-between; }}
.mermaid-container {{ overflow-x:auto; background:#fff; }} .mermaid-svg {{ display:block; width:100%; min-width:520px; max-width:760px; margin:0 auto; }}
.node-label-title {{ font-weight:700; }}
.flow-modal {{ position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(20,29,34,.72); }}
.flow-modal-panel {{ width:min(1040px,100%); max-height:calc(100vh - 40px); overflow:auto; border-radius:6px; background:#fff; padding:16px; }}
.artifact-links {{ display:flex; gap:10px; }} .artifact-links a {{ border:1px solid #aeb7bc; border-radius:4px; padding:6px 10px; text-decoration:none; }}
.technical {{ margin-top:12px; color:var(--muted); font-size:13px; }}
.technical-grid {{ display:grid; grid-template-columns:max-content 1fr; gap:5px 12px; }} .technical-grid dt {{ font-weight:700; color:var(--ink); }} .technical-grid dd {{ margin:0; }}
.question-item,.finding-item {{ margin-bottom:10px; border:1px solid var(--line); border-left:4px solid var(--warning); border-radius:8px; background:#fff; padding:14px; }}
.question-item.blocking {{ border-left-color:var(--danger); }} .question-title,.finding-title {{ display:flex; justify-content:space-between; gap:12px; font-weight:700; }}
.needs-answer {{ color:var(--danger); font-weight:700; }}
.gates li {{ margin-bottom:6px; }}
[hidden] {{ display:none!important; }}
@media (max-width:720px) {{ .filters,.two-column {{ grid-template-columns:1fr; }} .tc-card>summary {{ flex-direction:column; align-items:flex-start; }} }}
@media print {{ header {{ position:static; }} nav,.filter-panel,.group-toggle,.expand-flow {{ display:none!important; }} .tc-group-body {{ display:block!important; }} }}
</style>
</head>
<body>
<header><div class="shell"><h1>{esc(labels['report_title'])}</h1><p class="subtitle">{esc(labels['report_subtitle'])}</p>
<nav><a href="#summary">{esc(labels['summary'])}</a><a href="#test-cases">{esc(labels['test_cases'])}</a><a href="#merge">{esc(labels['merge'])}</a><a href="#findings">{esc(labels['findings'])}</a><a href="#questions">{esc(labels['questions'])}</a><a href="#coverage">{esc(labels['coverage'])}</a><a href="#expansion">{esc(labels['expansion'])}</a><a href="#gates">{esc(labels['gates'])}</a></nav></div></header>
<main class="shell">
<section id="summary"><h2>{esc(labels['summary'])}</h2><div class="metrics">{metric_html}</div><div class="run-info">{''.join(f'<span>{item}</span>' for item in info)}</div></section>
<section id="test-cases"><h2>{esc(labels['test_cases'])}</h2><div class="filter-panel"><div class="bulk-controls"><button type="button" id="expand-all">{esc(labels['expand_all'])}</button><button type="button" id="collapse-all">{esc(labels['collapse_all'])}</button></div><div class="filters">
<label>{esc(labels['search'])}<input id="search" type="search"></label>
<label>{esc(labels['status'])}<select id="status-filter"><option value="">{esc(labels['all'])}</option>{status_options}</select></label>
<label>{esc(labels['priority'])}<select id="priority-filter"><option value="">{esc(labels['all'])}</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label>
<label>{esc(labels['family'])}<select id="family-filter"><option value="">{esc(labels['all'])}</option>{family_options}</select></label>
<label>{esc(labels['feature'])}<select id="feature-filter"><option value="">{esc(labels['all'])}</option>{feature_options}</select></label>
</div></div><div id="case-list">{''.join(groups_html)}</div><p id="no-results" hidden>{esc(labels['no_results'])}</p></section>
<section id="merge"><h2>{esc(labels['merge'])}</h2>{merge_html or f'<p class="empty">{esc(labels["no_merge"])}</p>'}</section>
<section id="findings"><h2>{esc(labels['findings'])}</h2>{finding_html or f'<p class="empty">{esc(labels["no_findings"])}</p>'}</section>
<section id="questions"><h2>{esc(labels['questions'])}</h2>{question_html or f'<p class="empty">{esc(labels["no_questions"])}</p>'}</section>
<section id="coverage"><h2>{esc(labels['coverage'])}</h2>{coverage_html}</section>
<section id="expansion"><h2>{esc(labels['expansion'])}</h2>{expansion_html}</section>
<section id="gates"><h2>{esc(labels['gates'])}</h2><ul class="gates">{gate_html or f'<li>{esc(labels["none"])}</li>'}</ul>{f'<h3>{esc(labels["gap_metrics"])}</h3><ul>{gap_html}</ul>' if gap_html else ''}</section>
</main>
<div id="flow-modal" class="flow-modal" role="dialog" aria-modal="true" hidden><div class="flow-modal-panel"><button type="button" class="modal-close">{esc(labels['close'])}</button><div id="flow-modal-canvas"></div></div></div>
<script>
const q=id=>document.getElementById(id);const controls=['search','status-filter','priority-filter','family-filter','feature-filter'].map(q);const cards=[...document.querySelectorAll('.tc-card')];const groups=[...document.querySelectorAll('.tc-group')];
function applyFilters(){{const term=q('search').value.trim().toLocaleLowerCase();let visible=0;cards.forEach(card=>{{const status=q('status-filter').value;const show=(!term||card.dataset.search.includes(term))&&(!status||card.dataset.status===status||(status==='BLOCKED'&&card.dataset.status.startsWith('BLOCKED')))&&(!q('priority-filter').value||card.dataset.priority===q('priority-filter').value)&&(!q('family-filter').value||card.dataset.family===q('family-filter').value)&&(!q('feature-filter').value||card.dataset.features.split(' ').includes(q('feature-filter').value));card.hidden=!show;if(show)visible+=1;}});groups.forEach(group=>{{group.hidden=![...group.querySelectorAll('.tc-card')].some(card=>!card.hidden);}});q('no-results').hidden=visible!==0;}}
controls.forEach(control=>control.addEventListener(control.id==='search'?'input':'change',applyFilters));
document.querySelectorAll('.group-toggle').forEach(button=>button.addEventListener('click',()=>{{const body=button.closest('.tc-group').querySelector('.tc-group-body');const expanded=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!expanded));button.textContent=expanded?{json.dumps(labels['expand'])}:{json.dumps(labels['collapse'])};body.hidden=expanded;}}));
function setAll(open){{document.querySelectorAll('.tc-group-body').forEach(body=>body.hidden=!open);cards.forEach(card=>card.open=open);}}
q('expand-all').addEventListener('click',()=>setAll(true));q('collapse-all').addEventListener('click',()=>setAll(false));
const modal=q('flow-modal');const canvas=q('flow-modal-canvas');function closeModal(){{modal.hidden=true;canvas.replaceChildren();document.body.classList.remove('modal-open');}}
document.querySelectorAll('.expand-flow').forEach(button=>button.addEventListener('click',()=>{{const svg=q(button.dataset.flowTarget).querySelector('svg');canvas.replaceChildren(svg.cloneNode(true));modal.hidden=false;document.body.classList.add('modal-open');}}));
modal.querySelector('.modal-close').addEventListener('click',closeModal);modal.addEventListener('click',event=>{{if(event.target===modal)closeModal();}});document.addEventListener('keydown',event=>{{if(event.key==='Escape')closeModal();}});
</script>
</body>
</html>
"""
    destination = Path(destination).resolve() if destination else output_dir / "report.html"
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="output", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        render_markdown(args.output)
        destination = render_report(args.output, args.destination)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: report generated at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
