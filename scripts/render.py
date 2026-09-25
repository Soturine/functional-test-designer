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
        "open_group": "Ver Test Cases", "modal_prev": "Anterior", "modal_next": "Próximo", "requirement_filter": "Requisito",
        "request_contract": "Contrato da requisição", "execution_variants": "Variantes de execução",
        "state_contract": "Restauração de estado", "rc_method": "Método", "rc_endpoint": "Endpoint",
        "rc_parameters": "Parâmetros", "rc_body": "Corpo", "rc_fixture_pool": "Massa de fixtures",
        "rc_varies": "O que varia", "rc_measurements": "Medições",
        "SELF_CLEANING": "o próprio caso limpa (ver Limpeza)",
        "REQUIRES_FIXTURE_RESET": "o harness deve reiniciar as fixtures de Dados de teste antes do próximo caso",
        "execution_plan": "Plano de execução", "plan_order": "Ordem", "plan_post_suite": "pós-suíte",
        "view_functional": "Por requisito", "view_all": "Todos", "view_families": "Famílias", "modal_page": "Visão", "notes": "Notas", "post_suite": "Pós-suíte", "post_suite_rationale": "Motivação",
        "post_suite_related": "Test Cases relacionados", "post_suite_lineage": "Origem (execução pós-suíte · run)",
        "order_use_case_main_flow": "ordem do fluxo principal", "order_canonical_order": "ordem canônica",
        "order_execution_order": "ordem de execução",
        "modal_of": " de ", "glossary_title": "Legenda e termos do relatório", "modal_close": "Fechar",
        "tc_alerts": "Atenções da análise", "finding_singular": "Finding", "question_singular": "Pergunta",
        "pendency_singular": "Pendência de execução", "pendency_plural": "Pendências", "pendency_one": "Pendência",
        "pendency_detail": "Neste caso",
        "no_filter_results": "Nenhum Test Case corresponde aos filtros ativos.",
        "tc_count_suffix": "Test Cases", "blocking_question": "Pergunta bloqueante",
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
        "expansion_help_title": "Como ler estas colunas",
        "candidates_help": "Quantidade de cenários candidatos materialmente relevantes considerados nesta dimensão. Não é o número de Test Cases finais.",
        "materialized_help": "Candidatos que viraram Test Cases canônicos adicionais durante a expansão aditiva.",
        "covered_help": "Candidatos já exercidos semanticamente por um TC existente, então nenhum TC duplicado foi criado.",
        "question_required_help": "Candidatos que não puderam virar um TC determinístico com segurança porque a evidência selecionada deixou uma ambiguidade material; uma Pergunta foi criada.",
        "not_applicable_help": "A dimensão foi avaliada mas não se aplica ao comportamento/contexto real do projeto (zero não significa que foi pulada).",
        "dimension_all": "Todas as 17 dimensões avaliadas",
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
        "open_group": "View Test Cases", "modal_prev": "Previous", "modal_next": "Next", "requirement_filter": "Requirement",
        "request_contract": "Request contract", "execution_variants": "Execution variants",
        "state_contract": "State restoration", "rc_method": "Method", "rc_endpoint": "Endpoint",
        "rc_parameters": "Parameters", "rc_body": "Body", "rc_fixture_pool": "Fixture pool",
        "rc_varies": "What varies", "rc_measurements": "Measurements",
        "SELF_CLEANING": "the case cleans up itself (see Cleanup)",
        "REQUIRES_FIXTURE_RESET": "the harness must reset the Test Data fixtures before the next case",
        "execution_plan": "Execution plan", "plan_order": "Order", "plan_post_suite": "post-suite",
        "view_functional": "By requirement", "view_all": "All", "view_families": "Families", "modal_page": "View", "notes": "Notes", "post_suite": "Post-suite", "post_suite_rationale": "Rationale",
        "post_suite_related": "Related Test Cases", "post_suite_lineage": "Origin (post-suite run · run)",
        "order_use_case_main_flow": "main-flow order", "order_canonical_order": "canonical order",
        "order_execution_order": "execution order",
        "modal_of": " of ", "glossary_title": "Report legend and terminology", "modal_close": "Close",
        "tc_alerts": "Analysis alerts", "finding_singular": "Finding", "question_singular": "Question",
        "pendency_singular": "Execution open item", "pendency_plural": "Open items", "pendency_one": "Open item",
        "pendency_detail": "In this case",
        "no_filter_results": "No Test Case matches the active filters.",
        "tc_count_suffix": "Test Cases", "blocking_question": "Blocking question",
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
        "expansion_help_title": "How to read these columns",
        "candidates_help": "Number of materially relevant scenario candidates considered for this dimension. Not the number of final Test Cases.",
        "materialized_help": "Candidates that became additional canonical Test Cases during the additive expansion pass.",
        "covered_help": "Candidates already semantically exercised by an existing TC, so no duplicate TC was added.",
        "question_required_help": "Candidates that could not safely become a deterministic TC because the selected evidence left a material ambiguity; a Question was required instead.",
        "not_applicable_help": "The dimension was evaluated but did not apply to the project's actual behavior/context (zero does not mean it was skipped).",
        "dimension_all": "All 17 dimensions evaluated",
    },
}
# Human-readable descriptions only; these never feed generation logic, they only
# explain the dimension codes the runtime already computed.
EXPANSION_DIMENSION_INFO: dict[str, dict[str, tuple[str, str]]] = {
    "pt": {
        "NEGATIVE": ("Comportamento negativo", "Caminhos inválidos/recusados/de erro em torno de uma funcionalidade válida."),
        "BOUNDARY": ("Condições de limite", "Limites, thresholds, bordas exatas e comportamento logo dentro/fora do permitido."),
        "OPERATOR_ERROR": ("Erro de operador", "Erros humanos plausíveis: recurso errado, ator errado, sequência errada, associação errada ou ação omitida/repetida."),
        "MISUSE": ("Uso indevido", "Uso de capacidades válidas de forma não intencional ou não suportada."),
        "STATE_TRANSITION": ("Transição de estado", "Comportamento ao mover entre estados válidos/inválidos e a aplicação das transições permitidas."),
        "DECISION_TABLE": ("Combinações de decisão", "Combinações relevantes de condições/regras cujas saídas diferem."),
        "CONCURRENCY": ("Concorrência", "Dois ou mais atores/processos agindo simultaneamente sobre estado relacionado."),
        "RACE_CONDITION": ("Condição de corrida", "Intercalações sensíveis a tempo em que a ordem de execução pode mudar o resultado."),
        "IDEMPOTENCY": ("Idempotência", "Execução/retentativa repetida não deve duplicar ou corromper efeitos incorretamente."),
        "INTEGRATION": ("Integração", "Comportamento nas fronteiras entre subsistemas internos/externos e suas dependências."),
        "RECOVERY": ("Recuperação", "Retorno a um estado válido/conhecido após interrupção ou falha."),
        "CHAOS": ("Caos / disrupção", "Disrupção deliberada de dependência/rede/processo/ambiente usada para expor comportamento de resiliência."),
        "SECURITY": ("Segurança", "Comportamento sensível a segurança além das checagens funcionais comuns de autorização, quando a evidência sustenta."),
        "AUTHORIZATION": ("Autorização", "Se atores só conseguem realizar operações permitidas por papel/política."),
        "DATA_INTEGRITY": ("Integridade de dados", "Consistência/correção de dados persistidos ou propagados entre operações/falhas."),
        "CROSS_REQUIREMENT": ("Interação entre requisitos", "Comportamento que emerge quando dois ou mais requisitos/regras interagem."),
        "E2E": ("Ponta a ponta", "Uma jornada composta de usuário/sistema que percorre vários comportamentos atômicos."),
    },
    "en": {
        "NEGATIVE": ("Negative behavior", "Invalid/refused/error paths around otherwise valid functionality."),
        "BOUNDARY": ("Boundary conditions", "Limits, thresholds, exact edges and just-inside/just-outside behavior."),
        "OPERATOR_ERROR": ("Operator error", "Plausible human mistakes: wrong resource, wrong actor, wrong sequence, wrong association or omitted/repeated action."),
        "MISUSE": ("Misuse", "Use of valid capabilities in an unintended or unsupported way."),
        "STATE_TRANSITION": ("State transition", "Behavior when moving between valid/invalid states and enforcing allowed transitions."),
        "DECISION_TABLE": ("Decision combinations", "Relevant combinations of conditions/rules whose outputs differ."),
        "CONCURRENCY": ("Concurrency", "Two or more actors/processes acting simultaneously on related state."),
        "RACE_CONDITION": ("Race condition", "Timing-sensitive interleavings where execution order can change the outcome."),
        "IDEMPOTENCY": ("Idempotency", "Repeated execution/retry should not incorrectly duplicate or corrupt effects."),
        "INTEGRATION": ("Integration", "Behavior across external/internal subsystem boundaries and dependencies."),
        "RECOVERY": ("Recovery", "Return to a valid/known state after interruption or failure."),
        "CHAOS": ("Chaos / disruption", "Deliberate dependency/network/process/environment disruption used to expose resilience behavior."),
        "SECURITY": ("Security", "Security-sensitive behavior beyond ordinary functional authorization checks, where evidence supports it."),
        "AUTHORIZATION": ("Authorization", "Whether actors can perform only operations permitted by role/policy."),
        "DATA_INTEGRITY": ("Data integrity", "Consistency/correctness of persisted or propagated data across operations/failures."),
        "CROSS_REQUIREMENT": ("Cross-requirement interaction", "Behavior that emerges when two or more requirements/rules interact."),
        "E2E": ("End-to-end", "A composed user/system journey spanning multiple atomic behaviors."),
    },
}


def dimension_info(dimension: str, language: str) -> tuple[str, str]:
    table = EXPANSION_DIMENSION_INFO.get(language, EXPANSION_DIMENSION_INFO["en"])
    return table.get(dimension, (dimension, ""))


OPERATOR_DIMENSIONS = {"OPERATOR_ERROR", "MISUSE"}
CHAOS_DIMENSIONS = {"CHAOS", "RECOVERY"}
CONCURRENCY_DIMENSIONS = {"CONCURRENCY", "RACE_CONDITION", "IDEMPOTENCY"}
SECURITY_DIMENSIONS = {"SECURITY", "AUTHORIZATION"}


def labels_for(index: dict[str, Any]) -> dict[str, str]:
    # Suites published before v2.3 carry no locale; they keep neutral English labels.
    language = str(index.get("output_locale", "en")).split("-", 1)[0].casefold()
    labels = LABELS.get(language, LABELS["en"])
    return {**labels, "_language": language if language in LABELS else "en"}


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
        *_execution_context_markdown(case, labels),
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


# What each procedure unknown means for whoever runs the case, per locale. The detail
# recorded for the specific case (in its notes as "KIND: detail") is shown next to it.
UNKNOWN_MEANINGS = {
    "pt": {
        "MISSING_EXECUTION_SURFACE": "As fontes selecionadas não mostram onde executar esta ação (tela, endpoint ou dispositivo). O cenário é mantido; a superfície de execução precisa ser confirmada.",
        "UNKNOWN_SETUP_PATH": "As fontes selecionadas não mostram como preparar o estado inicial ou a condição de teste. O caminho de preparação precisa ser confirmado.",
        "MISSING_ORACLE": "A autoridade não define o resultado esperado; ele precisa ser decidido antes de julgar aprovação ou reprovação.",
        "AMBIGUOUS_POLICY": "A regra aplicável é ambígua ou conflitante nas fontes.",
        "UNRESOLVED_PERMISSION": "Não está definido qual perfil pode executar a ação.",
        "EXTERNAL_DEPENDENCY_UNAVAILABLE": "A execução depende de um sistema externo indisponível no ambiente de teste.",
        "MISSING_FIXTURE": "Falta massa de dados determinística para automatizar; um testador ainda consegue executar.",
        "MISSING_SELECTOR": "Falta um seletor ou identificador estável para automatizar a interface.",
        "MISSING_ENVIRONMENT": "Falta um ambiente adequado (volume, dispositivos, gerador de carga) para executar ou automatizar.",
    },
    "en": {
        "MISSING_EXECUTION_SURFACE": "The selected sources do not show where to perform this action (screen, endpoint or device). The scenario is kept; its execution surface must be confirmed.",
        "UNKNOWN_SETUP_PATH": "The selected sources do not show how to prepare the starting state or test condition. The setup path must be confirmed.",
        "MISSING_ORACLE": "The authority does not define the expected result; it must be decided before judging pass or fail.",
        "AMBIGUOUS_POLICY": "The applicable rule is ambiguous or conflicting in the sources.",
        "UNRESOLVED_PERMISSION": "It is not defined which role may perform the action.",
        "EXTERNAL_DEPENDENCY_UNAVAILABLE": "Execution depends on an external system unavailable in the test environment.",
        "MISSING_FIXTURE": "Deterministic test data for automation is missing; a tester can still run the case.",
        "MISSING_SELECTOR": "A stable selector or identifier for UI automation is missing.",
        "MISSING_ENVIRONMENT": "A suitable environment (volume, devices, load generator) is missing to run or automate the case.",
    },
}
_NOTE_KIND = re.compile(r"^([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+):\s*(.+)$", re.DOTALL)


def execution_pendencies(case: dict[str, Any], language: str) -> list[dict[str, str]]:
    """The case's recorded execution unknowns, each with what it means and, when the procedure
    recorded one, its case-specific detail. A blocking Question is shown as its Question, not
    here; nothing is invented and no Question is created."""
    meanings = UNKNOWN_MEANINGS.get(language, UNKNOWN_MEANINGS["en"])
    details: dict[str, list[str]] = {}
    for note in case.get("notes", []) or []:
        match = _NOTE_KIND.match(str(note).strip())
        if match and match.group(1) in meanings:
            details.setdefault(match.group(1), []).append(match.group(2).strip())
    kinds = [k for k in case.get("readiness_blockers", []) or [] if k != "BLOCKING_QUESTION"]
    kinds += [k for k in details if k not in kinds]
    return [{"kind": kind, "meaning": meanings.get(kind, ""), "detail": " ".join(details.get(kind, []))}
            for kind in kinds]


def render_pendency_card(item: dict[str, str], labels: dict[str, str]) -> str:
    return (
        f'<article class="pendency-item"><div class="question-title"><span>{esc(labels["pendency_singular"])}</span>'
        f'<span class="badge">{esc(item["kind"])}</span></div>'
        + (f'<p>{esc(item["meaning"])}</p>' if item["meaning"] else "")
        + (f'<p><strong>{esc(labels["pendency_detail"])}:</strong> {esc(item["detail"])}</p>' if item["detail"] else "")
        + "</article>"
    )


def _case_badges(case: dict[str, Any], labels: dict[str, str]) -> str:
    """Shared between the compact TC row and the opened TC's own heading, so both
    always agree — one badge-building rule, not two copies that can drift apart."""
    badges = [f'<span class="badge test-basis">{esc(case.get("test_basis", "ACCEPTANCE"))}</span>']
    if case.get("expansion_dimension"):
        badges.append(f'<span class="badge dimension">{esc(case["expansion_dimension"])}</span>')
    badges.append(f'<span class="badge status-{esc(case["status"].lower())}">{esc(case["status"])}</span>')
    badges.append(f'<span class="badge priority">{esc(case["priority"])}</span>')
    if case.get("automation_suitability"):
        badges.append(
            f'<span class="badge automation" title="{esc(labels["suitability"])} / {esc(labels["automation_readiness"])}">'
            f'{esc(case["automation_suitability"])} / {esc(case.get("automation_readiness"))}</span>'
        )
    n_findings, n_questions = len(case.get("finding_refs") or []), len(case.get("question_refs") or [])
    if n_findings:
        word = labels["finding_singular"] if n_findings == 1 else labels["findings"]
        badges.append(f'<span class="badge badge-finding">{n_findings} {esc(word)}</span>')
    if n_questions:
        word = labels["question_singular"] if n_questions == 1 else labels["questions"]
        badges.append(f'<span class="badge badge-question">{n_questions} {esc(word)}</span>')
    n_pending = len(execution_pendencies(case, labels.get("_language", "en")))
    if n_pending:
        word = labels["pendency_one"] if n_pending == 1 else labels["pendency_plural"]
        badges.append(f'<span class="badge badge-pendency">{n_pending} {esc(word)}</span>')
    return "".join(badges)


def render_finding_card(finding: dict[str, Any], labels: dict[str, str], requirements: dict[str, dict[str, Any]]) -> str:
    """Only the Finding fields canonical state actually stores; nothing is invented."""
    none = labels["none"]
    reqs = "; ".join(
        requirement_label(requirements[r]) for r in finding.get("requirement_refs", []) if r in requirements
    ) or none
    evidence = "; ".join(f"{ref['source']} ({ref['reference']})" for ref in finding.get("source_refs", []) or []) or none
    tcs = ", ".join(finding.get("related_test_cases", []) or []) or none
    return (
        f'<article class="finding-item"><div class="finding-title"><span class="badge">{esc(finding["type"])}</span>'
        f'<strong>{esc(finding["id"])}</strong></div><p>{esc(finding["statement"])}</p>'
        f'<dl class="technical-grid"><dt>{esc(labels["requirements"])}</dt><dd>{esc(reqs)}</dd>'
        f'<dt>{esc(labels["impacted"])}</dt><dd>{esc(tcs)}</dd>'
        + (f'<dt>{esc(labels["questions"])}</dt><dd>{esc(", ".join(finding["question_refs"]))}</dd>'
           if finding.get("question_refs") else "")
        + f'<dt>{esc(labels["evidence"])}</dt><dd>{esc(evidence)}</dd></dl></article>'
    )


def render_question_card(question: dict[str, Any], labels: dict[str, str]) -> str:
    """Only the Question fields canonical state actually stores; no answer is fabricated."""
    none = labels["none"]
    evidence = "; ".join(f"{ref['source']} ({ref['reference']})" for ref in question.get("source_refs", []) or []) or none
    tcs = ", ".join(question.get("related_test_cases", []) or []) or none
    blocking = bool(question.get("blocking"))
    return (
        f'<article class="question-item{" blocking" if blocking else ""}"><div class="question-title">'
        f'<span>{esc(question["id"])} &middot; {esc(question["question"])}</span>'
        f'<span class="badge">{esc(labels["blocking"])}: {esc(labels["yes"] if blocking else labels["no"])}</span></div>'
        f'<p><strong>{esc(labels["reason"])}:</strong> {esc(question["reason"])}</p>'
        f'<p><strong>{esc(labels["impacted"])}:</strong> {esc(tcs)}</p>'
        f'<p class="muted"><strong>{esc(labels["evidence"])}:</strong> {esc(evidence)}</p></article>'
    )


def render_tc_alerts(
    case: dict[str, Any], labels: dict[str, str], findings_by_id: dict[str, dict[str, Any]],
    questions_by_id: dict[str, dict[str, Any]], requirements: dict[str, dict[str, Any]],
) -> str:
    """Only the Findings/Questions this specific TC links to — never an unrelated one,
    and never rendered at all when there is nothing to show."""
    finding_cards = [
        render_finding_card(findings_by_id[ref], labels, requirements)
        for ref in case.get("finding_refs", []) or [] if ref in findings_by_id
    ]
    question_cards = [
        render_question_card(questions_by_id[ref], labels)
        for ref in case.get("question_refs", []) or [] if ref in questions_by_id
    ]
    pendency_cards = [render_pendency_card(item, labels) for item in execution_pendencies(case, labels.get("_language", "en"))]
    if not finding_cards and not question_cards and not pendency_cards:
        return ""
    return (
        f'<section class="tc-alerts"><h3>{esc(labels["tc_alerts"])}</h3>'
        f'{"".join(finding_cards)}{"".join(question_cards)}{"".join(pendency_cards)}</section>'
    )


def render_case_body(
    case: dict[str, Any], entry: dict[str, Any], mermaid: str, labels: dict[str, str],
    requirements: dict[str, dict[str, Any]], family: str, artifact_formats: set[str],
    findings_by_id: dict[str, dict[str, Any]] | None = None, questions_by_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    """The expensive, per-case detail fragment (header + full content). Callers place
    this inside a `<template>` so the browser never lays it out or materializes its
    flow SVG until the one currently viewed case is cloned into the live modal."""
    none = labels["none"]
    badges = _case_badges(case, labels)
    alerts = render_tc_alerts(case, labels, findings_by_id or {}, questions_by_id or {}, requirements)
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
    return f"""<div class="tc-detail-head"><span class="tc-heading"><span class="tc-id">{esc(case['id'])}</span>{esc(case['title'])}{chips}</span><span class="badges">{badges}</span></div>
  <div class="tc-content">
    {alerts}
    <section><h3>{esc(labels['objective'])}</h3><p>{esc(case['objective'])}</p></section>
    <p class="related-requirements"><strong>{esc(labels['requirements'])}:</strong> {esc('; '.join(requirement_names))}</p>
    <div class="two-column">
      <section><h3>{esc(labels['preconditions'])}</h3>{_list(case.get('preconditions', []), none)}</section>
      <section><h3>{esc(labels['test_data'])}</h3>{_data(case.get('test_data', []), none)}</section>
    </div>
    <section><h3>{esc(labels['steps'])}</h3>{_steps(case['steps'], labels)}</section>
    <div class="two-column">
      <section><h3>{esc(labels['postconditions'])}</h3>{_list(case.get('postconditions', []), none)}</section>
      <section><h3>{esc(labels['cleanup'])}</h3>{_list(case.get('cleanup', []), none)}</section>
    </div>
    {_execution_context_html(case, labels)}
    <section class="flow-section"><div class="flow-heading"><h3>{esc(labels['flow'])}</h3>{expand}</div>{flow}</section>
    {f'<section><h3>{esc(labels["suitability"])}</h3>{automation}</section>' if automation else ''}
    <section><h3>{esc(labels['artifacts'])}</h3><div class="artifact-links">{''.join(links) or esc(none)}</div></section>
    <details class="technical"><summary>{esc(labels['technical'])}</summary>{trace}</details>
  </div>"""


def render_case_template(
    case: dict[str, Any], entry: dict[str, Any], mermaid: str, labels: dict[str, str],
    requirements: dict[str, dict[str, Any]], family_id: str, family: str, flags: set[str],
    artifact_formats: set[str], findings_by_id: dict[str, dict[str, Any]], questions_by_id: dict[str, dict[str, Any]],
) -> str:
    """A `<template>` never renders/lays out its content and never runs the scripts or
    loads the resources it contains until it is explicitly cloned — the browser-native
    way to keep hundreds of Test Cases' full detail out of the visible/materialized DOM
    while still shipping compact, filterable data-* attributes for every one of them. One
    global template per TC: the same TC can be cloned into several requirement pages
    without its data ever being duplicated or mutated."""
    search = " ".join([case["id"], case["title"], case["objective"], family, " ".join(case.get("tags", [])),
                       " ".join(case.get("source_identifiers", []))]).casefold()
    body = render_case_body(case, entry, mermaid, labels, requirements, family, artifact_formats,
                            findings_by_id, questions_by_id)
    return (
        f'<template class="tc-template" id="tc-tpl-{esc(case["id"])}" data-id="{esc(case["id"])}" '
        f'data-title="{esc(case["title"])}" data-status="{esc(case["status"])}" '
        f'data-priority="{esc(case["priority"])}" data-family="{esc(family_id)}" '
        f'data-features="{esc(" ".join(sorted(flags)))}" data-search="{esc(search)}">{body}</template>'
    )


def _contract_rows(case: dict[str, Any], labels: dict[str, str]) -> list[tuple[str, str]]:
    contract = case.get("request_contract") or {}
    rows = []
    for field in ("method", "endpoint", "parameters", "body", "fixture_pool", "varies", "measurements"):
        value = contract.get(field)
        if value:
            rows.append((labels[f"rc_{field}"], "; ".join(value) if isinstance(value, list) else str(value)))
    return rows


def _execution_context_markdown(case: dict[str, Any], labels: dict[str, str]) -> list[str]:
    """Request contract, execution variants and the state contract, when the case has them."""
    sections = []
    if case.get("request_contract"):
        sections.append(f"## {labels['request_contract']}\n" + "\n".join(
            f"- **{name}:** {value}" for name, value in _contract_rows(case, labels)))
    if case.get("execution_variants"):
        sections.append(f"## {labels['execution_variants']}\n" + "\n".join(
            f"- **{v['kind']}:** {v['description']}" for v in case["execution_variants"]))
    if case.get("state_contract"):
        sections.append(f"## {labels['state_contract']}\n{case['state_contract']} — {labels[case['state_contract']]}")
    return sections


def _execution_context_html(case: dict[str, Any], labels: dict[str, str]) -> str:
    parts = []
    if case.get("request_contract"):
        parts.append(f"<section><h3>{esc(labels['request_contract'])}</h3><dl class=\"technical-grid\">" + "".join(
            f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in _contract_rows(case, labels)) + "</dl></section>")
    if case.get("execution_variants"):
        parts.append(f"<section><h3>{esc(labels['execution_variants'])}</h3><ul>" + "".join(
            f"<li><strong>{esc(v['kind'])}:</strong> {esc(v['description'])}</li>" for v in case["execution_variants"])
            + "</ul></section>")
    if case.get("state_contract"):
        parts.append(f"<p class=\"muted\"><strong>{esc(labels['state_contract'])}:</strong> "
                     f"{esc(case['state_contract'])} — {esc(labels[case['state_contract']])}</p>")
    return "".join(parts)


def _case_row(case: dict[str, Any], labels: dict[str, str]) -> str:
    """The lightweight, always-in-DOM header row for one TC inside a requirement page.
    The expensive body is cloned from the TC's own global `<template>` only when this
    row's disclosure control is opened — see the modal controller script."""
    badges = _case_badges(case, labels)
    body_id = f"tc-row-body-{esc(case['id'])}"
    return (
        f'<li class="tc-row" data-id="{esc(case["id"])}">'
        f'<button type="button" class="tc-row-toggle" aria-expanded="false" aria-controls="{body_id}">'
        f'<span class="tc-row-chevron" aria-hidden="true">&#9656;</span>'
        f'<span class="tc-row-id">{esc(case["id"])}</span><span class="tc-row-title">{esc(case["title"])}</span>'
        f'<span class="badges">{badges}</span></button>'
        f'<div class="tc-row-body" id="{body_id}" hidden></div></li>'
    )


def _case_requirement_keys(case: dict[str, Any], requirements: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """The official identifiers this TC belongs to (key, display title), in the order
    the case lists them. Falls back to internal requirement_refs, with their stored
    title, for suites that predate `source_identifiers` (schema 1.2)."""
    identifiers = case.get("source_identifiers") or []
    if identifiers:
        return [(value, _identifier_title(value, requirements)) for value in identifiers]
    return [
        (ref, requirement_label(requirements[ref]) if ref in requirements else ref)
        for ref in case.get("requirement_refs", []) or []
    ]


def render_requirement_page(group_id: str, key: str, title: str, members: list[dict[str, Any]],
                            labels: dict[str, str], *, scope: str = "requirement", rows: str | None = None,
                            count: int | None = None) -> str:
    """One `<template>` per modal page of a family/group. The first page (scope "all")
    lists every unique Test Case the family card counts; the following pages refine it
    by authoritative identifier, where a multi-identifier TC appears on each of its pages.
    Pages never paginate individual Test Cases. Reading `.content` (to find which TC ids
    live on a page, or to filter them) never materializes or lays this out."""
    rows = rows if rows is not None else "".join(_case_row(case, labels) for case in members)
    count = len(members) if count is None else count
    return (
        f'<template class="req-template" data-family="{esc(group_id)}" data-key="{esc(key)}" '
        f'data-scope="{esc(scope)}" data-title="{esc(title)}"><div class="req-page-head"><h4>{esc(title)}</h4>'
        f'<p class="muted req-page-count"><span class="req-page-count-value">{count}</span> '
        f'{esc(labels["tc_count_suffix"])}</p></div>'
        f'<ul class="tc-row-list">{rows}</ul>'
        f'<p class="empty req-page-empty" hidden>{esc(labels["no_filter_results"])}</p></template>'
    )


def _post_suite_row(case: dict[str, Any], labels: dict[str, str]) -> str:
    """A post-suite (chaos) case row: same accordion as a TC row, its own CH identity."""
    body_id = f"tc-row-body-{esc(case['key'])}"
    tags = "".join(f'<span class="badge">{esc(tag)}</span>' for tag in case.get("execution_tags", []))
    return (
        f'<li class="tc-row" data-id="{esc(case["key"])}">'
        f'<button type="button" class="tc-row-toggle" aria-expanded="false" aria-controls="{body_id}">'
        f'<span class="tc-row-chevron" aria-hidden="true">&#9656;</span>'
        f'<span class="tc-row-id">{esc(case["id"])}</span><span class="tc-row-title">{esc(case["title"])}</span>'
        f'<span class="badges"><span class="badge post-suite">{esc(labels["post_suite"])}</span>{tags}</span></button>'
        f'<div class="tc-row-body" id="{body_id}" hidden></div></li>'
    )


def render_post_suite_template(case: dict[str, Any], labels: dict[str, str]) -> str:
    """The full body of a post-suite case, shown in the same modal as canonical cases.
    Its content comes from its own finalized run; the canonical suite is not touched."""
    def listing(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>" if items else ""
    data = "".join(f"<tr><th>{esc(row.get('name'))}</th><td>{esc(row.get('description'))}</td></tr>"
                   for row in case.get("test_data", []))
    steps = "".join(f"<li><strong>{esc(step.get('action'))}</strong><br>{esc(step.get('expected_result') or '')}</li>"
                    for step in case.get("steps", []))
    unknowns = [f"{u.get('kind')}: {u.get('detail')}" for u in case.get("unknowns", [])]
    sections = [
        (labels["post_suite_rationale"], f"<p>{esc(case.get('rationale', ''))}</p>"),
        (labels["preconditions"], listing(case.get("preconditions", []))),
        (labels["test_data"], f"<table class='data'>{data}</table>" if data else ""),
        (labels["steps"], f"<ol>{steps}</ol>" if steps else ""),
        (labels["postconditions"], listing(case.get("postconditions", []))),
        (labels["cleanup"], listing(case.get("cleanup", []))),
        (labels["blockers"], listing(unknowns)),
        (labels["notes"], listing(case.get("notes", []))),
        (labels["post_suite_related"], esc(", ".join(case.get("related_test_cases", [])))),
        (labels["post_suite_lineage"], esc(f"{case.get('chaos_run_id')} · {case.get('parent_run_id')}")),
    ]
    body = "".join(f"<h4>{esc(title)}</h4>{content}" for title, content in sections if content)
    body += _execution_context_html(case, labels)
    search = " ".join([case["id"], case["title"], case.get("rationale", ""), " ".join(case.get("execution_tags", []))]).casefold()
    return (
        f'<template class="tc-template" id="tc-tpl-{esc(case["key"])}" data-id="{esc(case["key"])}" '
        f'data-title="{esc(case["title"])}" data-status="" data-priority="{esc(case.get("priority") or "")}" '
        f'data-family="post-suite" data-features="post-suite" data-search="{esc(search)}">'
        f'<article class="tc-content post-suite-case"><h3>{esc(case["id"])} · {esc(case["title"])}</h3>{body}</article></template>'
    )


def render_execution_plan(organization: dict[str, Any], index: dict[str, Any]) -> str:
    """Markdown view of the organization: every group with its cases in execution order.
    Cases are referenced, never repeated in full."""
    labels = labels_for(index)
    titles = {entry["id"]: entry.get("title", "") for entry in index.get("test_cases", [])}
    post = {case["key"]: case for case in organization.get("post_suite_cases", [])}
    lines = [f"# {labels['execution_plan']}", ""]
    for group in organization["groups"]:
        lines += [f"## {group['label']}", ""]
        order = labels.get(f"order_{group['order_source'].lower()}", group["order_source"])
        reference = f" ({group['flow_reference']})" if group.get("flow_reference") else ""
        lines += [f"_{labels['plan_order']}: {order}{reference}_", ""]
        for member in group["members"]:
            if member["origin"] == "CANONICAL":
                lines.append(f"{member['order']}. [{member['case']}](test-cases-md/{member['case']}.md) — {titles.get(member['case'], '')}")
            else:
                key = f"{member['chaos_run_id']}:{member['case']}"
                lines.append(f"{member['order']}. {member['case']} ({labels['plan_post_suite']} {member['chaos_run_id']})"
                             f" — {post.get(key, {}).get('title', '')}")
        lines.append("")
    return "\n".join(lines)


def _organization_views(organization: dict[str, Any], cases: list[dict[str, Any]], labels: dict[str, str],
                        requirements: dict[str, dict[str, Any]]) -> tuple[list[tuple[str, str, str]], str]:
    """Cards for every organization group, grouped into views; plus the post-suite templates.
    Each card's modal opens on the group's ordered 'all' page."""
    by_id = {case["id"]: case for case in cases}
    post = {case["key"]: case for case in organization.get("post_suite_cases", [])}

    def card(view: str, group: dict[str, Any]) -> str:
        key = f"{view}:{group['id']}"
        rows, canonical_members = [], []
        for member in group["members"]:
            if member["origin"] == "CANONICAL" and member["case"] in by_id:
                rows.append(_case_row(by_id[member["case"]], labels))
                canonical_members.append(by_id[member["case"]])
            elif member["origin"] != "CANONICAL":
                entry = post.get(f"{member['chaos_run_id']}:{member['case']}")
                if entry:
                    rows.append(_post_suite_row(entry, labels))
        pages = render_requirement_page(key, labels["all"], group["label"], [], labels, scope="all", rows="".join(rows),
                                        count=len(rows))
        if group["kind"] == "FUNCTIONAL":
            refined: dict[str, dict[str, Any]] = {}
            for case in canonical_members:
                for ident, page_title in _case_requirement_keys(case, requirements):
                    refined.setdefault(ident, {"title": page_title, "cases": []})["cases"].append(case)
            pages += "".join(render_requirement_page(key, ident, page["title"], page["cases"], labels)
                             for ident, page in refined.items())
        detail = labels["order_" + group["order_source"].lower()] if f"order_{group['order_source'].lower()}" in labels else ""
        return (
            f'<section class="tc-group" data-family="{esc(key)}"><div class="tc-group-card">'
            f'<div><h3>{esc(group["label"])}</h3><span><span class="tc-count">{len(rows)}</span> TCs'
            f'{" &middot; " + esc(detail) if detail else ""}</span></div>'
            f'<button type="button" class="open-group" data-family="{esc(key)}">{esc(labels["open_group"])}</button>'
            f'</div>{pages}</section>'
        )

    functional = [g for g in organization["groups"] if g["kind"] in {"FUNCTIONAL", "USE_CASE", "TRANSVERSAL"}]
    views = [("functional", labels["view_functional"], "".join(card("functional", g) for g in functional))]
    for group in organization["groups"]:
        if group["kind"] == "EXECUTION_VIEW":
            views.append((group["id"].lower(), group["label"], card(group["id"].lower(), group)))
    everything = {"id": "ALL", "kind": "ALL", "label": labels["view_all"], "order_source": "CANONICAL_ORDER",
                  "members": [{"case": case["id"], "origin": "CANONICAL"} for case in cases]
                  + [{"case": c["id"], "origin": "POST_SUITE", "chaos_run_id": c["chaos_run_id"]} for c in post.values()]}
    views.append(("all", labels["view_all"], card("all", everything)))
    templates = "".join(render_post_suite_template(case, labels) for case in post.values())
    return views, templates


GLOSSARY: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {
    "pt": [
        ("Natureza do Test Case", [
            ("Normativos / Acceptance", "Test Cases derivados diretamente dos requisitos/regras da autoridade normativa e do baseline normativo congelado."),
            ("Derivados", "Test Cases adicionais, determinísticos, derivados semanticamente de regras, relações, estados ou comportamento de falha já conhecidos, sem inventar um novo requisito."),
            ("Caracterização", "Testes que documentam o comportamento observado da implementação, especialmente quando ele precisa ser entendido separadamente da expectativa normativa."),
            ("Exploratório", "Uma hipótese/cenário que vale investigar quando não existe um oracle ou política determinística completa."),
            ("E2E", "Uma jornada ponta a ponta composta, que percorre vários comportamentos/estágios atômicos."),
        ]),
        ("Status de execução / prontidão", [
            ("READY", "Existe informação fundamentada suficiente para executar o TC como desenhado."),
            ("NEEDS_REVIEW", "O cenário é válido, mas uma incerteza material ou um detalhe de execução ausente exige revisão/esclarecimento."),
            ("BLOCKED", "A execução depende de uma dependência externa, ambiente, equipamento indisponível ou outra condição bloqueante."),
            ("EXPLORATORY", "O caso é intencionalmente exploratório, não um teste normativo determinístico de aprova/reprova."),
            ("Pendência de execução", "Uma incerteza registrada no procedimento (por exemplo MISSING_EXECUTION_SURFACE ou UNKNOWN_SETUP_PATH), exibida no TC com o que significa e o detalhe do caso. Não é uma Pergunta: uma Pergunta só aparece quando a análise a criou."),
        ]),
        ("Automação: adequação / prontidão", [
            ("MEDIUM / NEEDS_FIXTURE", "O selo de automação mostra adequação / prontidão: quanto vale automatizar o caso (HIGH, MEDIUM, LOW, MANUAL_ONLY) e o que ainda falta para automatizá-lo."),
            ("READY", "Nada falta para automatizar o caso."),
            ("NEEDS_POLICY", "Falta decidir uma regra, permissão ou resultado esperado."),
            ("NEEDS_ENVIRONMENT", "Falta um ambiente ou superfície de execução adequado."),
            ("NEEDS_FIXTURE", "Falta massa de dados determinística ou um caminho de preparação conhecido."),
            ("NEEDS_SELECTOR", "Falta um seletor ou identificador estável de interface."),
            ("BLOCKED_EXTERNAL_DEPENDENCY", "Depende de um sistema externo indisponível."),
            ("NOT_APPLICABLE", "O caso é MANUAL_ONLY; prontidão de automação não se aplica."),
        ]),
        ("Prioridade", [
            ("CRITICAL", "A falha pode quebrar um fluxo central, integridade/segurança, uma transição irreversível, auditabilidade crítica ou comportamento igualmente severo."),
            ("HIGH", "Falha funcional ou operacional de alto impacto, exigindo cobertura forte."),
            ("MEDIUM", "Comportamento relevante, de impacto moderado."),
            ("LOW", "Comportamento de baixo impacto, de suporte ou cosmético."),
        ]),
        ("Conceitos de QA / expansão", [
            ("Erro de operador", "Cenários que exploram erros humanos plausíveis: recurso, associação, ator, estado ou sequência errados, entre outros."),
            ("Caos / Recuperação", "Comportamento de falha/recuperação envolvendo dependências, interrupções, reinício, retentativa, falha parcial ou disrupção operacional semelhante."),
            ("Concorrência", "Ações simultâneas/concorrentes, idempotência e consistência de estado sob execução concorrente."),
            ("Segurança / Autorização", "Comportamento de autenticação/autorização/controle de acesso/segurança representado na suíte."),
            ("Famílias", "Famílias de cenários usadas para organizar Test Cases relacionados para revisão."),
            ("Merge Candidates", "Casos parecidos o suficiente para uma revisão humana de possível consolidação; não são mesclados automaticamente."),
        ]),
        ("Conceitos de análise / qualidade", [
            ("Findings", "Divergências, conflitos ou observações notáveis da implementação, fundamentados em evidência, encontrados durante a análise. Um Finding não é automaticamente sinônimo de um Test Case reprovado."),
            ("Perguntas", "Questões abertas criadas quando a evidência selecionada é insuficiente ou ambígua e inventar uma resposta seria inseguro."),
            ("Pergunta bloqueante", "Uma Pergunta cuja resposta ausente impede materialmente um oracle/execução determinística do comportamento afetado."),
            ("Cobertura / Identificadores cobertos", "Quantos identificadores da autoridade têm uma relação explícita de teste/disposição. Cobertura não significa que todos os testes passaram."),
            ("Quality gates", "Verificações determinísticas de integridade/qualidade que protegem escopo, baseline, referências, procedimentos, integridade do pipeline e publicação."),
            ("Baseline histórico", "Comparação opcional com um baseline histórico explicitamente carregado. NOT_APPLIED significa que nenhum baseline histórico foi carregado — não é uma falha."),
        ]),
        ("Conceitos de automação", [
            ("Automatizáveis", "Casos cuja adequação à automação (automation suitability) é HIGH ou MEDIUM, conforme a métrica já implementada no relatório."),
            ("Automação pronta", "Casos cuja prontidão para automação (automation readiness) indica que as fixtures/ambiente/seletores/dependências hoje conhecidos são suficientes, conforme o contrato já existente da FTD."),
        ]),
        ("Expansão (segunda passada)", [
            ("Candidatos", "Cenários candidatos materialmente relevantes considerados em uma dimensão. Não é o número de TCs finais."),
            ("Materializados", "Candidatos que viraram Test Cases canônicos adicionais."),
            ("Já cobertos", "Candidatos já exercidos semanticamente por um TC existente; nenhum TC duplicado foi criado."),
            ("Pergunta", "Candidatos que não puderam virar um TC determinístico com segurança; uma Pergunta foi criada."),
            ("Não aplicável", "A dimensão foi avaliada mas não se aplica ao comportamento real do projeto — zero não significa que foi pulada."),
            *[(f"{code} — {label}", description) for code, (label, description) in EXPANSION_DIMENSION_INFO["pt"].items()],
        ]),
    ],
    "en": [
        ("Test Case nature", [
            ("Normative / Acceptance", "Test Cases derived directly from normative authority requirements/rules and the frozen normative baseline."),
            ("Derived", "Additional deterministic Test Cases derived semantically from known rules, relationships, states or failure behavior, without inventing a new requirement."),
            ("Characterization", "Tests documenting observed implementation behavior, especially where it must be understood separately from normative expectation."),
            ("Exploratory", "A hypothesis/scenario worth investigating when a complete deterministic oracle/policy is not established."),
            ("E2E", "A composed end-to-end journey spanning multiple atomic behaviors/stages."),
        ]),
        ("Execution / readiness status", [
            ("READY", "Enough grounded information exists to execute the TC as designed."),
            ("NEEDS_REVIEW", "The scenario is valid, but a material uncertainty or missing execution detail requires review/clarification."),
            ("BLOCKED", "Execution depends on an unavailable external dependency/environment/equipment or another blocking condition."),
            ("EXPLORATORY", "The case is intentionally exploratory rather than a deterministic normative pass/fail test."),
            ("Execution open item", "An uncertainty recorded in the procedure (for example MISSING_EXECUTION_SURFACE or UNKNOWN_SETUP_PATH), shown on the TC with what it means and the case's own detail. It is not a Question: a Question appears only when the analysis created one."),
        ]),
        ("Automation: suitability / readiness", [
            ("MEDIUM / NEEDS_FIXTURE", "The automation badge reads suitability / readiness: how worthwhile automating the case is (HIGH, MEDIUM, LOW, MANUAL_ONLY) and what is still missing to automate it."),
            ("READY", "Nothing is missing to automate the case."),
            ("NEEDS_POLICY", "A rule, permission or expected result still has to be decided."),
            ("NEEDS_ENVIRONMENT", "A suitable environment or execution surface is missing."),
            ("NEEDS_FIXTURE", "Deterministic test data or a known setup path is missing."),
            ("NEEDS_SELECTOR", "A stable UI selector or identifier is missing."),
            ("BLOCKED_EXTERNAL_DEPENDENCY", "Depends on an unavailable external system."),
            ("NOT_APPLICABLE", "The case is MANUAL_ONLY; automation readiness does not apply."),
        ]),
        ("Priority", [
            ("CRITICAL", "Failure can break a core flow, integrity/security, an irreversible transition, critical auditability, or similarly severe behavior."),
            ("HIGH", "High-impact functional or operational failure requiring strong coverage."),
            ("MEDIUM", "Relevant behavior with moderate impact."),
            ("LOW", "Lower-impact, supporting or cosmetic behavior."),
        ]),
        ("QA / expansion concepts", [
            ("Operator error", "Scenarios exploring plausible human/operator mistakes: wrong resource, association, actor, state, sequence, and similar."),
            ("Chaos / Recovery", "Failure/recovery behavior involving dependencies, interruptions, restart, retry, partial failure, or similar operational disruption."),
            ("Concurrency", "Simultaneous/racing actions, idempotency and state consistency under concurrent execution."),
            ("Security / Authorization", "Authentication/authorization/access-control/security behavior represented in the suite."),
            ("Families", "Scenario families used to organize related Test Cases for review."),
            ("Merge Candidates", "Cases that may be similar enough for human review of possible consolidation; they are not automatically merged."),
        ]),
        ("Analysis / quality concepts", [
            ("Findings", "Evidence-backed discrepancies, conflicts or notable implementation observations found during analysis. A Finding is not automatically synonymous with a failed Test Case."),
            ("Questions", "Open Questions created where selected evidence is insufficient or ambiguous and inventing an answer would be unsafe."),
            ("Blocking Question", "A Question whose missing answer materially prevents a deterministic oracle/execution for the affected behavior."),
            ("Coverage / Identifiers covered", "How many authoritative identifiers have an explicit test/disposition relationship. Coverage does not mean all tests passed."),
            ("Quality gates", "Deterministic integrity/quality checks protecting scope, baseline, references, procedures, pipeline integrity and publication."),
            ("Historical baseline", "Optional comparison against an explicitly loaded historical baseline. NOT_APPLIED means no historical baseline was loaded — not a failure."),
        ]),
        ("Automation concepts", [
            ("Automatable", "Cases whose automation suitability is HIGH or MEDIUM according to the report's existing metric."),
            ("Automation ready", "Cases whose automation readiness indicates the currently known fixtures/environment/selectors/dependencies are sufficient, per the existing FTD contract."),
        ]),
        ("Expansion (second pass)", [
            ("Candidates", "Materially relevant scenario candidates considered for a dimension. Not the number of final TCs."),
            ("Materialized", "Candidates that became additional canonical Test Cases."),
            ("Already covered", "Candidates already semantically exercised by an existing TC; no duplicate TC was created."),
            ("Question", "Candidates that could not safely become a deterministic TC; a Question was created instead."),
            ("Not applicable", "The dimension was evaluated but did not apply to the project's actual behavior — zero does not mean it was skipped."),
            *[(f"{code} — {label}", description) for code, (label, description) in EXPANSION_DIMENSION_INFO["en"].items()],
        ]),
    ],
}


def render_glossary(labels: dict[str, str], language: str) -> str:
    categories = GLOSSARY.get(language, GLOSSARY["en"])
    sections = "".join(
        f'<div class="glossary-group"><h3>{esc(category)}</h3><dl class="glossary-list">' +
        "".join(f"<dt>{esc(term)}</dt><dd>{esc(description)}</dd>" for term, description in terms) +
        "</dl></div>"
        for category, terms in categories
    )
    return f'<section id="glossary"><h2>{esc(labels["glossary_title"])}</h2><div class="glossary-grid">{sections}</div></section>'


def render_report(output_dir: Path, destination: Path | None = None, artifact_formats: set[str] | None = None) -> Path:
    output_dir = Path(output_dir).resolve()
    errors = validate(output_dir)
    if errors:
        raise ValueError("Output validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    artifact_formats = {"JSON", "MARKDOWN"} if artifact_formats is None else set(artifact_formats)
    index = read_json(output_dir / "test-cases.json")
    labels = labels_for(index)
    language = str(index.get("output_locale", "en")).split("-", 1)[0].casefold()
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
    findings_by_id = {item["id"]: item for item in index.get("findings", [])}
    questions_by_id = {item["id"]: item for item in questions}
    groups_html = []
    for group_id in group_order:
        members = [(entry, case) for entry, case in zip(index["test_cases"], cases) if group_of[case["id"]][0] == group_id]
        if not members:
            continue
        title = group_of[members[0][1]["id"]][1]
        # One authoritative identifier can be touched by several TCs, and one TC can
        # touch several identifiers; the modal paginates by identifier, never by TC.
        pages: dict[str, dict[str, Any]] = {}
        for _, case in members:
            for key, page_title in _case_requirement_keys(case, requirements):
                pages.setdefault(key, {"title": page_title, "cases": []})["cases"].append(case)
        req_line = "; ".join(f"{key} — {page['title']}" if page["title"] != key else key for key, page in pages.items())
        templates = "".join(
            render_case_template(case, entry, mermaid_by_id[case["id"]], labels, requirements, group_id, title,
                                 _case_flags(case, merge_ids, question_case_ids), artifact_formats,
                                 findings_by_id, questions_by_id)
            for entry, case in members
        )
        # The default page is the whole family: exactly the unique TCs the card counts.
        req_pages_html = render_requirement_page(
            group_id, labels["all"], title, [case for _, case in members], labels, scope="all",
        ) + "".join(
            render_requirement_page(group_id, key, page["title"], page["cases"], labels)
            for key, page in pages.items()
        )
        groups_html.append(
            f'<section class="tc-group" id="family-{esc(group_id)}" data-family="{esc(group_id)}">'
            f'<div class="tc-group-card">'
            f'<div><h3>{esc(title)}</h3><span><span class="tc-count">{len(members)}</span> TCs &middot; {esc(req_line)}</span></div>'
            f'<button type="button" class="open-group" data-family="{esc(group_id)}">{esc(labels["open_group"])}</button>'
            f'</div>{templates}{req_pages_html}</section>'
        )

    # With a publication organization, the case list offers views over the same Test Cases:
    # functional (default, placement order), families, each execution view, and all.
    # Every view references the single global template of each case; nothing is cloned.
    organization_path = output_dir / "organization.json"
    if organization_path.is_file():
        organization = read_json(organization_path)
        post_suite = organization.get("post_suite_cases", [])
        if post_suite and "rationale" not in post_suite[0]:  # published refs only: no bodies to show
            organization = {**organization, "post_suite_cases": []}
        views, post_templates = _organization_views(organization, cases, labels, requirements)
        views.insert(1, ("families", labels["view_families"], "".join(groups_html)))
        tabs = "".join(
            f'<button type="button" class="view-tab" role="tab" data-view="{esc(view)}" '
            f'aria-selected="{"true" if position == 0 else "false"}">{esc(title)}</button>'
            for position, (view, title, _) in enumerate(views))
        case_list_html = (
            f'<div class="view-tabs" role="tablist">{tabs}</div>'
            + "".join(f'<div class="case-view" data-view="{esc(view)}"{"" if position == 0 else " hidden"}>{body}</div>'
                      for position, (view, _, body) in enumerate(views))
            + post_templates)
    else:
        case_list_html = "".join(groups_html)

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
    expansion_help = (
        f'<div class="expansion-help"><h3>{esc(labels["expansion_help_title"])}</h3><dl class="technical-grid">'
        f'<dt>{esc(labels["candidates"])}</dt><dd>{esc(labels["candidates_help"])}</dd>'
        f'<dt>{esc(labels["materialized"])}</dt><dd>{esc(labels["materialized_help"])}</dd>'
        f'<dt>{esc(labels["covered"])}</dt><dd>{esc(labels["covered_help"])}</dd>'
        f'<dt>{esc(labels["question_required"])}</dt><dd>{esc(labels["question_required_help"])}</dd>'
        f'<dt>{esc(labels["not_applicable"])}</dt><dd>{esc(labels["not_applicable_help"])}</dd></dl></div>'
    )
    expansion_rows = "".join(
        (lambda dim_label, dim_desc:
         f'<tr><td><span class="dimension-name" title="{esc(dim_desc)}">{esc(item["dimension"])} &mdash; {esc(dim_label)}</span></td>'
         f'<td>{item["candidates_considered"]}</td><td>{item["materialized"]}</td>'
         f'<td>{item["already_covered"]}</td><td>{item["question_required"]}</td><td>{item["not_applicable"]}</td></tr>'
        )(*dimension_info(item["dimension"], language))
        for item in index.get("expansion_summary", [])
    )
    expansion_legend = "".join(
        f'<dt>{esc(code)} &mdash; {esc(label)}</dt><dd>{esc(description)}</dd>'
        for code, (label, description) in EXPANSION_DIMENSION_INFO.get(language, EXPANSION_DIMENSION_INFO["en"]).items()
    )
    expansion_html = (
        expansion_help +
        (f'<div class="table-wrap"><table><thead><tr><th>{esc(labels["dimension"])}</th><th>{esc(labels["candidates"])}</th>'
        f'<th>{esc(labels["materialized"])}</th><th>{esc(labels["covered"])}</th><th>{esc(labels["question_required"])}</th>'
        f'<th>{esc(labels["not_applicable"])}</th></tr></thead><tbody>{expansion_rows}</tbody></table></div>'
        if expansion_rows else f'<p class="empty">{esc(labels["none"])}</p>')
        + f'<details class="expansion-legend"><summary>{esc(labels["dimension_all"])}</summary>'
        f'<dl class="technical-grid">{expansion_legend}</dl></details>'
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
:root {{ --ink:#182027; --muted:#5f6b73; --line:#d7dfe3; --surface:#fff; --soft:#f3f6f7; --accent:#087f5b; --accent-soft:#eaf7f2; --warning:#9a6700; --warning-soft:#fff8e6; --danger:#b42318; --danger-soft:#fdecea; --info:#3949ab; --info-soft:#f0f1ff; --shadow:0 8px 24px rgba(26,43,52,.07); --shadow-lift:0 12px 28px rgba(26,43,52,.12); --radius:10px; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:var(--soft); font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }}
body.modal-open {{ overflow:hidden; }}
.shell {{ width:min(1200px,calc(100% - 32px)); margin:0 auto; }}
header {{ position:sticky; top:0; z-index:20; background:rgba(255,255,255,.97); backdrop-filter:blur(4px); border-bottom:1px solid var(--line); padding:18px 0 10px; }}
h1 {{ margin:0 0 4px; font-size:26px; font-weight:800; letter-spacing:-.01em; }}
h2 {{ margin:0 0 16px; font-size:20px; font-weight:800; padding-bottom:8px; border-bottom:2px solid var(--line); }}
h3 {{ margin:0 0 8px; font-size:15px; font-weight:750; }}
.muted,.empty,.subtitle {{ color:var(--muted); }}
.empty {{ padding:14px; border:1px dashed var(--line); border-radius:var(--radius); background:#fff; }}
nav {{ display:flex; gap:4px; flex-wrap:wrap; margin-top:14px; }}
nav a {{ padding:6px 10px; border-radius:6px; text-decoration:none; font-weight:650; font-size:13px; color:var(--muted); }}
nav a:hover,nav a:focus-visible {{ background:var(--soft); color:var(--ink); }}
main {{ padding:24px 0 56px; }} main>section {{ padding:22px 0; border-bottom:1px solid var(--line); }} main>section:last-child {{ border-bottom:none; }}
a,button,input,select,summary,[tabindex] {{ outline-offset:2px; }}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,[tabindex]:focus-visible {{ outline:2px solid var(--accent); }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }}
.metric {{ background:#fff; border:1px solid var(--line); border-radius:var(--radius); padding:12px 14px; box-shadow:var(--shadow); }}
.metric strong {{ display:block; font-size:23px; font-weight:800; }} .metric span {{ color:var(--muted); font-size:12.5px; }}
.run-info {{ margin-top:14px; display:flex; gap:20px; flex-wrap:wrap; font-size:13.5px; }}
.filter-panel {{ padding:16px; border:1px solid var(--line); border-radius:var(--radius); background:#fff; margin-bottom:18px; box-shadow:var(--shadow); }}
.filters {{ display:grid; grid-template-columns:minmax(200px,1fr) repeat(4,minmax(130px,190px)); gap:10px; }}
.filters label {{ font-size:12.5px; font-weight:650; color:var(--muted); }}
button {{ border:1px solid #aeb7bc; border-radius:6px; background:#fff; padding:7px 12px; font:inherit; font-weight:600; cursor:pointer; transition:background-color .12s,box-shadow .12s; }}
button:hover:not(:disabled) {{ background:var(--soft); }} button:disabled {{ opacity:.5; cursor:not-allowed; }}
input,select {{ width:100%; min-height:38px; border:1px solid #aeb7bc; border-radius:6px; padding:7px 9px; font:inherit; background:#fff; margin-top:4px; }}
.tc-group {{ margin:16px 0; }}
.view-tabs {{ display:flex; flex-wrap:wrap; gap:6px; margin:16px 0 4px; }}
.view-tab {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:6px 14px; cursor:pointer; font:inherit; font-size:13px; }}
.view-tab[aria-selected="true"] {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
.badge.post-suite {{ border-style:dashed; }}
.tc-group-card {{ display:flex; align-items:center; gap:14px; padding:16px; border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:var(--radius); background:#fff; box-shadow:var(--shadow); transition:box-shadow .15s; }}
.tc-group-card:hover {{ box-shadow:var(--shadow-lift); }}
.tc-group-card h3 {{ margin:0 0 3px; font-size:16.5px; }} .tc-group-card span {{ color:var(--muted); font-size:12.5px; line-height:1.5; }}
.open-group {{ margin-left:auto; font-weight:700; border-color:var(--accent); color:var(--accent); flex-shrink:0; }}
.tc-heading {{ display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
.identifier-chips {{ display:inline-flex; gap:4px; flex-wrap:wrap; }}
.chip {{ border:1px solid #9fd8c6; background:var(--accent-soft); color:#075e47; border-radius:4px; padding:1px 6px; font-size:11px; font-weight:700; }}
.tc-id {{ color:var(--muted); font-size:13px; white-space:nowrap; font-weight:600; }}
.badges {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}
.badge {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 9px; font-size:10.5px; font-weight:750; letter-spacing:.02em; white-space:nowrap; }}
.status-ready {{ color:#08633f; background:#eaf7f0; border-color:#b8dfc9; }} .status-needs_review {{ color:#765500; background:#fff6dd; }}
.status-exploratory,.test-basis,.dimension,.automation {{ color:var(--info); background:var(--info-soft); border-color:#c5cae9; }}
[class*="status-blocked"] {{ color:#8f1d14; background:#fff0ee; }}
.badge-finding {{ color:#7a4a00; background:var(--warning-soft); border-color:#f0dca6; }}
.badge-question {{ color:#1e3a8a; background:#eaf1ff; border-color:#bcd2f7; }}
.tc-detail-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; padding-bottom:12px; border-bottom:1px solid var(--line); margin-bottom:14px; }}
.tc-detail-head .tc-heading {{ font-size:15.5px; font-weight:700; }}
.tc-content {{ padding:0; }} .tc-content>section {{ margin-bottom:18px; }}
.two-column {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
.related-requirements {{ color:var(--muted); font-size:13px; }}
.table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; background:#fff; margin-bottom:14px; }}
th,td {{ border:1px solid var(--line); padding:9px 11px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }} th {{ background:#f0f3f2; font-size:12.5px; font-weight:750; }}
.step-number {{ width:48px; text-align:center; font-weight:700; }}
.flow-section {{ margin-top:16px; border:1px solid var(--line); border-radius:8px; background:#fbfcfc; padding:14px; }}
.flow-heading {{ display:flex; align-items:center; justify-content:space-between; }}
.mermaid-container {{ overflow-x:auto; background:#fff; }} .mermaid-svg {{ display:block; width:100%; min-width:520px; max-width:760px; margin:0 auto; }}
.node-label-title {{ font-weight:700; }}
dialog {{ border:none; padding:0; box-shadow:var(--shadow-lift); border-radius:var(--radius); }}
dialog::backdrop {{ background:rgba(20,29,34,.72); }}
.flow-modal {{ width:min(1040px,calc(100% - 40px)); max-height:calc(100vh - 40px); }}
.flow-modal-panel {{ max-height:calc(100vh - 40px); overflow:auto; padding:16px; }}
.tc-modal {{ width:min(1180px,calc(100% - 32px)); max-height:calc(100vh - 48px); }}
.tc-modal-panel {{ display:flex; flex-direction:column; max-height:calc(100vh - 48px); }}
.tc-modal-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:14px; padding:16px 20px; border-bottom:1px solid var(--line); position:sticky; top:0; background:#fff; z-index:2; border-radius:var(--radius) var(--radius) 0 0; }}
.tc-modal-header h3 {{ margin:0; font-size:19px; }} .tc-modal-header p {{ margin:2px 0 0; font-size:12.5px; }}
.tc-modal-body {{ padding:18px 20px; overflow:auto; background:var(--soft); }}
.tc-modal-footer {{ display:flex; align-items:center; gap:16px; padding:12px 20px; border-top:1px solid var(--line); position:sticky; bottom:0; background:#fff; flex-wrap:wrap; border-radius:0 0 var(--radius) var(--radius); }}
.tc-position {{ font-weight:700; font-size:13px; }}
.tc-page-pick {{ font-size:13px; }} .tc-page-pick select {{ margin-left:4px; max-width:260px; }}
.modal-close {{ font-size:20px; line-height:1; padding:4px 10px; }}
.tc-row-list {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px; }}
.tc-row {{ border:1px solid var(--line); border-radius:8px; background:#fff; box-shadow:var(--shadow); overflow:hidden; }}
.tc-row-toggle {{ width:100%; display:flex; align-items:center; gap:10px; padding:11px 14px; border:none; background:transparent; text-align:left; cursor:pointer; font-weight:650; border-radius:0; }}
.tc-row-toggle:hover {{ background:var(--soft); }}
.tc-row-chevron {{ flex-shrink:0; transition:transform .15s; color:var(--muted); }}
.tc-row-toggle[aria-expanded="true"] .tc-row-chevron {{ transform:rotate(90deg); }}
.tc-row-id {{ color:var(--muted); font-size:12.5px; font-weight:700; flex-shrink:0; }}
.tc-row-title {{ flex:1; min-width:120px; }}
.tc-row-body {{ border-top:1px solid var(--line); padding:16px; background:#fff; }}
.req-page-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin-bottom:14px; flex-wrap:wrap; }}
.req-page-head h4 {{ margin:0; font-size:17px; font-weight:800; }}
.req-page-empty {{ margin-top:10px; }}
.tc-alerts {{ margin-bottom:18px; padding:14px; border:1px solid #f0dca6; border-radius:8px; background:var(--warning-soft); }}
.tc-alerts h3 {{ margin-top:0; }}
.pendency-item {{ padding:10px 12px; margin-top:10px; border:1px dashed #d9b24c; border-radius:8px; background:#fff; }}
.pendency-item p {{ margin:6px 0 0; }}
.artifact-links {{ display:flex; gap:10px; }} .artifact-links a {{ border:1px solid #aeb7bc; border-radius:6px; padding:6px 10px; text-decoration:none; }}
.technical {{ margin-top:12px; color:var(--muted); font-size:13px; }}
.technical-grid {{ display:grid; grid-template-columns:max-content 1fr; gap:6px 14px; }} .technical-grid dt {{ font-weight:700; color:var(--ink); }} .technical-grid dd {{ margin:0; }}
.question-item,.finding-item {{ margin-bottom:10px; border:1px solid var(--line); border-left:4px solid var(--warning); border-radius:8px; background:#fff; padding:14px; }}
.finding-item {{ border-left-color:var(--warning); }}
.question-item {{ border-left-color:var(--info); }}
.question-item.blocking {{ border-left-color:var(--danger); background:var(--danger-soft); }}
.question-title,.finding-title {{ display:flex; justify-content:space-between; gap:12px; font-weight:700; }}
.needs-answer {{ color:var(--danger); font-weight:700; }}
.gates li {{ margin-bottom:6px; }}
.expansion-help {{ background:#fff; border:1px solid var(--line); border-radius:var(--radius); padding:14px 16px; margin-bottom:16px; }}
.expansion-help h3 {{ margin-top:0; }}
.dimension-name {{ cursor:help; border-bottom:1px dotted var(--muted); }}
.expansion-legend {{ margin-top:12px; background:#fff; border:1px solid var(--line); border-radius:var(--radius); padding:12px 16px; }}
.expansion-legend summary {{ cursor:pointer; font-weight:700; }}
.expansion-legend[open] summary {{ margin-bottom:10px; }}
.glossary-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:18px; }}
.glossary-group {{ background:#fff; border:1px solid var(--line); border-radius:var(--radius); padding:16px; }}
.glossary-list {{ margin:0; }} .glossary-list dt {{ font-weight:700; margin-top:10px; }} .glossary-list dt:first-child {{ margin-top:0; }}
.glossary-list dd {{ margin:2px 0 0; color:var(--muted); font-size:13px; }}
[hidden] {{ display:none!important; }}
@media (max-width:720px) {{ .filters,.two-column {{ grid-template-columns:1fr; }} .tc-group-card {{ flex-direction:column; align-items:flex-start; }} .open-group {{ margin-left:0; width:100%; }}
  .tc-modal,.flow-modal {{ width:100%; height:100%; max-height:100%; max-width:100%; border-radius:0; margin:0; }} .tc-modal-panel {{ max-height:100%; }}
  .tc-modal-header,.tc-modal-footer {{ border-radius:0; }} .tc-row-toggle {{ flex-wrap:wrap; }} .badges {{ justify-content:flex-start; }} }}
@media print {{ header {{ position:static; }} nav,.filter-panel,.open-group,.expand-flow {{ display:none!important; }} }}
</style>
</head>
<body>
<header><div class="shell"><h1>{esc(labels['report_title'])}</h1><p class="subtitle">{esc(labels['report_subtitle'])}</p>
<nav><a href="#summary">{esc(labels['summary'])}</a><a href="#test-cases">{esc(labels['test_cases'])}</a><a href="#merge">{esc(labels['merge'])}</a><a href="#findings">{esc(labels['findings'])}</a><a href="#questions">{esc(labels['questions'])}</a><a href="#coverage">{esc(labels['coverage'])}</a><a href="#expansion">{esc(labels['expansion'])}</a><a href="#gates">{esc(labels['gates'])}</a><a href="#glossary">{esc(labels['glossary_title'])}</a></nav></div></header>
<main class="shell">
<section id="summary"><h2>{esc(labels['summary'])}</h2><div class="metrics">{metric_html}</div><div class="run-info">{''.join(f'<span>{item}</span>' for item in info)}</div></section>
<section id="test-cases"><h2>{esc(labels['test_cases'])}</h2><div class="filter-panel"><div class="filters">
<label>{esc(labels['search'])}<input id="search" type="search"></label>
<label>{esc(labels['status'])}<select id="status-filter"><option value="">{esc(labels['all'])}</option>{status_options}</select></label>
<label>{esc(labels['priority'])}<select id="priority-filter"><option value="">{esc(labels['all'])}</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label>
<label>{esc(labels['family'])}<select id="family-filter"><option value="">{esc(labels['all'])}</option>{family_options}</select></label>
<label>{esc(labels['feature'])}<select id="feature-filter"><option value="">{esc(labels['all'])}</option>{feature_options}</select></label>
</div></div><div id="case-list">{case_list_html}</div><p id="no-results" hidden>{esc(labels['no_results'])}</p></section>
<section id="merge"><h2>{esc(labels['merge'])}</h2>{merge_html or f'<p class="empty">{esc(labels["no_merge"])}</p>'}</section>
<section id="findings"><h2>{esc(labels['findings'])}</h2>{finding_html or f'<p class="empty">{esc(labels["no_findings"])}</p>'}</section>
<section id="questions"><h2>{esc(labels['questions'])}</h2>{question_html or f'<p class="empty">{esc(labels["no_questions"])}</p>'}</section>
<section id="coverage"><h2>{esc(labels['coverage'])}</h2>{coverage_html}</section>
<section id="expansion"><h2>{esc(labels['expansion'])}</h2>{expansion_html}</section>
<section id="gates"><h2>{esc(labels['gates'])}</h2><ul class="gates">{gate_html or f'<li>{esc(labels["none"])}</li>'}</ul>{f'<h3>{esc(labels["gap_metrics"])}</h3><ul>{gap_html}</ul>' if gap_html else ''}</section>
{render_glossary(labels, language)}
</main>
<dialog id="flow-modal" class="flow-modal"><div class="flow-modal-panel"><button type="button" class="modal-close" aria-label="{esc(labels['modal_close'])}">{esc(labels['close'])}</button><div id="flow-modal-canvas"></div></div></dialog>
<dialog id="tc-modal" class="tc-modal" aria-labelledby="tc-modal-title">
  <div class="tc-modal-panel">
    <div class="tc-modal-header">
      <div><h3 id="tc-modal-title"></h3><p id="tc-modal-count" class="muted"></p></div>
      <button type="button" id="tc-modal-close" class="modal-close" aria-label="{esc(labels['modal_close'])}">&times;</button>
    </div>
    <div class="tc-modal-body" id="tc-modal-body"></div>
    <div class="tc-modal-footer">
      <button type="button" id="tc-prev">&larr; {esc(labels['modal_prev'])}</button>
      <label class="tc-page-pick">{esc(labels['requirement_filter'])} <select id="tc-page-select"></select></label>
      <span id="tc-position" class="tc-position"></span>
      <button type="button" id="tc-next">{esc(labels['modal_next'])} &rarr;</button>
    </div>
  </div>
</dialog>
<script>
const q=id=>document.getElementById(id);
const controls=['search','status-filter','priority-filter','family-filter','feature-filter'].map(q);
const groupEls=[...document.querySelectorAll('.tc-group')];
const tcTemplates=[...document.querySelectorAll('template.tc-template')];
const tcTemplateById={{}};
tcTemplates.forEach(t=>tcTemplateById[t.dataset.id]=t);
const reqTemplates=[...document.querySelectorAll('template.req-template')];
const POS_OF={json.dumps(labels["modal_of"])};
const PAGE_LABEL={json.dumps(labels["modal_page"])};
const TC_COUNT_SUFFIX={json.dumps(labels["tc_count_suffix"])};

function matchesTemplate(tpl){{
  const term=q('search').value.trim().toLocaleLowerCase();
  const status=q('status-filter').value,priority=q('priority-filter').value,family=q('family-filter').value,feature=q('feature-filter').value;
  return (!term||tpl.dataset.search.includes(term))
    &&(!status||tpl.dataset.status===status||(status==='BLOCKED'&&tpl.dataset.status.startsWith('BLOCKED')))
    &&(!priority||tpl.dataset.priority===priority)
    &&(!family||tpl.dataset.family===family)
    &&(!feature||tpl.dataset.features.split(' ').includes(feature));
}}
function matchesId(id){{const tpl=tcTemplateById[id];return tpl?matchesTemplate(tpl):false;}}
function reqPageTcIds(reqTpl){{return [...reqTpl.content.querySelectorAll('.tc-row')].map(li=>li.dataset.id);}}

// A card counts the unique cases on its whole-group page, whatever view it belongs to.
function groupCaseIds(familyId){{
  const all=reqTemplates.find(t=>t.dataset.family===familyId&&t.dataset.scope==='all');
  return all?reqPageTcIds(all):[];
}}
function activeView(){{return document.querySelector('.case-view:not([hidden])');}}
function applyFilters(){{
  let visibleGroups=0;
  const view=activeView();
  groupEls.forEach(group=>{{
    const matched=groupCaseIds(group.dataset.family).filter(matchesId);
    const countEl=group.querySelector('.tc-count');
    if(countEl)countEl.textContent=matched.length;
    const show=matched.length>0;
    group.hidden=!show;
    if(show&&(!view||view.contains(group)))visibleGroups+=1;
    const openBtn=group.querySelector('.open-group');
    if(openBtn)openBtn.disabled=matched.length===0;
  }});
  q('no-results').hidden=visibleGroups!==0;
}}
controls.forEach(control=>control.addEventListener(control.id==='search'?'input':'change',applyFilters));
document.querySelectorAll('.view-tab').forEach(tab=>tab.addEventListener('click',()=>{{
  document.querySelectorAll('.view-tab').forEach(t=>t.setAttribute('aria-selected',String(t===tab)));
  document.querySelectorAll('.case-view').forEach(v=>{{v.hidden=v.dataset.view!==tab.dataset.view;}});
  applyFilters();
}}));

const flowModal=q('flow-modal');const flowCanvas=q('flow-modal-canvas');
function closeFlowModal(){{if(flowModal.open)flowModal.close();flowCanvas.replaceChildren();document.body.classList.remove('modal-open');}}
document.addEventListener('click',event=>{{
  const button=event.target.closest('.expand-flow');
  if(!button)return;
  const container=q(button.dataset.flowTarget);
  const svg=container&&container.querySelector('svg');
  if(!svg)return;
  flowCanvas.replaceChildren(svg.cloneNode(true));
  flowModal.showModal();
  document.body.classList.add('modal-open');
}});
flowModal.querySelector('.modal-close').addEventListener('click',closeFlowModal);
flowModal.addEventListener('click',event=>{{if(event.target===flowModal)closeFlowModal();}});
flowModal.addEventListener('close',closeFlowModal);

// The modal navigates authoritative requirement identifiers, one page at a time.
// Each page's Test Case rows are an accordion: a row's full body is cloned from its
// own global tc-template only the first time it is opened, and stays hidden, never
// removed, once collapsed again.
const tcModal=q('tc-modal');
const tcState={{familyId:null,pages:[],index:0,opener:null}};

function renderNoMatches(){{
  q('tc-modal-body').replaceChildren();
  const empty=document.createElement('p');
  empty.className='empty';
  empty.textContent={json.dumps(labels["no_filter_results"])};
  q('tc-modal-body').appendChild(empty);
  q('tc-modal-title').textContent='';
  q('tc-modal-count').textContent='';
  q('tc-position').hidden=true;q('tc-prev').hidden=true;q('tc-next').hidden=true;
}}

function renderCurrentPage(){{
  const page=tcState.pages[tcState.index];
  if(!page){{renderNoMatches();return;}}
  const clone=page.tpl.content.cloneNode(true);
  clone.querySelectorAll('.tc-row').forEach(li=>{{li.hidden=!page.matchedIds.includes(li.dataset.id);}});
  const emptyMsg=clone.querySelector('.req-page-empty');
  if(emptyMsg)emptyMsg.hidden=page.matchedIds.length>0;
  const countValue=clone.querySelector('.req-page-count-value');
  if(countValue)countValue.textContent=page.matchedIds.length;
  q('tc-modal-body').replaceChildren(clone);
  const isAll=page.scope==='all';
  q('tc-modal-title').textContent=isAll||page.key===page.title?page.title:(page.key+' — '+page.title);
  q('tc-modal-count').textContent=page.matchedIds.length+' '+TC_COUNT_SUFFIX;
  const single=tcState.pages.length<=1;
  q('tc-position').hidden=single;q('tc-prev').hidden=single;q('tc-next').hidden=single;
  q('tc-page-select').parentElement.hidden=single;
  q('tc-page-select').value=String(tcState.index);
  if(!single)q('tc-position').textContent=PAGE_LABEL+' '+(tcState.index+1)+POS_OF+tcState.pages.length;
  q('tc-prev').disabled=tcState.index===0;
  q('tc-next').disabled=tcState.index===tcState.pages.length-1;
}}

function openGroup(familyId,opener){{
  const pages=reqTemplates.filter(t=>t.dataset.family===familyId).map(t=>{{
    const tcIds=reqPageTcIds(t);
    return {{tpl:t,key:t.dataset.key,title:t.dataset.title,scope:t.dataset.scope,tcIds:tcIds,matchedIds:tcIds.filter(matchesId)}};
  }}).filter(p=>p.matchedIds.length>0);
  // Page 0 is always the whole family ("all"), so the modal opens on every unique TC
  // the card counts; the identifier pages after it are refinements, never the default.
  tcState.familyId=familyId;tcState.pages=pages;tcState.index=0;tcState.opener=opener;
  q('tc-page-select').replaceChildren(...pages.map((p,i)=>{{
    const option=document.createElement('option');option.value=String(i);
    option.textContent=p.key+' ('+p.matchedIds.length+')';return option;
  }}));
  renderCurrentPage();
  tcModal.showModal();
  document.body.classList.add('modal-open');
}}
document.querySelectorAll('.open-group').forEach(button=>button.addEventListener('click',()=>{{
  openGroup(button.dataset.family,button);
}}));
q('tc-prev').addEventListener('click',()=>{{if(tcState.index>0){{tcState.index-=1;renderCurrentPage();}}}});
q('tc-next').addEventListener('click',()=>{{if(tcState.index<tcState.pages.length-1){{tcState.index+=1;renderCurrentPage();}}}});
q('tc-page-select').addEventListener('change',event=>{{tcState.index=Number(event.target.value)||0;renderCurrentPage();}});

// Accordion: opening a TC row clones its full body from the global template exactly
// once; closing only hides it. Several rows may stay open at once.
q('tc-modal-body').addEventListener('click',event=>{{
  const toggle=event.target.closest('.tc-row-toggle');
  if(!toggle)return;
  const row=toggle.closest('.tc-row');
  const body=row.querySelector('.tc-row-body');
  const expanded=toggle.getAttribute('aria-expanded')==='true';
  if(!expanded&&!body.dataset.materialized){{
    const tpl=tcTemplateById[row.dataset.id];
    if(tpl)body.appendChild(tpl.content.cloneNode(true));
    body.dataset.materialized='1';
  }}
  toggle.setAttribute('aria-expanded',String(!expanded));
  body.hidden=expanded;
}});

function closeTcModal(){{if(tcModal.open)tcModal.close();document.body.classList.remove('modal-open');}}
q('tc-modal-close').addEventListener('click',closeTcModal);
tcModal.addEventListener('click',event=>{{if(event.target===tcModal)closeTcModal();}});
tcModal.addEventListener('close',()=>{{if(tcState.opener)tcState.opener.focus();}});
tcModal.addEventListener('keydown',event=>{{
  const tag=(document.activeElement&&document.activeElement.tagName)||'';
  if(['INPUT','SELECT','TEXTAREA'].includes(tag))return;
  if(event.key==='ArrowLeft'&&!q('tc-prev').hidden){{event.preventDefault();q('tc-prev').click();}}
  if(event.key==='ArrowRight'&&!q('tc-next').hidden){{event.preventDefault();q('tc-next').click();}}
}});

applyFilters();
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
