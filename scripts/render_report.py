#!/usr/bin/env python3
"""Render validated functional-test-designer output as one offline HTML report."""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_output import validate  # noqa: E402


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


def render_case(case: dict[str, Any]) -> str:
    status = case["status"]
    priority = case["priority"]
    search_text = " ".join(
        [case["id"], case["title"], case["objective"], " ".join(case.get("tags", []))]
    ).casefold()
    technical = (
        f'Requisitos: {", ".join(case["requirement_refs"])} | '
        f'Cen&aacute;rios: {", ".join(case["scenario_refs"])} | '
        f'Coverage Points: {", ".join(case["coverage_point_refs"])}'
    )
    return f"""
<details class="tc-card" data-status="{esc(status)}" data-priority="{esc(priority)}" data-search="{esc(search_text)}">
  <summary>
    <span class="tc-heading"><span class="tc-id">{esc(case['id'])}</span>{esc(case['title'])}</span>
    <span class="badges"><span class="badge status-{esc(status.lower())}">{STATUS_LABELS[status]}</span><span class="badge priority">{PRIORITY_LABELS[priority]}</span></span>
  </summary>
  <div class="tc-content">
    <section><h3>Objetivo</h3><p>{esc(case['objective'])}</p></section>
    <div class="two-column">
      <section><h3>Pr&eacute;-condi&ccedil;&otilde;es</h3>{render_list(case.get('preconditions', []))}</section>
      <section><h3>Dados</h3>{render_data(case.get('test_data', []))}</section>
    </div>
    <section><h3>Passos</h3>{render_steps(case['steps'])}</section>
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
    case_html = "".join(render_case(case) for case in cases)
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
body {{ margin:0; color:var(--ink); background:var(--soft); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; letter-spacing:0; }}
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
@media (max-width:720px) {{ .shell {{ width:min(100% - 20px,1180px); }} .filters,.two-column {{ grid-template-columns:1fr; }} .tc-card>summary,.question-title {{ align-items:flex-start; flex-direction:column; }} .badges {{ justify-content:flex-start; }} }}
</style>
</head>
<body>
<header><div class="shell"><h1>Functional Test Report</h1><p class="subtitle">Casos manuais derivados exclusivamente do documento de requisitos.</p><nav aria-label="Relat&oacute;rio"><a href="#resumo">Resumo</a><a href="#test-cases">Test Cases</a><a href="#perguntas">Perguntas</a><a href="#cobertura">Cobertura</a></nav></div></header>
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
<script>
const search=document.getElementById('search');const statusFilter=document.getElementById('status-filter');const priorityFilter=document.getElementById('priority-filter');const cards=[...document.querySelectorAll('.tc-card')];const noResults=document.getElementById('no-results');
function applyFilters(){{const term=search.value.trim().toLocaleLowerCase();let visible=0;cards.forEach(card=>{{const show=(!term||card.dataset.search.includes(term))&&(!statusFilter.value||card.dataset.status===statusFilter.value)&&(!priorityFilter.value||card.dataset.priority===priorityFilter.value);card.hidden=!show;if(show)visible+=1;}});noResults.hidden=visible!==0;}}
[search,statusFilter,priorityFilter].forEach(control=>control.addEventListener(control===search?'input':'change',applyFilters));
</script>
</body>
</html>
"""
    destination = destination.resolve() if destination else output_dir / "report.html"
    destination.write_text(report, encoding="utf-8")
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
