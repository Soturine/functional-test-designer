---
name: functional-test-designer
description: Designs traceable, executable functional Test Cases from only user-selected sources for any domain. Use for atomic normative coverage, a mandatory second QA pass (negative, operator error, concurrency, recovery, security, E2E), existing-test challenge, executable procedures, readiness and automation classification, offline HTML/Markdown/JSON, and preview-first Test Management export.
---

# Functional Test Designer

A QA method encoded as a skill. **You do the QA reasoning; the runtime enforces the few invariants that protect quality.** The semantic core is yours: understanding requirements, inferring the domain, decomposing behavior, finding contradictions, imagining operator mistakes and failures, and writing procedures. The runtime owns scope, source accounting, identifiers, ids, validation, canonical state and publication. It never invents scenarios and never decides business meaning.

This works for any project: logistics, ERP, SaaS, APIs, IoT, industrial, aerospace, finance, healthcare, mobile. Use the vocabulary of the selected sources, never of another project.

## Boundaries

- A selected file authorizes only that file; a selected directory is recursive only below itself. Never follow imports, links or neighbours outside the selection.
- Every selected source has an explicit role: `FUNCTIONAL_AUTHORITY` (what must happen), `IMPLEMENTATION_EVIDENCE` (what exists), `TECHNICAL_CONTEXT` (how to reach it), `TEST_ASSET` (existing tests: a challenge set, never authority).
- Never invent an oracle, route, label, field, message, credential, id format or state. Unknowns become Questions or procedure unknowns.
- Write every human-readable text in the run's `output_locale` (explicit request > authority language > request language). Keep code symbols, endpoints, constants, enums, fields, ids and filenames verbatim.
- The artifact root must be an explicit user destination, never the skill root or the source root.

## The pipeline

```text
start (runtime)     scope lock → source records → authority identifiers/titles → locale → test assets
design (you)        domain model → requirements → atomic claims → atomic Acceptance tests → dispositions
                    ── normative baseline frozen ──
expansion (you)     17 dimensions evaluated · operator-error patterns · failure surfaces · test-asset
                    challenge · characterization · E2E journeys          (additive only)
procedures (you)    executable steps · semantic fixtures · unknowns · automation suitability/layer
finalize (runtime)  validation (8 gates) → canonical state → HTML / JSON / Markdown → publication proof
```

```bash
python scripts/pipeline.py start --workspace <root> --source "<selector>=FUNCTIONAL_AUTHORITY" \
    [--source "<selector>=IMPLEMENTATION_EVIDENCE" ...] --artifact-root <dest> --run-id <id> [--locale pt-BR]
# read <run>/work-order.json, write the stage payload, then:
python scripts/pipeline.py submit --run <run> --stage design --file design.json
python scripts/pipeline.py submit --run <run> --stage expansion --file expansion.json
python scripts/pipeline.py submit --run <run> --stage procedures --file procedures.json
python scripts/pipeline.py finalize --run <run> --formats HTML,JSON,MARKDOWN
```

After each command read the new `work-order.json`: it lists what the next stage must account for (authority identifiers with official titles, frozen tests, dimensions, checklists, discovered test assets, Test Cases needing procedures). A rejected stage returns every problem at once and records nothing; fix and resubmit. Exact payload fields: [stage-contracts.md](references/stage-contracts.md). Method detail: [method.md](references/method.md). Techniques: [test-design.md](references/test-design.md).

The user's request stays natural ("Use this PDF, `docs/user`, `apps` and `config`, generate the Test Cases, save HTML/JSON/Markdown and enable diagnostics"): you assign each selection a role and pass the requested formats (`--formats`), `--diagnostics`, explicit source order (`--order`, one group per flag) and prior clarifications; finalize applies the requested formats by default.

Unreadable authority (a scanned PDF) needs `--transcription <source>=<text file>`; unusual identifier conventions can use `--id-pattern`.

## Design stage — normative baseline

- Read every selected source yourself. Build a lightweight `domain_model` from them: actors, entities, states, operations, invariants, permissions, integrations, events, dependencies, observables, failure surfaces.
- One requirement per authority identifier. Keep `source_identifier` and `source_title` exactly as the authority states them; the runtime rejects altered titles and invented identifiers.
- Decompose **requirements and business rules alike** into atomic claims. Transversal rules (uniqueness, audit, role matrices, state machines, deduplication, idempotency, history/KPIs, isolation, lifecycle) get their own claims; do not let requirement bullets overshadow them.
- One independently diagnosable failure domain → one atomic Acceptance test. Status change, balance update, audit record and alert triggered by one action are four tests. One audit record's fields may stay one test when they form an indivisible contract — say so in `indivisible_contract`.
- Every authority identifier ends exercised by tests or explicitly `QUESTION_REQUIRED`, `NOT_TESTABLE_WITH_REASON` or `SUPERSEDED_BY_AUTHORITY`. Normative behavior without implementation evidence is still designed; missing implementation becomes a procedure blocker, never a reason to drop it.
- Do not over-compress: when an authority unit lists several items (bullets, sentences, flow steps) and you keep it as one claim, add a `structure_reviews` entry explaining why. The runtime counts items; it never interprets them.
- Keep every authoritative relationship: a test whose scenario also involves other identifiers lists them in `related_identifiers`. With its claims' identifiers they become the test's `requirement_refs`/`source_identifiers` and show as chips on the collapsed HTML card (`TC-001 <title> [REQ-A] [POLICY-B]`).
- Priority (`CRITICAL/HIGH/MEDIUM/LOW`) follows impact: core flow blockage, integrity corruption, security, cross-account leakage, irreversible transitions, auditability, major SLA, recovery, supporting/cosmetic. Always give a short reason.

## Expansion stage — mandatory second pass

The baseline is frozen; expansion only adds. Evaluate every dimension: `NEGATIVE, BOUNDARY, OPERATOR_ERROR, MISUSE, STATE_TRANSITION, DECISION_TABLE, CONCURRENCY, RACE_CONDITION, IDEMPOTENCY, INTEGRATION, RECOVERY, CHAOS, SECURITY, AUTHORIZATION, DATA_INTEGRITY, CROSS_REQUIREMENT, E2E`. Discover candidates from requirements, rules, state models, implementation, existing tests, integrations and the physical/operational workflow. A zero-result dimension is valid only with a summary of how it was evaluated.

- Operator error: walk every universal mistake (wrong resource, wrong association, wrong actor, wrong state, wrong sequence, repeated/omitted action, stale/partial operation, cross-context mistake, physical/digital mismatch, wrong acknowledgement, manual after automatic, abandoned operation). Interpret each in this project's terms, or mark it `NOT_APPLICABLE` with the project-specific reason.
- Chaos/recovery: walk every failure surface (external dependency, network, middleware, device/hardware, cache, database, async worker, retry, duplicate/out-of-order event, partial commit, process restart, session interruption, concurrency, race). Only materialize surfaces that exist in this project. Defined policy → deterministic `DERIVED` test; undefined policy → `EXPLORATORY` test with safe invariants plus a Question.
- Existing tests: normalize each discovered test's intent and disposition it (`ALREADY_COVERED_BY`, `PROMOTE_DERIVED`, `PROMOTE_CHARACTERIZATION`, `QUESTION_REQUIRED`, `TECHNICAL_ONLY`, `DUPLICATE`, `OUT_OF_SCOPE_WITH_REASON`). Coverage is checked on actor, state, trigger, failure domain and expected outcome; a generic test does not cover an unrelated behavior.
- Write each covered intent in your own words for that behavior; an intent copied from the target, or an adversarial scenario (operator error, misuse, chaos, security) "covered" by a happy-path Acceptance test, is rejected. Several independent failure surfaces answered by one Question need a `shared_policy` naming the single decision they share.
- `CHARACTERIZATION` documents current implementation behavior with an implementation oracle; divergences from authority become Findings, never new requirements.
- E2E: after atomics, compose journeys stage by stage from at least two atomic tests; every documented use case gets a journey disposition.

## Procedures stage — executable Test Cases

- Preconditions state the real starting context (never `Preconditions for: <title>`). Test data uses deterministic semantic fixtures (`ROLE_A`, `ENTITY_ACTIVE_A`, `ACCOUNT_B`) with clear properties; real values only when evidence gives them.
- Every step is one action with an observable expected result. One step only when one action completes the failure domain (`single_step_reason`); never compress a multi-action flow.
- READY never needs fabricated literal data. Record only real unknowns: material ones (`MISSING_ORACLE`, `AMBIGUOUS_POLICY`, `UNRESOLVED_PERMISSION`, `MISSING_EXECUTION_SURFACE`, `UNKNOWN_SETUP_PATH`, `EXTERNAL_DEPENDENCY_UNAVAILABLE`) make it NEEDS_REVIEW or BLOCKED; automation-only ones (`MISSING_FIXTURE`, `MISSING_SELECTOR`, `MISSING_ENVIRONMENT`) only affect automation readiness.
- Procedures come after the suite is frozen: they never add, delete, merge, retitle or re-oracle a test. The oracle step observes the designed expected result.
- Ground each procedure in the selected evidence: `evidence_refs` (source + section) or an honest path unknown (`MISSING_EXECUTION_SURFACE`, `UNKNOWN_SETUP_PATH`). Use visible labels, one imperative action per step, setup in preconditions, and no generic "log in" step unless authentication is what is tested. Work family batch by family batch from the work order's `evidence_index` and excerpts; do not reread the corpus per Test Case.
- Classify `automation.suitability` (`HIGH/MEDIUM/LOW/MANUAL_ONLY`) and `automation.layer` (`UI/API/SERVICE/INTEGRATION/HARDWARE/MIXED`) independently of readiness.

## Other intents

Natural language is primary; `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, `ftd-mcp` are optional aliases through `scripts/workflow.py`. Clarify at most five high-impact Questions per round. `ftd-check` audits a published suite read-only. `ftd-render` re-renders a validated run from canonical state (`python scripts/pipeline.py render --run <run>`). `ftd-mcp` previews an Azure DevOps export and writes nothing without explicit approval. See [workflow.md](references/workflow.md).

## Completion

Finalize produces `output/` (HTML report, JSON, Markdown per Test Case) and a verified manifest. Report honestly: identifier dispositions, gap metrics (`0 gaps` only when every gap dimension is zero), open Questions, Findings, readiness, and `baseline: NOT_APPLIED` unless a benchmark baseline was loaded. Output contract: [output-contract.md](references/output-contract.md). Gates and metrics: [validation.md](references/validation.md).
