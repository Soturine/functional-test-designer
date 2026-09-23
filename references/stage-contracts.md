# Stage contracts

Each model stage is one JSON object submitted with `python scripts/pipeline.py submit --run <run> --stage <stage> --file <payload.json>`. Unknown top-level or procedure fields are rejected: status, ids, gates, coverage dispositions and readiness are runtime-owned. Keys (`key`) are yours; the runtime assigns `REQ-`, `CLAIM-`, `CP-`, `TC-`, `SCN-`, `Q-`, `FND-` ids. Tests may be referenced by key or, after design, by their `TC-` id.

Complete worked payloads for six domains live in `benchmarks/domains/*.json` (`stages.design`, `stages.expansion`, `stages.procedures`).

## design

```json
{
  "domain_model": {"actors": [], "entities": [], "states": [], "operations": [], "invariants": [],
                   "permissions": [], "integrations": [], "events": [], "dependencies": [],
                   "observables": [], "failure_surfaces": []},
  "requirements": [{"key": "RF-01", "source_identifier": "RF-01", "source_title": "optional; must equal the authority title",
                    "source_statement": "what the authority requires", "source_refs": [{"source": "path", "reference": "locator"}],
                    "status": "TESTABLE"}],
  "claims": [{"key": "C1", "requirement": "RF-01", "text": "one observable obligation", "identifiers": ["RN-04"],
              "destination": "TEST | QUESTION | NOT_TESTABLE | FINDING", "question": "Q key", "finding": "F key",
              "reason": "for NOT_TESTABLE", "indivisible_contract": "only when the text is one indivisible observation"}],
  "tests": [{"key": "T1", "claims": ["C1"], "title": "", "objective": "", "family": "Scenario Family title",
             "actor": "", "state": "", "trigger": "", "expected": "the oracle", "failure_domain": "",
             "primary_type": "FUNCTIONAL", "priority": "HIGH", "priority_reason": "",
             "indivisible_contract": "required when claims has more than one", "event": "optional business event",
             "related_identifiers": ["RN-02"], "questions": ["Q key"], "findings": ["F key"]}],
  "structure_reviews": [{"identifier": "RF-03", "reason": "why several listed items are one obligation"}],
  "dispositions": [{"identifier": "RN-09", "disposition": "QUESTION_REQUIRED | NOT_TESTABLE_WITH_REASON | SUPERSEDED_BY_AUTHORITY",
                    "reason": "", "question": "Q key", "superseded_by": "RN-10"}],
  "questions": [{"key": "Q1", "question": "", "reason": "", "requirements": ["RF-01"], "tests": ["T1"],
                 "impact": "EXPECTED_RESULT", "blocking": false, "source_refs": []}],
  "findings": [{"key": "F1", "type": "IMPLEMENTATION_DIVERGENCE | SOURCE_CONFLICT | COVERAGE_GAP | INFORMATION",
                "statement": "", "requirements": ["RF-01"], "tests": ["T1"], "source_refs": [{"source": "", "reference": ""}],
                "coverage_disposition": "COVERED_BY_EXISTING_SCENARIO"}]
}
```

- `domain_model.actors`, `entities`, `operations` must be non-empty; values come from the sources.
- The requirement's `source_identifier` is added to each of its claims' `identifiers`; add other identifiers a claim satisfies (a business rule exercised by a requirement's claim).
- An identifier is `COVERED_BY_ATOMIC_TC` / `COVERED_BY_MULTIPLE_ATOMIC_TCS` when Acceptance tests exercise its claims; `BLOCKED_EXTERNAL_DEPENDENCY` is derived when all of those tests are blocked by an unavailable dependency. Explicit dispositions are only for identifiers that no test exercises.
- `related_identifiers` keeps every authoritative relationship visible: the test's `requirement_refs`/`source_identifiers` are its claims' identifiers plus these (each must exist in authority). The HTML card shows them as chips.
- Over-compression guard: the runtime counts each identifier's structural items (bullets, substantive sentences). An identifier with two or more items and a single claim needs a `structure_reviews` reason (≥ 5 words), or more claims.
- Rejected: compound claim text without `indivisible_contract`, tests over several claims without it, `NOT_TESTABLE` because implementation is missing, altered titles, identifiers absent from authority, text in another language than the run locale.
- Question `impact`: `EXECUTION_DETAIL, TEST_DATA, ACTOR_PERMISSION, EXPECTED_RESULT, ENVIRONMENT, SCOPE, IMPLEMENTATION_LOCATION, REQUIREMENT_AMBIGUITY`.
- `primary_type`: `FUNCTIONAL, NEGATIVE, BOUNDARY, SECURITY, AUTHORIZATION, PERFORMANCE, RESILIENCE, RECOVERY, CONCURRENCY, RACE_CONDITION, IDEMPOTENCY, INTEGRATION, CONTRACT, DATA_INTEGRITY, AUDIT, STATE_TRANSITION, E2E, FIELD, HARDWARE_INTEGRATION, CHAOS, EXPLORATORY`.

## expansion

```json
{
  "dimensions": [{
    "dimension": "OPERATOR_ERROR",
    "summary": "how this dimension was evaluated across every family",
    "candidates": [{
      "key": "O1", "description": "", "pattern": "WRONG_RESOURCE", "surface": "NETWORK", "use_case": "CU-01",
      "disposition": "MATERIALIZED | ALREADY_COVERED | QUESTION_REQUIRED | NOT_APPLICABLE",
      "test": {"key": "D1", "basis": "DERIVED | CHARACTERIZATION | EXPLORATORY", "anchors": ["C4"],
               "oracle_source": {"source": "", "reference": ""}, "questions": [], "findings": [],
               "...": "same intent fields as a design test"},
      "covered_by": ["T4"], "intent": {"actor": "", "state": "", "trigger": "", "failure_domain": "", "expected": ""},
      "question": "Q key", "reason": "", "shared_policy": "when one Question answers several surfaces"
    }],
    "patterns_reviewed": [{"items": ["WRONG_RESOURCE"], "status": "CANDIDATES"},
                          {"items": ["ABANDONED_OPERATION"], "status": "NOT_APPLICABLE", "reason": ""}],
    "surfaces_reviewed": "only on CHAOS, same shape, over the failure surfaces"
  }],
  "test_assets": [{"asset": "path::test_name", "disposition": "ALREADY_COVERED_BY | PROMOTE_DERIVED | PROMOTE_CHARACTERIZATION | QUESTION_REQUIRED | TECHNICAL_ONLY | DUPLICATE | OUT_OF_SCOPE_WITH_REASON",
                   "intent": {"actor": "", "state": "", "trigger": "", "failure_domain": "", "expected": ""},
                   "covered_by": ["T1"], "test": {}, "dimension": "for promotions", "question": "", "duplicate_of": "", "reason": ""}],
  "questions": [], "findings": []
}
```

- All 17 dimensions appear once. `OPERATOR_ERROR` carries `patterns_reviewed` covering every operator pattern; `CHAOS` carries `surfaces_reviewed` covering every failure surface. `CANDIDATES` items must have at least one candidate (in any dimension) carrying that `pattern`/`surface`.
- `DERIVED` needs `oracle_source` in Functional Authority; `CHARACTERIZATION` in implementation evidence or a test asset; `EXPLORATORY` links a Question. Every non-E2E test anchors to design claims with destination `TEST`.
- `ALREADY_COVERED` needs the candidate intent; alignment against the target test is checked (actor/state/trigger containment ≥ 0.34, failure domain Jaccard ≥ 0.4, expected Jaccard ≥ 0.34) and the scores are kept for audit.
- Coverage is semantic, not lexical: an intent identical to the target's (4 of 5 fields) is rejected as copied; the description must relate to the target (containment ≥ 0.25); candidates in adversarial dimensions (`NEGATIVE`, `BOUNDARY`, `OPERATOR_ERROR`, `MISUSE`, `CONCURRENCY`, `RACE_CONDITION`, `IDEMPOTENCY`, `INTEGRATION`, `RECOVERY`, `CHAOS`, `SECURITY`, `AUTHORIZATION`) or carrying a pattern/surface cannot be covered only by happy-path Acceptance tests (primary type `FUNCTIONAL`, `FIELD` or `PERFORMANCE`). Test assets that converge on the same target must share its failure domain or expected result (Jaccard ≥ 0.4).
- Failure surfaces are not collapsed: several surfaces resolved by one Question need `shared_policy` (≥ 5 words) naming the single decision they share.
- E2E: `dimension: "E2E"` candidates. A `MATERIALIZED` journey's test has `stages: [{"name", "test", "trigger", "observation"}]` over at least two distinct atomic tests; each stage's observation must match the composed test's expected result. Every `USE_CASE` identifier needs an E2E candidate with `use_case`; `ALREADY_COVERED` journeys list at least two atomic tests and a reason.
- Every discovered test asset (listed in the work order) needs exactly one disposition.

## reading (before design)

When `start` plans reader tasks (`next_stage: reading`), every `PLANNED` source needs one reader result. Submit results with `pipeline.py reading-submit --run <run> --file <result.json>` (repeatable; one result or `{"results": [...]}` per file).

```json
{"source_key": "<from reading_tasks>", "path": "docs/spec.md", "content_digest": "<from reading_tasks>",
 "status": "CATALOGED", "reader": {"role": "LIGHTWEIGHT_SOURCE_READER", "model": "<the model that actually ran>"},
 "catalog": {"headings": [], "identifiers": [{"identifier": "REQ-1", "title": "..."}], "actors": [], "entities": [],
             "states": [], "operations": [], "integrations": [], "config_facts": [], "candidate_rules": [], "flows": [],
             "test_assets": [], "excerpts": [{"line_start": 10, "line_end": 14, "text": "..."}],
             "references": [{"target": "other/selected/path"}], "ambiguities": []}}
```

- Reader failures are `"status": "FAILED"` with an `error`. A source is never silently omitted.
- The digest must match. The role is fixed. Excerpt lines must exist in the snapshot.
- Any of `claims`, `tests`, `test_cases`, `oracles`, `findings`, `questions`, `requirements`, `coverage`, `dispositions`, `authority`, `role_override` or `completeness` is rejected: those decisions belong to the main model.
- A submission is all-or-nothing.
- `pipeline.py reading-reconcile --run <run>` then consolidates everything. It preserves conflicting statements with no vote and moves the run to `design`.

## procedures

```json
{"procedures": [{
  "test": "TC-001",
  "preconditions": ["real starting context"],
  "test_data": [{"name": "ENTITY_ACTIVE_A", "description": "entity in state Active owned by ACCOUNT_A"}],
  "steps": [{"action": "", "expected_result": ""}],
  "postconditions": [], "cleanup": [], "notes": [],
  "oracle_step": 2,
  "single_step_reason": "required when there is one step",
  "unknowns": [{"kind": "MISSING_FIXTURE", "detail": "", "question": "Q key"}],
  "evidence_refs": [{"source": "selected path", "reference": "section, function or screen"}],
  "automation": {"suitability": "HIGH | MEDIUM | LOW | MANUAL_ONLY",
                 "layer": "UI | API | SERVICE | INTEGRATION | HARDWARE | MIXED",
                 "tool_hint": "PLAYWRIGHT | API_TEST | TESTSPRITE | PYTEST | OTHER | NONE"}
}]}
```

- One procedure per Test Case. The `oracle_step` (default last) must observe the designed `expected` (containment ≥ 0.4). A `MISSING_ORACLE` unknown allows an empty expected result and must link the Question that asks for it.
- Derived fields: `status` READY / NEEDS_REVIEW / BLOCKED_EXTERNAL_DEPENDENCY / EXPLORATORY, `automation_readiness` READY / NEEDS_FIXTURE / NEEDS_SELECTOR / NEEDS_ENVIRONMENT / NEEDS_POLICY / BLOCKED_EXTERNAL_DEPENDENCY / NOT_APPLICABLE, `automation_candidate = suitability in {HIGH, MEDIUM}`. A blocking Question linked to the test also prevents READY.
- Steps follow the one-procedure-for-humans-and-automation contract in [method.md](method.md): who, where, what, target, data and expected when the evidence supports them. A whole step as vague as "access the system", "perform the operation", "validate it", "check if it worked", "continue the flow" or "do everything required", or an expected result like "it works", is rejected.
- Grounding: each procedure cites `evidence_refs` inside the selected scope, or declares `MISSING_EXECUTION_SURFACE` / `UNKNOWN_SETUP_PATH`. A generic authentication step is rejected unless the test is about authentication. Procedures run on frozen identities: identity, oracle and composition fields are rejected.
- Diagnostics: `procedures_generated`, `procedures_with_evidence_refs`, `procedures_requiring_additional_evidence`, `targeted_source_lookups`, `procedure_generation_seconds`, `average_procedure_generation_seconds`, `runtime_source_rereads` (always 0: sources are read once at start and only digest-checked later), `repeated_step_template_ratio` (a warning above 0.5).
- Rejected: generic preconditions, placeholders (`<...>`, `TBD`), abstract actions ("execute the described flow"), unobservable results ("works as expected"), hidden variants ("valid and invalid", "repeat for each"), a one-step case without reason or that compresses several actions.
