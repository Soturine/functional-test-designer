#!/usr/bin/env python3
"""Render validated functional-test-designer output as one offline HTML report."""

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

from validate_output import validate  # noqa: E402
from render_markdown import extract_mermaid, mermaid_source  # noqa: E402
from requirement_groups import case_group, requirement_group_map  # noqa: E402


STATUS_LABELS = {
    "READY": "READY",
    "NEEDS_REVIEW": "NEEDS REVIEW",
    "BLOCKED": "BLOCKED",
}
PRIORITY_LABELS = {
    "CRITICAL": "Cr&iacute;tica",
    "HIGH": "Alta",
    "MEDIUM": "M&eacute;dia",
    "LOW": "Baixa",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_list(values: list[str], empty: str = "Nenhum") -> str:
    if not values:
        return f'<p class="empty">{empty}</p>'
    return "<ul>" + "".join(f"<li>{esc(value)}</li>" for value in values) + "</ul>"


def render_data(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Nenhum dado espec&iacute;fico.</p>'
    items = "".join(
        f'<li><strong>{esc(row.get("name", ""))}</strong>: {esc(row.get("description", ""))}</li>'
        for row in rows
    )
    return f"<ul>{items}</ul>"


def render_steps(steps: list[dict[str, Any]]) -> str:
    rows = []
    for step in steps:
        expected = step.get("expected_result")
        expected_html = esc(expected) if expected is not None else '<span class="needs-answer">A esclarecer</span>'
        rows.append(
            "<tr>"
            f'<td class="step-number">{esc(step.get("step", ""))}</td>'
            f'<td>{esc(step.get("action", ""))}</td>'
            f"<td>{expected_html}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="steps"><thead><tr>'
        '<th scope="col">#</th><th scope="col">A&ccedil;&atilde;o</th>'
        '<th scope="col">Resultado esperado</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def parse_mermaid_flow(source: str) -> list[tuple[str, str]]:
    terminal_pattern = re.compile(r"^\s+(S|F)\(\[(.*)\]\)$")
    node_pattern = re.compile(r'^\s+([ARC][0-9]+)\["(.*)"\]$')
    nodes: dict[str, str] = {}
    chains: list[list[str]] = []
    for line in source.splitlines():
        terminal = terminal_pattern.match(line)
        node = node_pattern.match(line)
        if terminal:
            nodes[terminal.group(1)] = terminal.group(2)
        elif node:
            nodes[node.group(1)] = node.group(2)
        elif line.strip().startswith("S -->"):
            chains.append([part.strip() for part in line.strip().split("-->")])
    if len(chains) != 1 or chains[0][0] != "S" or chains[0][-1] != "F":
        raise ValueError("Mermaid flow must contain one Start-to-End chain")
    if any(node_id not in nodes for node_id in chains[0]):
        raise ValueError("Mermaid flow chain references an unknown node")
    return [(node_id, nodes[node_id]) for node_id in chains[0]]


def render_mermaid_svg(source: str, flow_id: str) -> str:
    nodes = parse_mermaid_flow(source)
    canvas_width = 720
    regular_width = 600
    terminal_width = 160
    gap = 34
    y = 24
    layout: list[dict[str, Any]] = []
    for node_id, label in nodes:
        lines = label.split("<br/>")
        terminal = node_id in {"S", "F"}
        height = 50 if terminal else max(72, 30 + 20 * len(lines))
        width = terminal_width if terminal else regular_width
        layout.append(
            {
                "id": node_id,
                "lines": lines,
                "x": (canvas_width - width) / 2,
                "y": y,
                "width": width,
                "height": height,
            }
        )
        y += height + gap
    canvas_height = y - gap + 24
    marker_id = "arrow-" + re.sub(r"[^a-zA-Z0-9_-]", "-", flow_id)
    connectors = []
    for previous, current in zip(layout, layout[1:]):
        x = canvas_width / 2
        connectors.append(
            f'<line x1="{x:g}" y1="{previous["y"] + previous["height"]:g}" '
            f'x2="{x:g}" y2="{current["y"] - 7:g}" stroke="#64748b" stroke-width="1.5" '
            f'marker-end="url(#{marker_id})" />'
        )

    shapes = []
    palette = {
        "terminal": ("#f8fafc", "#475569", "#0f172a"),
        "action": ("#eff6ff", "#2563eb", "#0f172a"),
        "expected": ("#f0fdf4", "#16a34a", "#14532d"),
        "clarification": ("#fff7ed", "#ea580c", "#7c2d12"),
    }
    for item in layout:
        node_id = item["id"]
        kind = (
            "terminal"
            if node_id in {"S", "F"}
            else "action"
            if node_id.startswith("A")
            else "clarification"
            if node_id.startswith("C")
            else "expected"
        )
        fill, stroke, color = palette[kind]
        dash = ' stroke-dasharray="4 3"' if kind == "clarification" else ""
        radius = item["height"] / 2 if kind == "terminal" else 8
        line_count = len(item["lines"])
        first_y = item["y"] + item["height"] / 2 - (line_count - 1) * 10
        tspans = []
        for position, line in enumerate(item["lines"]):
            css_class = ' class="node-label-title"' if position == 0 and line_count > 1 else ""
            dy = "0" if position == 0 else "20"
            tspans.append(
                f'<tspan x="{canvas_width / 2:g}" dy="{dy}"{css_class}>{esc(line)}</tspan>'
            )
        shapes.append(
            f'<g class="mermaid-node mermaid-{kind}" data-node-id="{esc(node_id)}">'
            f'<rect x="{item["x"]:g}" y="{item["y"]:g}" width="{item["width"]:g}" '
            f'height="{item["height"]:g}" rx="{radius:g}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1.5"{dash} />'
            f'<text x="{canvas_width / 2:g}" y="{first_y:g}" text-anchor="middle" '
            f'fill="{color}" font-family="system-ui, sans-serif" font-size="14">'
            + "".join(tspans)
            + "</text></g>"
        )
    return (
        f'<svg class="mermaid-svg" viewBox="0 0 {canvas_width} {canvas_height:g}" '
        'role="img" aria-label="Fluxo linear do teste" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" /></marker></defs>'
        + "".join(connectors)
        + "".join(shapes)
        + "</svg>"
    )


def render_flow(source: str, flow_id: str) -> tuple[str, bool]:
    try:
        visual = render_mermaid_svg(source, flow_id)
        body = f'<div class="mermaid-container" id="{esc(flow_id)}">{visual}</div>'
        expandable = True
    except ValueError:
        body = (
            '<div class="flow-error" role="status">N&atilde;o foi poss&iacute;vel renderizar este fluxo. '
            'Consulte a tabela de passos ou o Markdown.</div>'
        )
        expandable = False
    return body + f'<pre class="mermaid-source" hidden>{esc(source)}</pre>', expandable


def render_case(
    case: dict[str, Any],
    entry: dict[str, Any],
    mermaid: str,
    requirement_group: str | None = None,
    related_groups: list[str] | None = None,
) -> str:
    status = case["status"]
    priority = case["priority"]
    search_text = " ".join(
        [
            case["id"],
            case["title"],
            case["objective"],
            " ".join(case.get("tags", [])),
            requirement_group or "",
            " ".join(related_groups or []),
        ]
    ).casefold()
    technical = (
        f'Requisitos: {", ".join(case["requirement_refs"])} | '
        f'Cen&aacute;rios: {", ".join(case["scenario_refs"])} | '
        f'Coverage Points: {", ".join(case["coverage_point_refs"])}'
    )
    group_badge = (
        f'<span class="badge requirement-group">{esc(requirement_group)}</span>'
        if requirement_group
        else ""
    )
    related_html = (
        f'    <p class="related-requirements"><strong>Related requirements:</strong> {esc(", ".join(related_groups))}</p>\n'
        if related_groups
        else ""
    )
    artifacts = (
        f'<a href="{esc(entry["file"])}">JSON</a>'
        f'<a href="{esc(entry["markdown_file"])}">Markdown</a>'
    )
    flow_id = f"flow-{case['id']}"
    flow, expandable = render_flow(mermaid, flow_id)
    expand_button = (
        f'<button type="button" class="expand-flow" data-flow-target="{esc(flow_id)}" '
        f'aria-label="Ampliar fluxo do {esc(case["id"])}">Ampliar fluxo</button>'
        if expandable
        else ""
    )
    return f"""
<details class="tc-card" data-status="{esc(status)}" data-priority="{esc(priority)}" data-search="{esc(search_text)}">
  <summary>
    <span class="tc-heading"><span class="tc-id">{esc(case['id'])}</span>{esc(case['title'])}</span>
    <span class="badges">{group_badge}<span class="badge status-{esc(status.lower())}">{STATUS_LABELS[status]}</span><span class="badge priority">{PRIORITY_LABELS[priority]}</span></span>
  </summary>
  <div class="tc-content">
    <section><h3>Objetivo</h3><p>{esc(case['objective'])}</p></section>
{related_html}    <div class="two-column">
      <section><h3>Pr&eacute;-condi&ccedil;&otilde;es</h3>{render_list(case.get('preconditions', []))}</section>
      <section><h3>Dados</h3>{render_data(case.get('test_data', []))}</section>
    </div>
    <section><h3>Passos</h3>{render_steps(case['steps'])}</section>
    <section class="flow-section"><div class="flow-heading"><h3>Fluxo do Teste</h3>{expand_button}</div>{flow}</section>
    <section><h3>Artefatos</h3><div class="artifact-links">{artifacts}</div></section>
    <details class="technical"><summary>Detalhes t&eacute;cnicos</summary><p>{technical}</p></details>
  </div>
</details>"""


def render_question(question: dict[str, Any]) -> str:
    blocking = "Sim" if question["blocking"] else "N&atilde;o"
    cases = ", ".join(question["related_test_cases"]) or "Nenhum TC criado"
    return f"""
<article class="question-item {'blocking' if question['blocking'] else ''}">
  <div class="question-title"><span>{esc(question['question'])}</span><span class="badge">Bloqueante: {blocking}</span></div>
  <p><strong>Motivo:</strong> {esc(question['reason'])}</p>
  <p><strong>TCs impactados:</strong> {esc(cases)}</p>
  <details class="technical"><summary>Detalhes t&eacute;cnicos</summary><p>{esc(question['id'])} | {esc(', '.join(question['requirement_refs']))}</p></details>
</article>"""


def render_coverage(
    requirements: list[dict[str, Any]],
    coverage_points: list[dict[str, Any]],
    entries_by_id: dict[str, dict[str, Any]],
    questions_by_id: dict[str, dict[str, Any]],
) -> str:
    by_requirement: dict[str, list[dict[str, Any]]] = {}
    for coverage_point in coverage_points:
        by_requirement.setdefault(coverage_point["requirement_ref"], []).append(coverage_point)

    blocks = []
    for requirement in requirements:
        items = []
        for coverage_point in by_requirement.get(requirement["id"], []):
            disposition = coverage_point["disposition"]
            if disposition == "TEST_CASE":
                marker = "&#10003;"
                destinations = [entries_by_id[target]["title"] for target in coverage_point["target_refs"]]
                destination_text = "TC: " + "; ".join(destinations)
            elif disposition == "QUESTION":
                marker = "?"
                destinations = [questions_by_id[target]["question"] for target in coverage_point["target_refs"]]
                destination_text = "Pergunta: " + "; ".join(destinations)
            else:
                marker = "&ndash;"
                destination_text = "Fora do escopo: " + coverage_point.get("reason", "")
            items.append(
                f'<li class="coverage-{esc(disposition.lower())}"><span class="coverage-marker">{marker}</span>'
                f'<div><strong>{esc(coverage_point["statement"])}</strong><span>{esc(destination_text)}</span>'
                f'<details class="technical"><summary>Detalhes t&eacute;cnicos</summary><p>{esc(coverage_point["id"])}</p></details></div></li>'
            )
        blocks.append(
            f'<section class="requirement-block"><h3>{esc(requirement["statement"])}</h3>'
            f'<p class="requirement-source">{esc(requirement["source_refs"][0]["reference"])}</p>'
            f'<ul class="coverage-list">{"".join(items)}</ul></section>'
        )
    return "".join(blocks)


def render_report(output_dir: Path, destination: Path | None = None) -> Path:
    output_dir = output_dir.resolve()
    errors = validate(output_dir)
    if errors:
        raise ValueError("Output validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    index = read_json(output_dir / "test-cases.json")
    questions_doc = read_json(output_dir / "questions.json")
    cases = [read_json(output_dir / entry["file"]) for entry in index["test_cases"]]
    mermaid_by_id: dict[str, str] = {}
    for entry, case in zip(index["test_cases"], cases):
        markdown_path = output_dir / entry["markdown_file"]
        try:
            markdown = markdown_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"Missing Markdown artifact for {entry['id']}: {entry['markdown_file']}") from exc
        source = extract_mermaid(markdown)
        if source != mermaid_source(case):
            raise ValueError(f"Markdown Mermaid flow differs from JSON steps for {entry['id']}")
        mermaid_by_id[entry["id"]] = source
    questions = questions_doc["questions"]
    status_counts = Counter(case["status"] for case in cases)
    entries_by_id = {entry["id"]: entry for entry in index["test_cases"]}
    questions_by_id = {question["id"]: question for question in questions}
    coverage_points = index["coverage_points"]
    covered_count = sum(
        bool(item["target_refs"]) or item["disposition"] == "OUT_OF_SCOPE"
        for item in coverage_points
    )
    blocking_count = sum(bool(question["blocking"]) for question in questions)
    warning = (
        f'<div class="alert"><strong>Aten&ccedil;&atilde;o:</strong> {blocking_count} pergunta(s) bloqueante(s) requerem decis&atilde;o.</div>'
        if blocking_count or status_counts["BLOCKED"]
        else ""
    )
    groups = requirement_group_map(index["requirements"])
    requirement_order = {
        requirement["id"]: position for position, requirement in enumerate(index["requirements"])
    }
    grouped_cases: dict[str, list[tuple[tuple[int, str], dict[str, Any], dict[str, Any], list[str]]]] = {}
    for entry, case in zip(index["test_cases"], cases):
        group, related, sort_key = case_group(case, groups, requirement_order)
        grouped_cases.setdefault(group, []).append((sort_key, entry, case, related))
    case_groups = []
    for group, members in sorted(grouped_cases.items(), key=lambda item: min(member[0] for member in item[1])):
        cards = "".join(
            render_case(case, entry, mermaid_by_id[case["id"]], group, related)
            for _, entry, case, related in sorted(members, key=lambda member: member[0])
        )
        case_groups.append(
            f'<section class="tc-group" data-requirement-group="{esc(group)}">'
            f'<h3 class="tc-group-title">{esc(group)}</h3>{cards}</section>'
        )
    case_html = "".join(case_groups)
    question_html = "".join(render_question(question) for question in questions)
    coverage_html = render_coverage(
        index["requirements"], coverage_points, entries_by_id, questions_by_id
    )

    report = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Functional Test Report</title>
<style>
:root {{ --ink:#202427; --muted:#667078; --line:#d9dfe2; --surface:#fff; --soft:#f4f6f5; --accent:#087f5b; --warning:#9a6700; --danger:#b42318; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; overflow-x:hidden; color:var(--ink); background:var(--soft); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; letter-spacing:0; }}
body.modal-open {{ overflow:hidden; }}
a {{ color:inherit; }}
.shell {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; }}
header {{ background:#fff; border-bottom:1px solid var(--line); padding:28px 0 18px; }}
h1 {{ margin:0 0 4px; font-size:30px; }}
.subtitle,.empty,.requirement-source {{ color:var(--muted); }}
nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:20px; }}
nav a {{ padding:7px 10px; border-bottom:2px solid transparent; text-decoration:none; font-weight:650; }}
nav a:hover {{ border-color:var(--accent); }}
main {{ padding:24px 0 56px; }}
main>section {{ padding:20px 0; scroll-margin-top:12px; }}
h2 {{ margin:0 0 16px; font-size:22px; }}
h3 {{ margin:0 0 8px; font-size:15px; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:10px; }}
.metric {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:14px; }}
.metric strong {{ display:block; font-size:24px; }}
.metric span {{ color:var(--muted); font-size:13px; }}
.alert {{ margin-top:14px; padding:12px 14px; background:#fff6dd; border-left:4px solid var(--warning); }}
.filters {{ display:grid; grid-template-columns:minmax(220px,1fr) 180px 180px; gap:10px; margin-bottom:14px; }}
input,select {{ width:100%; min-height:40px; border:1px solid #aeb7bc; border-radius:4px; background:#fff; padding:8px 10px; font:inherit; }}
.tc-card {{ margin-bottom:10px; border:1px solid var(--line); border-radius:6px; background:#fff; }}
.tc-group {{ margin:18px 0 24px; }}
.tc-group-title {{ margin:0 0 10px; padding-bottom:7px; border-bottom:2px solid var(--accent); font-size:17px; }}
.requirement-group {{ color:#075e47; border-color:#9fd8c6; background:#eaf7f2; }}
.related-requirements {{ color:var(--muted); font-size:13px; }}
.tc-card>summary {{ display:flex; align-items:center; justify-content:space-between; gap:16px; min-height:58px; padding:12px 16px; cursor:pointer; font-weight:700; }}
.tc-heading {{ display:flex; gap:10px; align-items:baseline; }}
.tc-id {{ color:var(--muted); font-size:13px; white-space:nowrap; }}
.badges {{ display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }}
.badge {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:11px; font-weight:750; white-space:nowrap; }}
.status-ready {{ color:#08633f; background:#eaf7f0; border-color:#b8dfc9; }}
.status-needs_review {{ color:#765500; background:#fff6dd; border-color:#ead28e; }}
.status-blocked {{ color:#8f1d14; background:#fff0ee; border-color:#efb8b2; }}
.tc-content {{ border-top:1px solid var(--line); padding:16px; }}
.two-column {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
ul {{ margin:6px 0 14px; padding-left:20px; }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; background:#fff; }}
th,td {{ border:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
th {{ background:#f0f3f2; font-size:13px; }}
.step-number {{ width:48px; text-align:center; font-weight:700; }}
.flow-section {{ margin-top:18px; border:1px solid var(--line); border-radius:6px; background:#fbfcfc; padding:14px; }}
.flow-heading {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }}
.flow-heading h3 {{ margin:0; }}
.expand-flow,.modal-close {{ min-height:36px; border:1px solid #aeb7bc; border-radius:4px; background:#fff; color:var(--ink); padding:7px 10px; font:inherit; font-weight:650; cursor:pointer; }}
.expand-flow:hover,.expand-flow:focus-visible,.modal-close:hover,.modal-close:focus-visible {{ border-color:var(--accent); color:var(--accent); outline:2px solid transparent; }}
.mermaid-container {{ width:100%; overflow-x:auto; padding:8px; background:#fff; border:1px solid #e5e9eb; border-radius:4px; }}
.mermaid-svg {{ display:block; width:100%; min-width:560px; max-width:760px; height:auto; margin:0 auto; }}
.node-label-title {{ font-weight:700; }}
.flow-error {{ padding:12px; border-left:4px solid var(--warning); background:#fff6dd; color:#684b00; }}
.flow-modal {{ position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(20,29,34,.72); }}
.flow-modal-panel {{ display:flex; flex-direction:column; width:min(1040px,100%); max-height:calc(100vh - 40px); border-radius:6px; background:#fff; box-shadow:0 18px 55px rgba(0,0,0,.28); }}
.flow-modal-header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 16px; border-bottom:1px solid var(--line); }}
.flow-modal-header h2 {{ margin:0; font-size:18px; }}
.flow-modal-canvas {{ overflow:auto; padding:20px; }}
.flow-modal-canvas .mermaid-svg {{ min-width:720px; max-width:900px; }}
.artifact-links {{ display:flex; gap:10px; flex-wrap:wrap; }}
.artifact-links a {{ border:1px solid #aeb7bc; border-radius:4px; padding:7px 10px; text-decoration:none; font-weight:650; }}
.artifact-links a:hover {{ border-color:var(--accent); color:var(--accent); }}
.technical {{ margin-top:12px; color:var(--muted); font-size:13px; }}
.technical>summary {{ cursor:pointer; }}
.question-item,.requirement-block {{ margin-bottom:10px; border:1px solid var(--line); border-radius:6px; background:#fff; padding:16px; }}
.question-item.blocking {{ border-left:4px solid var(--danger); }}
.question-title {{ display:flex; justify-content:space-between; gap:14px; font-weight:750; }}
.coverage-list {{ list-style:none; padding:0; margin:12px 0 0; }}
.coverage-list>li {{ display:flex; gap:10px; padding:10px 0; border-top:1px solid #edf0f1; }}
.coverage-list span {{ display:block; color:var(--muted); }}
.coverage-marker {{ flex:0 0 22px; color:var(--accent)!important; font-size:18px; font-weight:800; }}
.needs-answer {{ color:var(--danger); font-weight:700; }}
[hidden] {{ display:none!important; }}
@media (max-width:720px) {{ .shell {{ width:min(100% - 20px,1180px); }} .filters,.two-column {{ grid-template-columns:1fr; }} .tc-card>summary,.question-title {{ align-items:flex-start; flex-direction:column; }} .badges {{ justify-content:flex-start; }} .flow-section {{ padding:10px; }} .flow-heading {{ align-items:flex-start; flex-direction:column; }} .flow-modal {{ padding:8px; }} .flow-modal-panel {{ max-height:calc(100vh - 16px); }} .flow-modal-canvas {{ padding:10px; }} }}
</style>
</head>
<body>
<header><div class="shell"><h1>Functional Test Report</h1><p class="subtitle">Casos manuais derivados das fontes explicitamente selecionadas.</p><nav aria-label="Relat&oacute;rio"><a href="#resumo">Resumo</a><a href="#test-cases">Test Cases</a><a href="#perguntas">Perguntas</a><a href="#cobertura">Cobertura</a></nav></div></header>
<main class="shell">
<section id="resumo"><h2>Resumo</h2><div class="metrics">
<div class="metric"><strong>{len(cases)}</strong><span>Total de TCs</span></div>
<div class="metric"><strong>{status_counts['READY']}</strong><span>READY</span></div>
<div class="metric"><strong>{status_counts['NEEDS_REVIEW']}</strong><span>NEEDS REVIEW</span></div>
<div class="metric"><strong>{status_counts['BLOCKED']}</strong><span>BLOCKED</span></div>
<div class="metric"><strong>{len(questions)}</strong><span>Perguntas</span></div>
<div class="metric"><strong>{len(index['requirements'])}</strong><span>Requisitos</span></div>
<div class="metric"><strong>{len(index['scenarios'])}</strong><span>Cen&aacute;rios</span></div>
<div class="metric"><strong>{len(coverage_points)}</strong><span>Coverage Points</span></div>
<div class="metric"><strong>{covered_count}/{len(coverage_points)}</strong><span>Cobertura com destino</span></div>
</div>{warning}</section>
<section id="test-cases"><h2>Test Cases</h2><div class="filters"><label>Buscar<input id="search" type="search" placeholder="T&iacute;tulo, objetivo ou tag"></label><label>Status<select id="status-filter"><option value="">Todos</option><option>READY</option><option>NEEDS_REVIEW</option><option>BLOCKED</option></select></label><label>Prioridade<select id="priority-filter"><option value="">Todas</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label></div><div id="case-list">{case_html}</div><p id="no-results" hidden>Nenhum Test Case corresponde aos filtros.</p></section>
<section id="perguntas"><h2>Perguntas</h2>{question_html or '<p class="empty">Nenhuma pergunta pendente.</p>'}</section>
<section id="cobertura"><h2>Cobertura</h2>{coverage_html}</section>
</main>
<div id="flow-modal" class="flow-modal" role="dialog" aria-modal="true" aria-labelledby="flow-modal-title" hidden>
  <div class="flow-modal-panel">
    <div class="flow-modal-header"><h2 id="flow-modal-title">Fluxo do Teste</h2><button type="button" class="modal-close" aria-label="Fechar fluxo ampliado">Fechar</button></div>
    <div id="flow-modal-canvas" class="flow-modal-canvas"></div>
  </div>
</div>
<script>
const search=document.getElementById('search');const statusFilter=document.getElementById('status-filter');const priorityFilter=document.getElementById('priority-filter');const cards=[...document.querySelectorAll('.tc-card')];const groups=[...document.querySelectorAll('.tc-group')];const noResults=document.getElementById('no-results');
function applyFilters(){{const term=search.value.trim().toLocaleLowerCase();let visible=0;cards.forEach(card=>{{const show=(!term||card.dataset.search.includes(term))&&(!statusFilter.value||card.dataset.status===statusFilter.value)&&(!priorityFilter.value||card.dataset.priority===priorityFilter.value);card.hidden=!show;if(show)visible+=1;}});groups.forEach(group=>{{group.hidden=![...group.querySelectorAll('.tc-card')].some(card=>!card.hidden);}});noResults.hidden=visible!==0;}}
[search,statusFilter,priorityFilter].forEach(control=>control.addEventListener(control===search?'input':'change',applyFilters));
const flowModal=document.getElementById('flow-modal');const flowCanvas=document.getElementById('flow-modal-canvas');const flowClose=flowModal.querySelector('.modal-close');let flowTrigger=null;
function closeFlowModal(){{if(flowModal.hidden)return;flowModal.hidden=true;flowCanvas.replaceChildren();document.body.classList.remove('modal-open');if(flowTrigger)flowTrigger.focus();}}
document.querySelectorAll('.expand-flow').forEach(button=>button.addEventListener('click',()=>{{const source=document.getElementById(button.dataset.flowTarget);const svg=source&&source.querySelector('svg');if(!svg)return;flowTrigger=button;flowCanvas.replaceChildren(svg.cloneNode(true));flowModal.hidden=false;document.body.classList.add('modal-open');flowClose.focus();}}));
flowClose.addEventListener('click',closeFlowModal);flowModal.addEventListener('click',event=>{{if(event.target===flowModal)closeFlowModal();}});document.addEventListener('keydown',event=>{{if(event.key==='Escape')closeFlowModal();}});
</script>
</body>
</html>
"""
    destination = destination.resolve() if destination else output_dir / "report.html"
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="output", type=Path, help="validated output directory")
    parser.add_argument("--destination", type=Path, help="HTML path; defaults to OUTPUT/report.html")
    args = parser.parse_args()
    try:
        destination = render_report(args.output, args.destination)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: report generated at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
