#!/usr/bin/env python3
"""Stage B: expand each frozen test intent into an executable procedure, then classify
human readiness and automation separately.

READY never requires fabricated literal data: deterministic semantic fixtures
(`USER_ROLE_A`, `ENTITY_ACTIVE_A`, `ACCOUNT_B`) are executable when their properties are
clear. A Test Case needs review only when a material unknown remains.
"""

from __future__ import annotations

import re
from typing import Any

from common import StageError, normalize, similarity
from design import check_locale, unknown_keys


SUITABILITY = ("HIGH", "MEDIUM", "LOW", "MANUAL_ONLY")
LAYERS = ("UI", "API", "SERVICE", "INTEGRATION", "HARDWARE", "MIXED")
TOOL_HINTS = ("PLAYWRIGHT", "API_TEST", "TESTSPRITE", "PYTEST", "OTHER", "NONE")
# Unknowns that stop a human from executing or judging the test.
MATERIAL_UNKNOWNS = {
    "MISSING_ORACLE": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "AMBIGUOUS_POLICY": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "UNRESOLVED_PERMISSION": ("NEEDS_REVIEW", "NEEDS_POLICY"),
    "MISSING_EXECUTION_SURFACE": ("NEEDS_REVIEW", "NEEDS_ENVIRONMENT"),
    "UNKNOWN_SETUP_PATH": ("NEEDS_REVIEW", "NEEDS_FIXTURE"),
    "EXTERNAL_DEPENDENCY_UNAVAILABLE": ("BLOCKED_EXTERNAL_DEPENDENCY", "BLOCKED_EXTERNAL_DEPENDENCY"),
}
# Unknowns that only affect automation; a human tester can still run the case.
AUTOMATION_UNKNOWNS = {
    "MISSING_FIXTURE": "NEEDS_FIXTURE",
    "MISSING_SELECTOR": "NEEDS_SELECTOR",
    "MISSING_ENVIRONMENT": "NEEDS_ENVIRONMENT",
}
READINESS_ORDER = (
    "BLOCKED_EXTERNAL_DEPENDENCY", "NEEDS_POLICY", "NEEDS_ENVIRONMENT", "NEEDS_FIXTURE",
    "NEEDS_SELECTOR",
)
PROCEDURE_KEYS = {"procedures"}
PROCEDURE_FIELDS = {
    "test", "preconditions", "test_data", "steps", "postconditions", "cleanup", "oracle_step",
    "single_step_reason", "unknowns", "automation", "notes", "evidence_refs", "execution_variants",
    "request_contract",
}
# How a case can be executed beyond its default surface (e.g. the same flow through a real
# device); used to place the one Test Case in more execution views, never to clone it.
EXECUTION_VARIANT_KINDS = ("PHYSICAL_DEVICE", "SIMULATED_DEVICE", "MANUAL_FIELD")
# The request a load/concurrency experiment repeats, described without tool syntax.
REQUEST_CONTRACT_FIELDS = ("method", "endpoint", "parameters", "body", "fixture_pool", "varies", "measurements")
REQUEST_CONTRACT_REQUIRED = ("method", "endpoint", "measurements")
TOOL_SYNTAX = re.compile(
    r"\b(?:curl\s+-|http\.(?:get|post|put|patch|delete)\s*\(|k6\s+run|jmeter\s+-|locust\s+-|"
    r"artillery\s+run|ab\s+-[nc]|wrk\s+-[tcd])", re.IGNORECASE)
STATE_CONTRACTS = ("SELF_CLEANING", "REQUIRES_FIXTURE_RESET")
# Words that talk about an outcome without saying what it is. An expected result made only of
# these (plus function words) carries no oracle: "an observable result on the affected resource".
_META_OUTCOME = {
    "result", "resul", "outco", "resou", "recur", "syste", "siste", "behav", "behavi", "comport", "data", "dado",
    "dato", "recor", "regis", "item", "iten", "state", "estad", "respo", "opera", "affec", "afeta", "afect",
    "obser", "visib", "visív", "expec", "esper", "corre", "valid", "válid", "appro", "adequ", "value", "valor",
    "relev", "prope", "entit", "entid", "objec", "objet", "eleme", "actio", "ação", "acció", "chang", "mudan",
    "cambi", "effec", "efeit", "efect", "outpu", "saída", "salid", "targe", "alvo", "objetiv", "shown", "displ",
    "prese", "retur", "happe", "occur", "appli", "updat", "refle", "exibi", "mostr", "apres", "retor", "atual",
    "alter", "aplic", "ocorr", "the", "and", "with", "for", "its", "are", "was", "were", "has", "have", "been",
    "into", "from", "that", "this", "não", "uma", "com", "são", "fica", "ficam", "como", "pelo", "pela", "para",
    "sobre", "esta", "está", "every", "each", "all", "todo", "toda", "after", "após", "then", "some", "any",
    "algum", "qualq", "del", "los", "las", "una", "est",
}
# Literals a designed oracle may state: a quoted message, a number, a code. Fixture-shaped
# names (USER_A, ORDER_1) are excluded: stages may legitimately rename semantic fixtures.
ORACLE_LITERAL = re.compile(r'"[^"]+"|“[^”]+”|\b\d+(?:[.,]\d+)?\b|\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b')
TRUNCATED = re.compile(
    r"(?:\b(?:and|or|the|of|to|with|e|ou|de|do|da|com|para|que|y|o|del|con)|[,:;(\-])\s*$|\.\.\.\s*$|…\s*$",
    re.IGNORECASE)
BOILERPLATE_ORACLE_LIMIT = 3


def _outcome_stems(text: str) -> set[str]:
    stems = set()
    for word in re.findall(r"[a-zà-ÿ]+", str(text).lower()):
        if len(word) < 3:
            continue
        if len(word) > 4 and word.endswith("s"):
            word = word[:-1]
        stems.add(word[:5])
    return stems


def semantically_empty(expected: str, fixtures: set[str]) -> bool:
    """True when an expected result names no specific thing: no content word beyond talk about
    'a result', no literal, no fixture."""
    if ORACLE_LITERAL.search(expected) or any(name in expected for name in fixtures):
        return False
    return not (_outcome_stems(expected) - _META_OUTCOME)


def malformed_prose(text: str) -> bool:
    """Cut-off or unbalanced prose: a trailing connector or ellipsis, or unmatched brackets/quotes."""
    if not text:
        return False
    if TRUNCATED.search(text):
        return True
    return any(text.count(a) != text.count(b) for a, b in ("()", "[]", "{}")) or text.count('"') % 2 == 1
# A step performed on behalf of a fixture actor ("As USER_A, ...", "Como USER_A, ...").
ACTING_FIXTURE = re.compile(
    r"^\s*(?:As|Como)\s+(?:(?:the|o|a|os|as|el|la)\s+)?([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")
# Load experiments against a request surface must say which request they repeat.
LOAD_TYPES = {"PERFORMANCE", "CONCURRENCY", "RACE_CONDITION"}
REQUEST_LAYERS = {"API", "INTEGRATION"}
# A request the procedure already names (an HTTP method or a resource path): evidence exists,
# so its contract must travel with the case.
NAMED_REQUEST = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\b|(?<![\w/])/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-{}.]*)*")


def state_contract(cleanup: list[str]) -> str:
    """Who restores state after the case: its own cleanup steps, or a harness that resets
    the fixtures its test_data declares before the next case."""
    return "SELF_CLEANING" if cleanup else "REQUIRES_FIXTURE_RESET"
# Unknowns that honestly explain why a procedure cannot cite its execution path yet.
PATH_UNKNOWNS = {"MISSING_EXECUTION_SURFACE", "UNKNOWN_SETUP_PATH"}

GENERIC_PRECONDITION = re.compile(
    r"^\s*(?:preconditions? for|pr[eé]-?condi[cç][oõ]es? para|precondiciones? para)\b|"
    r"\b(?:as applicable|conforme aplic[aá]vel|se aplic[aá]vel)\b",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"<[^>]+>|\bTBD\b|\bXXX\b|\?\?\?|\ba definir\b", re.IGNORECASE)
_VAGUE_CLAUSE = (
    r"(?:access|open|enter|log into) the (?:system|application|app|platform)|"
    r"(?:perform|execute|do|complete) the (?:operation|action|process|procedure|task)|"
    r"(?:validate|verify|check|confirm) (?:it|this|that|everything|the result)|"
    r"(?:check|verify|see) (?:if|whether) it (?:worked|works|succeeded)|"
    r"(?:continue|proceed with|follow) the (?:flow|process)|"
    r"do (?:everything|all) (?:required|necessary|needed)|"
    r"acess(?:ar|e) o (?:sistema|aplicativo)|"
    r"(?:realiz|execut|efetu|faz|fa[cç])(?:ar|e|er|a) a (?:opera[cç][aã]o|a[cç][aã]o|tarefa)|"
    r"(?:valid|verific|confirm)(?:ar|e|ue) (?:isso|tudo|o resultado)|"
    r"verifi(?:car|que) se (?:funcionou|deu certo)|"
    r"(?:continu|sig)(?:ar|e|a) o fluxo|"
    r"fa(?:zer|[cç]a) tudo (?:o )?que (?:for )?(?:necess[aá]rio|preciso)"
)
ABSTRACT_ACTION = re.compile(
    r"\b(?:execute|perform|carry out|complete) (?:the )?(?:action|operation|process|flow|scenario) "
    r"(?:described|indicated|applicable|appropriate|under test|in the objective)\b|"
    r"\b(?:proceed|continue) (?:as|when) applicable\b|\buse the (?:appropriate|correct) (?:item|record|option)\b|"
    r"\b(?:executar|realizar|acionar|efetuar) (?:a|o) (?:a[cç][aã]o|opera[cç][aã]o|processo|fluxo|cen[aá]rio) "
    r"(?:descrit[oa]|indicad[oa]|aplic[aá]vel|adequad[oa]|em teste|do objetivo)\b|"
    r"\b(?:prosseguir|continuar) conforme (?:necess[aá]rio|aplic[aá]vel)\b|"
    r"\bvalidar que funcionou\b|\bvalidate that it worked\b|"
    # A whole step made only of clauses that name no actor, target or observable:
    # "access the system", "perform the operation", "validate it", "check if it worked",
    # "continue the flow", "do everything required" — alone or chained ("access the
    # system and perform the operation"). Anchored to the full step, so concrete steps
    # that merely start with the same verb are untouched.
    r"^\s*(?:" + _VAGUE_CLAUSE + r")(?:(?:\s*(?:,|;|\band\b|\bthen\b|\bdepois\b|\bent[aã]o\b|\be\b|\by\b|\bluego\b)\s*)+(?:"
    + _VAGUE_CLAUSE + r"))*\s*[.!]?\s*$",
    re.IGNORECASE,
)
ABSTRACT_OBSERVATION = re.compile(
    r"\bthe (?:step|flow|next step) (?:becomes|remains|is) available\b|\bworks as expected\b|"
    r"\bfunciona (?:conforme|como) (?:esperado|o esperado)\b|\b(?:a etapa|o fluxo) (?:fica dispon[ií]vel|segue normalmente)\b|"
    r"\bcomportamento esperado\b|\bexpected behaviou?r\b|"
    r"^\s*(?:it works|it worked|success(?:ful)?|ok|done|funciona|funcionou|deu certo|sucesso)\s*[.!]?\s*$",
    re.IGNORECASE,
)
# An expected result that only restates that the action happened observes nothing:
# "the request is sent", "a resposta é recebida", "o envio é processado".
ACTION_ECHO = re.compile(
    r"^\s*(?:(?:the|a|o|os|as|la|el|las|los|both|all|as duas|os dois|todas as|todos os)\s+)?"
    r"(?:\w+\s+)?(?:request|response|submission|query|call|message|attempt|save|write|"
    r"requisi[cç][aã]o|requisi[cç][oõ]es|resposta|respostas|solicita[cç][aã]o|solicita[cç][oõ]es|envio|consulta|"
    r"grava[cç][aã]o|tentativa|mensagem|chamada|petici[oó]n|respuesta|solicitud|consulta)s?\s+"
    r"(?:is |are |was |were |é |são |foi |foram |fica |ficam |es |son |fue )?"
    r"(?:sent|received|processed|submitted|executed|attempted|made|done|answered|delivered|"
    r"arrives?(?: together)?|enviad[oa]s?|recebid[oa]s?|processad[oa]s?|submetid[oa]s?|executad[oa]s?|"
    r"tentad[oa]s?|feit[oa]s?|respondid[oa]s?|entregue?s?|cheg(?:a|am)(?: junt[oa]s)?|recibid[oa]s?|"
    r"procesad[oa]s?|enviad[oa]s?)\b[^.;]{0,25}[.!]?\s*$|"
    r"^\s*(?:the |o |a )?(?:form|system|formul[aá]rio|sistema)\s+(?:processes|receives|processa|recebe)\s+"
    r"(?:the |a |o )?(?:attempt|submission|request|tentativa|envio|requisi[cç][aã]o)\s*[.!]?\s*$",
    re.IGNORECASE,
)
# "X is shown or access is denied": two different outcomes offered as the oracle.
ALTERNATIVE_OUTCOMES = re.compile(
    r"\b(?:is|are|becomes?|shows?|displays?|accepts?|opens?|é|são|fica|ficam|exibe|mostra|aceita|abre)\b"
    r"[^.;]{0,60}?\s(?:or|ou)\s+(?:(?:the|a|o|os|as)\s+)?[^.;]{0,30}?\b"
    r"(?:is|are|shows?|displays?|denies|denied|rejects?|rejected|opens?|é|são|fica|ficam|exibe|mostra|"
    r"nega|negad[oa]|recusa|recusad[oa]|abre)\b",
    re.IGNORECASE,
)
# Semantic fixtures (ACTOR_A, ENTITY_ACTIVE_A, DEVICE_B) must be described in test_data.
FIXTURE_NAME = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9]\b")
# The fixture naming convention: a role or entity plus a short instance suffix
# (USER_A, ORDER_B, DEVICE_1, PAYMENT_CAPTURED_100, EMAIL_NEW). Such a name is always a
# fixture, even when the same token happens to appear in code or existing tests.
FIXTURE_SHAPE = re.compile(r"_(?:[A-Z]|\d{1,4}|NEW|NOVO|NOVA|NUEVO|NUEVA)$")
ACTION_VERB = re.compile(
    r"\b(?:access|open|search|locate|select|enter|provide|scan|read|confirm|submit|consult|click|"
    r"verify|review|choose|cancel|finalize|save|filter|export|move|pass|start|log in|"
    r"acess|abr|pesquis|localiz|selecion|inform|fornec|confirm|envi|consult|clic|verific|"
    r"revis|escolh|cancel|finaliz|salv|filtr|export|mov|inici|autentic|reconhe[cç])\w*\b|"
    r"\b(?:ler|l[eê]|leia|lendo|passar|passe|passa)\b",
    re.IGNORECASE,
)
SEQUENCE_MARKER = re.compile(
    r"(?:;|\s(?:>|→)\s|\b(?:then|and then|next|after that|depois|e depois|em seguida|e ent[aã]o|ap[oó]s isso)\b)",
    re.IGNORECASE,
)
AUTH_ONLY = re.compile(
    r"^\s*(?:autentic\w*|fa[cç]a login|fazer login|efetuar login|entrar no (?:sistema|aplicativo)|"
    r"logar|log in|sign in|authenticate|iniciar sess[aã]o|iniciar sesi[oó]n)\b[^,;]{0,60}$",
    re.IGNORECASE,
)
AUTH_WORDS = re.compile(r"\b(?:login|autentic|authentic|sign in|senha|password|credencia|credential|sess[aã]o|session)", re.IGNORECASE)
# A step that deliberately changes the environment or suppresses a physical signal to
# create a test condition. How to do that is never invented: the step needs evidence that
# supports it (an evidence_ref whose `supports` lists the step), or the procedure keeps
# the scenario and declares UNKNOWN_SETUP_PATH / MISSING_EXECUTION_SURFACE.
ENVIRONMENT_CONTROL = re.compile(
    r"\b(?:restart|reboot|stop|kill|shut\s*down|power\s*(?:off|down|cycle)|unplug|disconnect|interrupt|"
    r"take\s+down|bring\s+down|throttle|cover|shield|obstruct|block|suppress|jam|"
    r"reinici\w*|deslig\w*|derrub\w*|desconect\w*|interromp\w*|par(?:ar|e)|mat(?:ar|e)|"
    r"cobr(?:ir|a)|blind\w*|obstru\w*|bloque\w*|suprim\w*|impe[cç]\w*|deten\w*|apag(?:ar|ue|a)|cubr\w*|tap(?:ar|e))\b"
    r"[^.;:]{0,50}?\b(?:service|server|process|daemon|worker|container|database|db|broker|queue|network|"
    r"connection|link|power|device|hardware|sensor|reader|antenna|scanner|printer|terminal|signal|tag|label|"
    r"servi[cç]o|servidor|processo|cont[eê]iner|banco(?: de dados)?|fila|rede|conex[aã]o|liga[cç][aã]o|energia|"
    r"dispositivo|equipamento|sensor|leitor|antena|impressora|terminal|sinal|etiqueta|"
    r"servicio|red|conexi[oó]n|equipo|lector|se[nñ]al|base de datos|cola)s?\b|"
    # the same manipulation phrased object-first: "with the label covered", "rede desconectada"
    r"\b(?:service|server|process|container|database|network|connection|power|device|sensor|reader|antenna|"
    r"scanner|signal|tag|label|servi[cç]o|servidor|processo|banco|rede|conex[aã]o|energia|dispositivo|"
    r"equipamento|leitor|antena|sinal|etiqueta|servicio|red|lector|se[nñ]al)s?\b[^.;:]{0,20}?\b"
    r"(?:covered|shielded|blocked|obstructed|disconnected|unplugged|powered (?:off|down)|stopped|killed|"
    r"cobert[oa]s?|blindad[oa]s?|obstru[ií]d[oa]s?|bloquead[oa]s?|desconectad[oa]s?|desligad[oa]s?|"
    r"parad[oa]s?|derrubad[oa]s?|cubiert[oa]s?|apagad[oa]s?|detenid[oa]s?)\b",
    re.IGNORECASE,
)
_COMPARATOR = (
    r"(?:<=|>=|<|>|≤|≥|at most|at least|up to|within|under|below|above|less than|more than|no more than|"
    r"em at[eé]|at[eé]|no m[aá]ximo|no m[ií]nimo|pelo menos|menos de|mais de|dentro de|inferior a|superior a|"
    r"abaixo de|acima de|hasta|en menos de|como m[aá]ximo|como m[ií]nimo|al menos|m[aá]s de|por debajo de|por encima de)"
)
_LOAD_UNIT = (
    r"(?:ms|milliseconds?|milissegundos?|s|sec|seconds?|seg|segundos?|min|minutes?|minutos?|"
    r"(?:requests?|req|requisi[cç][oõ]es|events?|eventos|messages?|mensagens|reads?|readings?|leituras|"
    r"transactions?|transa[cç][oõ]es|transacciones|operations?|opera[cç][oõ]es|operaciones|calls?|chamadas|"
    r"llamadas|solicitudes|peticiones)\s*(?:/|per|por)\s*"
    r"(?:s|sec|second|segundo|min|minute|minuto)|rps|tps|qps|"
    r"(?:concurrent|simultaneous) (?:users?|sessions?|connections?)|"
    r"(?:usu[aá]rios|sess[oõ]es|conex[oõ]es|sesiones|conexiones) (?:simult[aâ]ne[oa]s|concorrentes|concurrentes))"
)
# A pass/fail load, latency or capacity threshold asserted in an expected result.
LOAD_THRESHOLD = re.compile(
    _COMPARATOR + r"\s*(?P<number>\d+(?:[.,]\d+)?)\s*" + _LOAD_UNIT + r"(?![\w/])",
    re.IGNORECASE,
)
INDEPENDENT_VARIANTS = re.compile(
    r"\b(?:separately|execute separately|valid and invalid|each variant|repeat for each|"
    r"cada variante|v[aá]lido e inv[aá]lido|separadamente|repetir para cada)\b",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


# Literal technical content in a step (paths, query strings, inline JSON, code identifiers
# such as reader_name) is data, not actions: it must not be counted as verbs or separators.
_LITERAL = re.compile(r"\S*[/=]\S*|\{[^{}]*\}|\[[^\[\]]*\]|`[^`]*`|\"[^\"]*\"|\b\w*_\w*\b")


def compressed_action(action: str) -> bool:
    """One written action that hides a multi-action sequence."""
    prose = _LITERAL.sub(" ", action)
    verbs = ACTION_VERB.findall(prose)
    markers = SEQUENCE_MARKER.findall(prose)
    commas = prose.count(",")
    return (len(verbs) >= 3 and (markers or commas >= 2)) or (len(verbs) >= 2 and len(markers) >= 1)


def hidden_subtest(action: str) -> bool:
    return bool(INDEPENDENT_VARIANTS.search(action))


def classify(unknowns: list[dict[str, Any]], suitability: str, basis: str, blocking_question: bool) -> dict[str, Any]:
    """Derive execution status and automation readiness from material unknowns only."""
    kinds = [str(item["kind"]) for item in unknowns]
    material = [kind for kind in kinds if kind in MATERIAL_UNKNOWNS]
    if basis == "EXPLORATORY":
        status = "EXPLORATORY"
    elif "EXTERNAL_DEPENDENCY_UNAVAILABLE" in material:
        status = "BLOCKED_EXTERNAL_DEPENDENCY"
    elif material or blocking_question:
        status = "NEEDS_REVIEW"
    else:
        status = "READY"
    readiness_values = [MATERIAL_UNKNOWNS[kind][1] for kind in material]
    readiness_values += [AUTOMATION_UNKNOWNS[kind] for kind in kinds if kind in AUTOMATION_UNKNOWNS]
    if suitability == "MANUAL_ONLY":
        automation_readiness = "NOT_APPLICABLE"
    elif basis == "EXPLORATORY":
        automation_readiness = "NEEDS_POLICY"
    else:
        automation_readiness = next((value for value in READINESS_ORDER if value in readiness_values), "READY")
    return {
        "status": status, "automation_readiness": automation_readiness,
        "readiness_blockers": list(dict.fromkeys(kinds + (["BLOCKING_QUESTION"] if blocking_question else []))),
    }


def validate_procedures(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    errors = unknown_keys(payload, PROCEDURE_KEYS, "procedures")
    locale = context["locale"]
    tests = context["tests"]
    by_ref: dict[str, dict[str, Any]] = {}
    for test in tests:
        by_ref[test["key"]] = test
        by_ref[test["id"]] = test
    question_keys = set(context["question_keys"])
    blocking_by_test = context.get("blocking_by_test", {})
    blocking_questions = set(context.get("blocking_questions", set()))
    source_tokens = set(context.get("source_tokens", set()))
    procedures: dict[str, dict[str, Any]] = {}
    oracle_texts: dict[str, set[str]] = {}
    for item in payload.get("procedures", []) or []:
        ref = _text(item.get("test"))
        test = by_ref.get(ref)
        label = f"procedure for {ref or '<missing>'}"
        if test is None:
            errors.append(f"{label} names an unknown Test Case")
            continue
        if test["id"] in procedures:
            errors.append(f"{label} is supplied twice")
        extra = sorted(set(item) - PROCEDURE_FIELDS)
        if extra:
            errors.append(f"{label} contains runtime-owned or unknown fields {extra}")
        preconditions = [_text(value) for value in item.get("preconditions", []) or [] if _text(value)]
        test_data = item.get("test_data", []) or []
        steps = item.get("steps", []) or []
        if not preconditions:
            errors.append(f"{label} requires the starting context as preconditions")
        for value in preconditions:
            if GENERIC_PRECONDITION.search(value):
                errors.append(f"{label} has a generic precondition {value!r}; state the real starting context")
            check_locale(f"{label}.precondition", value, locale, errors)
        normalized_data = []
        for row in test_data:
            name, description = _text(row.get("name")), _text(row.get("description"))
            if not name or not description:
                errors.append(f"{label} test_data rows require name and description")
            if PLACEHOLDER.search(f"{name} {description}"):
                errors.append(f"{label} test data {name!r} is a placeholder; use a semantic fixture with clear properties")
            check_locale(f"{label}.test_data.{name}", description, locale, errors)
            normalized_data.append({"name": name, "description": description})
        unknowns = []
        for unknown in item.get("unknowns", []) or []:
            kind = str(unknown.get("kind", ""))
            if kind not in MATERIAL_UNKNOWNS and kind not in AUTOMATION_UNKNOWNS:
                errors.append(f"{label} unknown kind {kind!r} is not supported")
            if not _text(unknown.get("detail")):
                errors.append(f"{label} unknown {kind} requires detail")
            question = _text(unknown.get("question")) or None
            if question and question not in question_keys:
                errors.append(f"{label} unknown {kind} links unknown question {question}")
            unknowns.append({"kind": kind, "detail": _text(unknown.get("detail")), "question": question})
        missing_oracle = any(unknown["kind"] == "MISSING_ORACLE" for unknown in unknowns)
        evidence_refs = [dict(ref) for ref in item.get("evidence_refs", []) or [] if isinstance(ref, dict)]
        supported_steps = {int(n) for ref in evidence_refs for n in ref.get("supports", []) or []
                           if str(n).isdigit()}
        path_unknown = any(unknown["kind"] in PATH_UNKNOWNS for unknown in unknowns)
        designed = " ".join(str(test.get(field, "")) for field in ("title", "objective", "trigger", "expected"))
        designed_numbers = {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", designed)}
        if not evidence_refs and not any(unknown["kind"] in PATH_UNKNOWNS for unknown in unknowns):
            errors.append(
                f"{label} is not grounded in selected evidence; cite evidence_refs for the execution path "
                "or declare MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH"
            )
        about_auth = bool(AUTH_WORDS.search(f"{test['title']} {test['trigger']} {test['objective']}"))
        normalized_steps = []
        established = " ".join(preconditions)
        if not steps:
            errors.append(f"{label} requires at least one step")
        for number, step in enumerate(steps, 1):
            action, expected = _text(step.get("action")), _text(step.get("expected_result"))
            if not action:
                errors.append(f"{label} step {number} requires an action")
            if not expected and not missing_oracle:
                errors.append(f"{label} step {number} requires an observable expected_result")
            acting = ACTING_FIXTURE.match(action)
            if acting and not re.search(rf"\b{re.escape(acting.group(1))}\b", established):
                errors.append(
                    f"{label} step {number} acts as {acting.group(1)}, but no precondition or earlier step gives "
                    f"{acting.group(1)} a usable starting context (an open session, a configured credential or "
                    "client, a device in hand); state it in the preconditions")
            established += " " + action
            if ABSTRACT_ACTION.search(action):
                errors.append(f"{label} step {number} action is abstract; say who does which atomic action to which target (and where, with which semantic data) as the evidence supports, or keep the known intent and declare MISSING_EXECUTION_SURFACE / UNKNOWN_SETUP_PATH")
            if expected and ABSTRACT_OBSERVATION.search(expected):
                errors.append(f"{label} step {number} expected result is not observable")
            elif expected and semantically_empty(expected, {row["name"] for row in normalized_data}):
                errors.append(
                    f"{label} step {number} expected result names nothing specific ({expected!r}); say which "
                    "state, message, record, counter or outcome becomes observable")
            for part, text in (("action", action), ("expected result", expected)):
                if malformed_prose(text):
                    errors.append(f"{label} step {number} {part} is truncated or unbalanced: {text[-60:]!r}")
            if expected and ACTION_ECHO.search(expected):
                errors.append(
                    f"{label} step {number} expected result only says the action happened; state what becomes "
                    "observable (status, counter, state, message, record)")
            if expected and ALTERNATIVE_OUTCOMES.search(expected):
                errors.append(
                    f"{label} step {number} expected result offers alternative outcomes; the oracle must be one "
                    "deterministic result — when the policy is unknown, declare it (UNRESOLVED_PERMISSION, "
                    "AMBIGUOUS_POLICY) instead of accepting either")
            if AUTH_ONLY.search(action) and not about_auth:
                errors.append(
                    f"{label} step {number} only authenticates; put the signed-in actor in preconditions and "
                    "describe the real execution path"
                )
            if hidden_subtest(action):
                errors.append(f"{label} step {number} hides independent variants; they belong to separate Test Cases")
            if ENVIRONMENT_CONTROL.search(action) and number not in supported_steps and not path_unknown:
                errors.append(
                    f"{label} step {number} changes the environment or suppresses a signal to create the test "
                    "condition; cite the evidence that says how (an evidence_ref whose `supports` lists this step) "
                    "or keep the scenario and declare UNKNOWN_SETUP_PATH / MISSING_EXECUTION_SURFACE — never invent "
                    "the technique")
            for threshold in LOAD_THRESHOLD.finditer(expected):
                if threshold.group("number").replace(",", ".") not in designed_numbers:
                    errors.append(
                        f"{label} step {number} asserts the threshold {threshold.group(0)!r}, which the designed "
                        "Test Case does not state; an undefined SLA stays undefined — record the observed values "
                        "(rate, latency, errors) as the result and link the Question that asks for the threshold. "
                        "Load schedules belong in the action or test_data as experiment configuration")
            check_locale(f"{label} step {number} action", action, locale, errors)
            check_locale(f"{label} step {number} expected_result", expected, locale, errors)
            normalized_steps.append({
                "step": number, "action": action, "expected_result": expected or None,
                "needs_clarification": not expected,
            })
        variants = []
        for variant in item.get("execution_variants", []) or []:
            kind = _text(variant.get("kind")) if isinstance(variant, dict) else ""
            description = _text(variant.get("description")) if isinstance(variant, dict) else ""
            if kind not in EXECUTION_VARIANT_KINDS:
                errors.append(f"{label} execution_variants kind must be one of {EXECUTION_VARIANT_KINDS}")
            elif len(description.split()) < 4:
                errors.append(f"{label} execution variant {kind} must describe how that execution differs")
            else:
                check_locale(f"{label}.execution_variant", description, locale, errors)
                variants.append({"kind": kind, "description": description})
        contract = None
        raw_contract = item.get("request_contract")
        if raw_contract is not None:
            if not isinstance(raw_contract, dict) or set(raw_contract) - set(REQUEST_CONTRACT_FIELDS):
                errors.append(f"{label} request_contract accepts only {REQUEST_CONTRACT_FIELDS}")
                raw_contract = {}
            contract = {}
            for field in REQUEST_CONTRACT_FIELDS:
                value = raw_contract.get(field)
                contract[field] = ([_text(v) for v in value if _text(v)] if isinstance(value, list)
                                   else _text(value) or None)
            for field in REQUEST_CONTRACT_REQUIRED:
                if not contract[field]:
                    errors.append(f"{label} request_contract.{field} is required")
            contract_text = " ".join(v if isinstance(v, str) else " ".join(v) for v in contract.values() if v)
            if TOOL_SYNTAX.search(contract_text):
                errors.append(f"{label} request_contract describes the request, not a tool invocation")
            for threshold in LOAD_THRESHOLD.finditer(" ".join(contract["measurements"] or [])
                                                      if isinstance(contract["measurements"], list)
                                                      else contract["measurements"] or ""):
                if threshold.group("number").replace(",", ".") not in designed_numbers:
                    errors.append(
                        f"{label} request_contract.measurements asserts {threshold.group(0)!r}, which the designed "
                        "Test Case does not state; measure and record the value instead")
        defined = {row["name"] for row in normalized_data}
        used_text = " ".join([*preconditions, *(s["action"] + " " + (s["expected_result"] or "") for s in normalized_steps),
                              *[variant["description"] for variant in variants],
                              *([str(contract.get("body") or ""), str(contract.get("fixture_pool") or "")] if contract else []),
                              *[_text(v) for v in item.get("postconditions", []) or []],
                              *[_text(v) for v in item.get("cleanup", []) or []]])
        # Codes and constants the selected sources themselves use are vocabulary, not fixtures.
        undefined = sorted(set(FIXTURE_NAME.findall(used_text)) - defined - source_tokens)
        if undefined:
            errors.append(
                f"{label} uses fixtures {undefined} that test_data does not describe; a reader of this Test Case "
                "alone must know who or what each fixture is")
        if len(normalized_steps) == 1:
            action = normalized_steps[0]["action"]
            if len(_text(item.get("single_step_reason")).split()) < 3:
                errors.append(
                    f"{label} has one step; explain in single_step_reason why one action completes the failure domain"
                )
            if compressed_action(action):
                errors.append(f"{label} compresses a multi-action flow into one step: {action!r}")
        oracle_step = int(item.get("oracle_step") or len(normalized_steps) or 1)
        if test["basis"] in {"ACCEPTANCE", "DERIVED", "CHARACTERIZATION"} and normalized_steps and not missing_oracle:
            if not 1 <= oracle_step <= len(normalized_steps):
                errors.append(f"{label} oracle_step {oracle_step} is outside the procedure")
            else:
                observed = normalized_steps[oracle_step - 1]["expected_result"] or ""
                if similarity(observed, test["expected"]) < 0.4:
                    errors.append(
                        f"{label} step {oracle_step} does not observe the designed oracle {test['expected']!r}"
                    )
                lost = [value for value in ORACLE_LITERAL.findall(str(test["expected"]))
                        if not FIXTURE_SHAPE.search(value) and value not in observed and value.strip('"“”') not in observed]
                if lost:
                    errors.append(
                        f"{label} step {oracle_step} drops what the designed oracle states exactly {lost}; keep the "
                        "message, number or code the Test Case is judged by")
                oracle_texts.setdefault(normalize(observed), set()).add(normalize(str(test["expected"])))
        automation = item.get("automation") if isinstance(item.get("automation"), dict) else {}
        suitability = str(automation.get("suitability", ""))
        layer = str(automation.get("layer", ""))
        hint = str(automation.get("tool_hint", "NONE"))
        if suitability not in SUITABILITY:
            errors.append(f"{label} automation.suitability must be one of {SUITABILITY}")
        if layer not in LAYERS:
            errors.append(f"{label} automation.layer must be one of {LAYERS}")
        if hint not in TOOL_HINTS:
            errors.append(f"{label} automation.tool_hint must be one of {TOOL_HINTS}")
        names_request = any(NAMED_REQUEST.search(step["action"]) for step in normalized_steps)
        if test.get("primary_type") in LOAD_TYPES and layer in REQUEST_LAYERS and names_request and contract is None:
            errors.append(
                f"{label} is a {test['primary_type']} experiment on a request its steps name; describe that request in "
                "request_contract (method, endpoint, parameters, body, fixture_pool, varies, measurements) so an "
                "executor can build it without reopening the sources")
        blocking = bool(blocking_by_test.get(test["id"])) or any(
            unknown["question"] in blocking_questions for unknown in unknowns
        )
        classification = classify(unknowns, suitability, test["basis"], blocking)
        for value in item.get("postconditions", []) or []:
            check_locale(f"{label}.postcondition", value, locale, errors)
        procedures[test["id"]] = {
            "preconditions": preconditions, "test_data": normalized_data, "steps": normalized_steps,
            "postconditions": [_text(v) for v in item.get("postconditions", []) or [] if _text(v)],
            "cleanup": [_text(v) for v in item.get("cleanup", []) or [] if _text(v)],
            "notes": [_text(v) for v in item.get("notes", []) or [] if _text(v)],
            "unknowns": unknowns, "oracle_step": oracle_step, "evidence_refs": evidence_refs,
            "single_step_reason": _text(item.get("single_step_reason")) or None,
            "automation_suitability": suitability, "automation_layer": layer,
            "automation_tool_hint": hint, **classification,
            "execution_variants": variants, "request_contract": contract,
        }
        if missing_oracle and not any(u["question"] for u in unknowns if u["kind"] == "MISSING_ORACLE"):
            errors.append(f"{label} MISSING_ORACLE requires the Question that asks for the oracle")
    # One oracle wording shared by procedures designed for different oracles is boilerplate
    # standing in for per-case semantics.
    for observed, designs in oracle_texts.items():
        if observed and len(designs) >= BOILERPLATE_ORACLE_LIMIT:
            errors.append(
                f"{len(designs)} procedures designed for different oracles observe the same result {observed!r}; "
                "each oracle step must observe its own Test Case's oracle")
    missing = [test["id"] for test in tests if test["id"] not in procedures]
    if missing:
        errors.append(f"{len(missing)} Test Case(s) have no procedure: " + ", ".join(missing[:20]))
    if errors:
        raise StageError("procedures", errors)
    return {"procedures": procedures, "warnings": procedure_warnings(procedures), "metrics": procedure_metrics(procedures)}


def source_vocabulary(texts: Any) -> set[str]:
    """Codes and constants the selected sources use (error codes, settings names): not
    fixtures. Fixture-shaped names are never vocabulary, so a fixture used in a procedure
    must be described in its test data even if the token also occurs in the sources."""
    return {token for text in texts for token in FIXTURE_NAME.findall(text or "")
            if not FIXTURE_SHAPE.search(token)}


def _template(action: str) -> str:
    text = re.sub(r"\b[A-Z][A-Z0-9_]{2,}\b", "<fixture>", action)
    return " ".join(re.sub(r"\d+", "<n>", text).casefold().split())


def procedure_metrics(procedures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actions = [_template(step["action"]) for item in procedures.values() for step in item["steps"]]
    counts: dict[str, int] = {}
    for action in actions:
        counts[action] = counts.get(action, 0) + 1
    repeated = sum(count for count in counts.values() if count > 1)
    return {
        "procedures_generated": len(procedures),
        "procedures_with_evidence_refs": sum(bool(item["evidence_refs"]) for item in procedures.values()),
        "procedures_requiring_additional_evidence": sum(
            any(u["kind"] in PATH_UNKNOWNS for u in item["unknowns"]) for item in procedures.values()
        ),
        "distinct_evidence_sources_cited": len({ref.get("source") for item in procedures.values() for ref in item["evidence_refs"]}),
        # Each distinct (source, section) pair is one targeted lookup shared by every procedure citing it.
        "targeted_source_lookups": len({(ref.get("source"), ref.get("reference")) for item in procedures.values()
                                        for ref in item["evidence_refs"]}),
        "repeated_step_template_ratio": round(repeated / len(actions), 3) if actions else 0.0,
    }


def procedure_warnings(procedures: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    metrics = procedure_metrics(procedures)
    if len(procedures) >= 10 and metrics["repeated_step_template_ratio"] > 0.5:
        warnings.append(
            f"PROCEDURE_BOILERPLATE: {metrics['repeated_step_template_ratio']:.0%} of steps repeat another step's template"
        )
    for test_id, procedure in procedures.items():
        for step in procedure["steps"]:
            if len(procedure["steps"]) > 1 and compressed_action(step["action"]):
                warnings.append(f"POSSIBLE_MULTI_ACTION_STEP: {test_id} step {step['step']}")
    return warnings


def audit_case(case: dict[str, Any]) -> list[str]:
    """Read-only quality signals for an already published Test Case (ftd-check)."""
    reasons = []
    steps = case.get("steps", [])
    if not case.get("preconditions"):
        reasons.append("MISSING_STARTING_CONTEXT")
    if any(GENERIC_PRECONDITION.search(str(value)) for value in case.get("preconditions", [])):
        reasons.append("GENERIC_PRECONDITION")
    if not steps:
        reasons.append("MISSING_TRIGGER")
    for step in steps:
        action, expected = str(step.get("action", "")), step.get("expected_result")
        if ABSTRACT_ACTION.search(action):
            reasons.append("ABSTRACT_TRIGGER")
        if expected is None:
            reasons.append("MISSING_OBSERVABLE_ASSERTION")
        elif ABSTRACT_OBSERVATION.search(str(expected)):
            reasons.append("ABSTRACT_OBSERVATION")
        if hidden_subtest(action):
            reasons.append("HIDDEN_SUBTEST")
    if len(steps) == 1 and compressed_action(str(steps[0].get("action", ""))):
        reasons.append("PATH_COMPRESSION")
    if any(PLACEHOLDER.search(f"{row.get('name')} {row.get('description')}") for row in case.get("test_data", [])):
        reasons.append("PLACEHOLDER_TEST_DATA")
    if case.get("status") not in {None, "READY"}:
        reasons.append("STATUS_NOT_READY")
    return list(dict.fromkeys(reasons))
