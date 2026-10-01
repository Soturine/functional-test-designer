#!/usr/bin/env python3
"""FTD ADR outputs: what one ADR round changed, for QA and non-QA reviewers alike.

Written to `<artifact_root>/output/adr/<adr-id>/` from the round's validated state only, in the
parent run's output locale: JSON for tools, `adr-summary.md`, an offline self-contained
`adr-report.html`, and the local Azure ADR delta under `azure/`. The normal suite report is not
re-rendered and stays the canonical one.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from common import file_digest, read_json, write_json

LABELS = {
    "en": {
        "title": "ADR review", "baseline": "Baseline", "round": "ADR round", "previous": "Builds on",
        "sources": "ADR files", "read": "read", "reused": "reused", "new": "new", "changed": "changed",
        "unsupported": "unsupported", "failed": "failed", "removed": "removed from selection",
        "decisions": "Decisions", "direct": "Directly affected", "indirect": "Indirectly affected",
        "updates": "Proposed updates", "creates": "Proposed new", "review": "Need review", "blocked": "Blocked",
        "superseded": "Superseded", "questions": "Questions", "findings": "Findings", "unaffected": "Unaffected",
        "statements": "ADR evidence catalog", "decision": "Decision", "relationship": "Relationship",
        "previous_rule": "Previous rule", "evidence": "Evidence", "affected": "Affected Test Cases",
        "action": "ADR action", "impact": "Impact", "status": "Execution status", "reason": "Reason",
        "before": "Before", "after": "After", "changed_fields": "Changed", "unchanged_fields": "Unchanged",
        "procedure": "Procedure", "step": "Step", "expected": "Expected result", "claims": "Testable claims",
        "dimensions": "Targeted expansion", "lineage": "Lineage", "blocking": "Blocking", "yes": "Yes", "no": "No",
        "preconditions": "Preconditions", "test_data": "Test data", "cleanup": "Cleanup", "metrics": "Metrics",
        "azure": "Local Azure delta (never published automatically)", "requirements": "Affected requirements",
        "dispositions": "Existing Questions and Findings", "none": "None.",
    },
    "pt": {
        "title": "Revisão de ADR", "baseline": "Base", "round": "Rodada ADR", "previous": "Parte de",
        "sources": "Arquivos de ADR", "read": "lidos", "reused": "reaproveitados", "new": "novos", "changed": "alterados",
        "unsupported": "não suportados", "failed": "com falha", "removed": "removidos da seleção",
        "decisions": "Decisões", "direct": "Afetados diretamente", "indirect": "Afetados indiretamente",
        "updates": "Atualizações propostas", "creates": "Novos propostos", "review": "Precisam de revisão",
        "blocked": "Bloqueados", "superseded": "Substituídos", "questions": "Questions", "findings": "Findings",
        "unaffected": "Não afetados", "statements": "Catálogo de evidências do ADR", "decision": "Decisão",
        "relationship": "Relação", "previous_rule": "Regra anterior", "evidence": "Evidência",
        "affected": "Test Cases afetados", "action": "Ação do ADR", "impact": "Impacto", "status": "Status de execução",
        "reason": "Motivo", "before": "Antes", "after": "Depois", "changed_fields": "Alterado",
        "unchanged_fields": "Sem alteração", "procedure": "Procedimento", "step": "Passo", "expected": "Resultado esperado",
        "claims": "Comportamentos testáveis", "dimensions": "Expansão direcionada", "lineage": "Linhagem",
        "blocking": "Bloqueante", "yes": "Sim", "no": "Não", "preconditions": "Pré-condições", "test_data": "Dados de teste",
        "cleanup": "Limpeza", "metrics": "Métricas", "azure": "Delta local do Azure (nunca publicado automaticamente)",
        "requirements": "Requisitos afetados", "dispositions": "Questions e Findings existentes", "none": "Nenhum.",
    },
    "es": {
        "title": "Revisión de ADR", "baseline": "Base", "round": "Ronda ADR", "previous": "Parte de",
        "sources": "Archivos de ADR", "read": "leídos", "reused": "reutilizados", "new": "nuevos", "changed": "modificados",
        "unsupported": "no soportados", "failed": "con error", "removed": "quitados de la selección",
        "decisions": "Decisiones", "direct": "Afectados directamente", "indirect": "Afectados indirectamente",
        "updates": "Actualizaciones propuestas", "creates": "Nuevos propuestos", "review": "Requieren revisión",
        "blocked": "Bloqueados", "superseded": "Reemplazados", "questions": "Questions", "findings": "Findings",
        "unaffected": "No afectados", "statements": "Catálogo de evidencias del ADR", "decision": "Decisión",
        "relationship": "Relación", "previous_rule": "Regla anterior", "evidence": "Evidencia",
        "affected": "Test Cases afectados", "action": "Acción del ADR", "impact": "Impacto",
        "status": "Estado de ejecución", "reason": "Motivo", "before": "Antes", "after": "Después",
        "changed_fields": "Cambiado", "unchanged_fields": "Sin cambios", "procedure": "Procedimiento", "step": "Paso",
        "expected": "Resultado esperado", "claims": "Comportamientos verificables", "dimensions": "Expansión dirigida",
        "lineage": "Linaje", "blocking": "Bloqueante", "yes": "Sí", "no": "No", "preconditions": "Precondiciones",
        "test_data": "Datos de prueba", "cleanup": "Limpieza", "metrics": "Métricas",
        "azure": "Delta local de Azure (nunca se publica automáticamente)", "requirements": "Requisitos afectados",
        "dispositions": "Questions y Findings existentes", "none": "Ninguno.",
    },
}


def labels_for(locale: str) -> dict[str, str]:
    return LABELS.get(str(locale or "en").split("-")[0].lower(), LABELS["en"])


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def publish(run_dir: Path, round_dir: Path, document: dict[str, Any], base: dict[str, Any], analysis: dict[str, Any],
            built: dict[str, Any], entries: list[dict[str, Any]], metrics: dict[str, Any], delta: dict[str, Any],
            lineage: dict[str, Any]) -> dict[str, dict[str, str]]:
    import adr_azure
    adr_id = document["adr_run_id"]
    artifact_root = Path(read_json(Path(run_dir) / "run.json")["artifact_root"])
    destination = artifact_root / "output" / "adr" / adr_id
    view = report_model(document, base, analysis, built, entries, metrics, lineage)
    documents = {
        "adr-analysis.json": {"adr_run_id": adr_id, "lineage": view["lineage"], "metrics": metrics,
                              "sources": entries, "statements": analysis["statements"],
                              "dimension_reviews": analysis["dimension_reviews"]},
        "adr-decisions.json": {"adr_run_id": adr_id, "decisions": analysis["decisions"],
                               "ledger": [d["id"] for d in document["decisions"]]},
        "affected-test-cases.json": {"adr_run_id": adr_id, "test_cases": view["affected"],
                                     "unaffected_cases": metrics["unaffected_cases"]},
        "proposed-test-cases.json": {"adr_run_id": adr_id, "test_cases": [built["cases"][k] for k in sorted(built["cases"])]},
        "procedure-changes.json": {"adr_run_id": adr_id, "changes": built["changes"]},
        "questions.json": {"adr_run_id": adr_id, "new": [q for q in document["questions"]
                                                         if q["id"] in {x["id"] for x in analysis["questions"]}],
                           "dispositions": analysis["question_dispositions"]},
        "findings.json": {"adr_run_id": adr_id, "new": [f for f in document["findings"]
                                                        if f["id"] in {x["id"] for x in analysis["findings"]}],
                          "dispositions": analysis["finding_dispositions"]},
        "azure/azure-adr-export-package.json": delta,
        "azure/azure-adr-preview.json": adr_azure.local_preview(delta),
    }
    staging = destination.with_name(f".{adr_id}.staging")
    if staging.exists():
        import shutil
        shutil.rmtree(staging)
    for name, value in documents.items():
        write_json(staging / name, value)
    (staging / "adr-summary.md").write_text(summary_markdown(view), encoding="utf-8")
    (staging / "adr-report.html").write_text(report_html(view), encoding="utf-8")
    names = sorted(p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file())
    write_json(staging / "adr-manifest.json", {
        "adr_run_id": adr_id, "parent_run_id": Path(run_dir).name,
        "parent_canonical_digest": document["parent"]["canonical_digest"],
        "previous_adr_id": document["previous_adr_id"], "effective_digest": document["effective_digest"],
        "files": {name: file_digest(staging / name) for name in names}})
    if destination.exists():
        import shutil
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(destination)
    return {name: {"path": str(destination / name), "digest": file_digest(destination / name)}
            for name in [*names, "adr-manifest.json"]}


def report_model(document: dict[str, Any], base: dict[str, Any], analysis: dict[str, Any], built: dict[str, Any],
                 entries: list[dict[str, Any]], metrics: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    cases = {c["id"]: c for c in [*base["cases"], *document["cases"]]}
    affected = []
    for entry in analysis["test_cases"]:
        case = built["cases"].get(entry["id"]) or cases[entry["id"]]
        affected.append({"id": entry["id"], "title": case["title"], "action": entry["action"], "impact": entry["impact"],
                         "status": case["status"], "decisions": entry["decisions"], "reason": entry["reason"],
                         "supersedes": document["case_states"][entry["id"]].get("supersedes"),
                         "superseded_by": entry["superseded_by"],
                         "export_key": document["case_states"][entry["id"]]["export_key"]})
    requirements = {r["id"]: r for r in [*document["requirements"], *document["adr_requirements"]]}
    return {
        "locale": document["output_locale"], "labels": labels_for(document["output_locale"]),
        "lineage": {"parent_run_id": document["parent"]["run_id"], "canonical_digest": document["parent"]["canonical_digest"],
                    "adr_run_id": document["adr_run_id"], "previous_adr_id": document["previous_adr_id"],
                    "previous_effective_digest": document["previous_effective_digest"],
                    "effective_digest": document["effective_digest"], "rounds": document["lineage"]},
        "metrics": metrics, "entries": entries, "statements": analysis["statements"], "decisions": analysis["decisions"],
        "requirements": {d["id"]: [requirements[r] for r in analysis["requirements_of"].get(d["id"], []) if r in requirements]
                         for d in analysis["decisions"]},
        "affected": affected, "cases": built["cases"], "before": {cid: cases[cid] for cid in built["changes"]},
        "changes": built["changes"], "questions": [q for q in document["questions"]
                                                   if q["id"] in {x["id"] for x in analysis["questions"]}],
        "findings": [f for f in document["findings"] if f["id"] in {x["id"] for x in analysis["findings"]}],
        "question_dispositions": analysis["question_dispositions"],
        "finding_dispositions": analysis["finding_dispositions"], "dimension_reviews": analysis["dimension_reviews"],
    }


def _headline(view: dict[str, Any]) -> list[tuple[str, Any]]:
    m, l = view["metrics"], view["labels"]
    return [(l["decisions"], m["adr_decisions"]), (l["direct"], m["directly_affected_cases"]),
            (l["indirect"], m["indirectly_affected_cases"]), (l["updates"], m["updated_cases"]),
            (l["creates"], m["created_cases"]), (l["review"], m["review_cases"]), (l["blocked"], m["blocked_cases"]),
            (l["superseded"], m["superseded_cases"]), (l["questions"], m["questions_created"]),
            (l["findings"], m["findings_created"]), (l["unaffected"], m["unaffected_cases"])]


def _sources_line(view: dict[str, Any]) -> str:
    m, l = view["metrics"], view["labels"]
    parts = [f"{m['adr_files_total']} {l['sources'].lower()}", f"{m['adr_files_new']} {l['new']}",
             f"{m['adr_files_changed']} {l['changed']}", f"{m['adr_files_reused']} {l['reused']}"]
    for key, label in (("adr_files_unsupported", "unsupported"), ("adr_files_failed", "failed"),
                       ("adr_files_removed_from_selection", "removed")):
        if m[key]:
            parts.append(f"{m[key]} {l[label]}")
    return " · ".join(parts)


def summary_markdown(view: dict[str, Any]) -> str:
    l, lineage = view["labels"], view["lineage"]
    lines = [f"# {l['title']} — {lineage['adr_run_id']}", "",
             f"- {l['baseline']}: {lineage['parent_run_id']}",
             f"- {l['previous']}: {lineage['previous_adr_id'] or lineage['parent_run_id']}",
             f"- {l['sources']}: {_sources_line(view)}", "",
             "| | |", "| --- | --- |", *(f"| {name} | {value} |" for name, value in _headline(view)), "",
             f"## {l['decisions']}", ""]
    for decision in view["decisions"]:
        lines += [f"### {decision['id']} — {decision['relationship']} ({decision['status']})", "",
                  decision["statement"], ""]
        if decision["previous_authority"]["statement"]:
            lines += [f"- {l['previous_rule']}: {decision['previous_authority']['statement']}"]
        lines += [f"- {l['evidence']}: " + "; ".join(f"{p['source']} ({p['reference']})" for p in decision["provenance"]), ""]
    lines += [f"## {l['affected']}", "", f"| ID | {l['action']} | {l['impact']} | {l['status']} | {l['reason']} |",
              "| --- | --- | --- | --- | --- |",
              *(f"| {a['id']} | {a['action']} | {a['impact']} | {a['status']} | {a['reason']} |" for a in view["affected"]), ""]
    for cid, change in view["changes"].items():
        lines += [f"### {cid} — UPDATE", "", f"- {l['changed_fields']}: {', '.join(change['changed']) or '-'}",
                  f"- {l['unchanged_fields']}: {', '.join(change['unchanged'])}",
                  *(f"- {l['step']} {s['step']}: {s['change']} {', '.join(s.get('parts', []))}" for s in change["steps"]), ""]
    questions = [f"- **{q['id']}** {q['question']} ({l['blocking']}: {l['yes'] if q['blocking'] else l['no']})"
                 for q in view["questions"]]
    findings = [f"- **{f['id']}** {f['statement']}" for f in view["findings"]]
    lines += [f"## {l['questions']}", "", *(questions or [l["none"]]), "",
              f"## {l['findings']}", "", *(findings or [l["none"]]), ""]
    return "\n".join(lines)


CSS = """
:root{--bg:#fbfbfa;--fg:#1f2328;--muted:#5f6670;--card:#fff;--line:#e3e5e8;--accent:#2f5bd3;--add:#e7f6ec;--del:#fbeaea;--warn:#fff4dc}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e6e8eb;--muted:#9aa3ad;--card:#1d2024;--line:#2e3238;--accent:#7ea2ff;--add:#173222;--del:#3a1d1d;--warn:#3a3016}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{margin:0 0 4px}h2{margin-top:36px;border-bottom:1px solid var(--line);padding-bottom:6px}
.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.card b{display:block;font-size:24px}
section.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
table{border-collapse:collapse;width:100%;background:var(--card)}td,th{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:0 8px;font-size:12px;margin-right:4px}
.before{background:var(--del)}.after{background:var(--add)}.warn{background:var(--warn)}code,pre{white-space:pre-wrap;overflow-wrap:anywhere}
.scroll{overflow-x:auto}
"""


def _case_html(case: dict[str, Any], l: dict[str, str]) -> str:
    rows = "".join(f"<tr><td>{s['step']}</td><td>{_e(s['action'])}</td><td>{_e(s.get('expected_result') or '')}</td></tr>"
                   for s in case.get("steps", []))
    lists = "".join(f"<p><b>{_e(l[field])}</b></p><ul>{''.join(f'<li>{_e(v)}</li>' for v in case.get(field, []))}</ul>"
                    for field in ("preconditions", "cleanup") if case.get(field))
    data = "".join(f"<li><code>{_e(r['name'])}</code>: {_e(r['description'])}</li>" for r in case.get("test_data", []))
    return (f"<p>{_e(case.get('objective'))}</p>{lists}"
            + (f"<p><b>{_e(l['test_data'])}</b></p><ul>{data}</ul>" if data else "")
            + f"<div class='scroll'><table><tr><th>{_e(l['step'])}</th><th>{_e(l['procedure'])}</th>"
              f"<th>{_e(l['expected'])}</th></tr>{rows}</table></div>"
            + f"<p class='muted'>{_e(case['status'])} · {_e(case.get('automation_suitability'))} · "
              f"{_e(case.get('automation_readiness'))} · {_e(', '.join(case.get('readiness_blockers', [])))}</p>")


def report_html(view: dict[str, Any]) -> str:
    l, lineage = view["labels"], view["lineage"]
    cards = "".join(f"<div class='card'><b>{_e(v)}</b>{_e(k)}</div>" for k, v in _headline(view))
    decisions = []
    for d in view["decisions"]:
        reqs = ", ".join(f"{r['id']} ({r.get('source_identifier')})" for r in view["requirements"].get(d["id"], []))
        affected = ", ".join(a["id"] for a in view["affected"] if d["id"] in a["decisions"])
        provenance = "".join(f"<li><code>{_e(p['source'])}</code> ({_e(p['reference'])}): “{_e(p['excerpt'])}” "
                             f"<span class='tag'>{_e(p['status'])}</span></li>" for p in d["provenance"])
        claims = "".join(f"<li>{_e(c['claim'])} <span class='tag'>{_e(c['disposition'])}</span> {_e(', '.join(c['cases']))}</li>"
                         for c in d["claims"])
        decisions.append(
            f"<section class='item'><h3>{_e(d['id'])} <span class='tag'>{_e(d['relationship'])}</span>"
            f"<span class='tag'>{_e(d['status'])}</span></h3><p>{_e(d['statement'])}</p>"
            + (f"<p class='before'><b>{_e(l['previous_rule'])}:</b> {_e(d['previous_authority']['statement'])}</p>"
               if d["previous_authority"]["statement"] else "")
            + f"<p><b>{_e(l['requirements'])}:</b> {_e(reqs or '-')}</p><p><b>{_e(l['affected'])}:</b> {_e(affected or '-')}</p>"
            + f"<p><b>{_e(l['evidence'])}</b></p><ul>{provenance}</ul>"
            + (f"<p><b>{_e(l['claims'])}</b></p><ul>{claims}</ul>" if claims else "") + "</section>")
    rows = "".join(f"<tr><td>{_e(a['id'])}</td><td>{_e(a['title'])}</td><td>{_e(a['action'])}</td><td>{_e(a['impact'])}</td>"
                   f"<td>{_e(a['status'])}</td><td>{_e(', '.join(a['decisions']))}</td><td>{_e(a['reason'])}</td></tr>"
                   for a in view["affected"])
    changes = []
    for cid, change in view["changes"].items():
        diff = "".join(f"<tr><td>{_e(field)}</td><td class='before'><pre>{_e(json.dumps(v['before'], ensure_ascii=False, indent=1))}"
                       f"</pre></td><td class='after'><pre>{_e(json.dumps(v['after'], ensure_ascii=False, indent=1))}</pre></td></tr>"
                       for field, v in change["fields"].items())
        steps = ", ".join(f"{l['step']} {s['step']} {s['change']}" for s in change["steps"])
        changes.append(f"<section class='item'><h3>{_e(cid)} — UPDATE</h3><p><b>{_e(l['changed_fields'])}:</b> "
                       f"{_e(', '.join(change['changed']))}</p><p><b>{_e(l['unchanged_fields'])}:</b> "
                       f"{_e(', '.join(change['unchanged']))}</p><p>{_e(steps)}</p><div class='scroll'><table><tr><th></th>"
                       f"<th>{_e(l['before'])}</th><th>{_e(l['after'])}</th></tr>{diff}</table></div></section>")
    procedures = "".join(f"<section class='item'><h3>{_e(cid)} — {_e(case['title'])}</h3>{_case_html(case, l)}</section>"
                         for cid, case in sorted(view["cases"].items()))
    questions = "".join(f"<li class='{'warn' if q['blocking'] else ''}'><b>{_e(q['id'])}</b> {_e(q['question'])} "
                        f"<span class='muted'>{_e(q['reason'])} · {_e(', '.join(q['related_test_cases']))} · "
                        f"{_e(l['blocking'])}: {_e(l['yes'] if q['blocking'] else l['no'])}</span></li>" for q in view["questions"])
    findings = "".join(f"<li><b>{_e(f['id'])}</b> <span class='tag'>{_e(f['type'])}</span>{_e(f['statement'])}</li>"
                       for f in view["findings"])
    dispositions = "".join(f"<li>{_e(d.get('question') or d.get('finding'))}: <b>{_e(d['disposition'])}</b> "
                           f"({_e(d['decision'])}) — {_e(d['reason'])}</li>"
                           for d in [*view["question_dispositions"], *view["finding_dispositions"]])
    statements = "".join(f"<tr><td>{_e(s['key'])}</td><td><code>{_e(s['source'])}</code><br>{_e(s['reference'])}</td>"
                         f"<td>“{_e(s['excerpt'])}”<br><span class='muted'>{_e(s['meaning'])}</span></td><td>{_e(s['kind'])}</td>"
                         f"<td>{_e(s['status'])}</td><td>{_e(s['disposition'])}</td></tr>" for s in view["statements"])
    sources = "".join(f"<tr><td><code>{_e(e['path'])}</code></td><td>{_e(e['disposition'])}</td><td>{_e(e.get('reason'))}</td></tr>"
                      for e in view["entries"])
    dimensions = "".join(f"<tr><td>{_e(r['decision'])}</td><td>{_e(r['dimension'])}</td><td>{_e(r['disposition'])}</td>"
                         f"<td>{_e(', '.join(r['cases']) or r.get('reason') or r.get('question') or '')}</td></tr>"
                         for r in view["dimension_reviews"])
    metrics = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in view["metrics"].items())
    none = f"<p class='muted'>{_e(l['none'])}</p>"
    return f"""<!doctype html>
<html lang="{_e(view['locale'])}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(l['title'])} {_e(lineage['adr_run_id'])}</title><style>{CSS}</style></head><body><main>
<h1>{_e(l['title'])} — {_e(lineage['adr_run_id'])}</h1>
<p class="muted">{_e(l['baseline'])}: {_e(lineage['parent_run_id'])} · {_e(l['previous'])}: {_e(lineage['previous_adr_id'] or lineage['parent_run_id'])}
 · {_e(l['lineage'])}: {_e(' → '.join([lineage['parent_run_id'], *lineage['rounds']]))}</p>
<p>{_e(l['sources'])}: {_e(_sources_line(view))}</p>
<div class="cards">{cards}</div>
<h2>{_e(l['decisions'])}</h2>{''.join(decisions) or none}
<h2>{_e(l['affected'])}</h2><div class="scroll"><table><tr><th>ID</th><th></th><th>{_e(l['action'])}</th><th>{_e(l['impact'])}</th>
<th>{_e(l['status'])}</th><th>{_e(l['decisions'])}</th><th>{_e(l['reason'])}</th></tr>{rows}</table></div>
<h2>{_e(l['before'])} / {_e(l['after'])}</h2>{''.join(changes) or none}
<h2>{_e(l['procedure'])}</h2>{procedures or none}
<h2>{_e(l['questions'])}</h2><ul>{questions}</ul>{'' if questions else none}
<h2>{_e(l['findings'])}</h2><ul>{findings}</ul>{'' if findings else none}
<h2>{_e(l['dispositions'])}</h2><ul>{dispositions}</ul>{'' if dispositions else none}
<h2>{_e(l['statements'])}</h2><div class="scroll"><table>{statements}</table></div>
<h2>{_e(l['dimensions'])}</h2><div class="scroll"><table>{dimensions}</table></div>
<h2>{_e(l['sources'])}</h2><div class="scroll"><table>{sources}</table></div>
<h2>{_e(l['azure'])}</h2><p class="muted">output/adr/{_e(lineage['adr_run_id'])}/azure/azure-adr-export-package.json</p>
<h2>{_e(l['metrics'])}</h2><div class="scroll"><table>{metrics}</table></div>
</main></body></html>
"""
