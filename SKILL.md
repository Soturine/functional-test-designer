---
name: functional-test-designer
description: Designs traceable, executable functional Test Cases from only user-selected sources for any domain. Use for atomic normative coverage, a mandatory second QA pass (negative, operator error, concurrency, recovery, security, E2E), existing-test challenge, executable procedures, readiness and automation classification, offline HTML/Markdown/JSON, an optional post-suite /ftd-chaos pass over a finalized run, and local Azure DevOps Test Plans input JSON (/ftd-azure).
---

# Functional Test Designer

A QA method encoded as a skill. **You do the QA reasoning; the runtime enforces the few invariants that protect quality.** The semantic core is yours: understanding requirements, inferring the domain, decomposing behavior, finding contradictions, imagining operator mistakes and failures, and writing procedures. The runtime owns scope, source accounting, identifiers, ids, validation, canonical state and publication. It never invents scenarios and never decides business meaning.

This works for any project: logistics, ERP, SaaS, APIs, IoT, industrial, aerospace, finance, healthcare, mobile. Use the vocabulary of the selected sources, never of another project.

## Boundaries

- A selected file authorizes only that file; a selected directory is recursive only below itself. Never follow imports, links or neighbours outside the selection.
- Every selected source has an explicit role: `FUNCTIONAL_AUTHORITY` (what must happen), `IMPLEMENTATION_EVIDENCE` (what exists), `TECHNICAL_CONTEXT` (how to reach it), `TEST_ASSET` (existing tests: a challenge set, never authority). Conventional test files inside an `IMPLEMENTATION_EVIDENCE` selection are challenged too, keeping their role.
- Never invent an oracle, route, label, field, message, credential, id format or state. Unknowns become Questions or procedure unknowns.
- Write every human-readable text in the run's `output_locale` (explicit request > authority language > request language). Keep code symbols, endpoints, constants, enums, fields, ids and filenames verbatim.
- The artifact root must be an explicit user destination, never the skill root or the source root.

## Commands

```text
/ftd-gen   --input-file "<path>/instructions.md" --output json,md,html [--diagnostics] [--output-dir <dir>] [--locale <tag>]
/ftd-chaos --run "<run>" [--input-file "<path>/instructions.md"] [--output json,md,html]
/ftd-azure --run "<run>" --output json [--chaos-id <id> ...]
/ftd-clarify · /ftd-check · /ftd-render
```

- **Routing.** Natural language is first-class, and **you** resolve its meaning in context. For example, "do the real tests" means `ftd-gen` for new sources but `ftd-chaos` for an already-finalized suite. Hand off `resolved_intent`; `scripts/workflow.py` only validates exact aliases and dispatches, and holds no phrase list. `ftd-challenge` and `ftd-mcp` are retired and only print migration messages.
- **The instructions file** is `instructions.md` or `instructions.txt`; `instructions.html` is accepted only as a converted form of the same content.
  - It resolves as explicit path > `<workspace>/docs/` > the skill's `docs/`.
  - It is guidance, source-selection intent and seeds, never authority, and its headings are free-form.
  - Run `scripts/workflow.py gen --input-file ...` to get its text and the handoff contract. Interpret it **semantically** into a normalized request: sources with roles and order, output, reading preferences, guidance and seeds. Then rerun with `--normalized <file>`, which persists `<run>/normalized-request.json`.
  - Explicit command options and what the user says now win over the file; the file wins over defaults. Seeds provoke reasoning and never limit it.
  - If a source's authority role is materially ambiguous, ask one concise question instead of promoting evidence.
- **Orchestration.** `/ftd-gen` then drives the pipeline below end to end. Do not ask the user to run stages by hand. Details: [workflow.md](references/workflow.md).

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

With or without an instructions file, you assign each selection a role and pass the requested formats, `--diagnostics`, the explicit source order (`--order`, one group per flag) and any prior clarifications. Finalize applies the requested formats by default.

Unreadable authority (a scanned PDF) needs `--transcription <source>=<text file>`; unusual identifier conventions can use `--id-pattern`.

## Design stage — normative baseline

- **Reading comes first** (`next_stage: reading`). Read sources in parallel by default; decide semantics centrally.
  - **Reader unit.** Each source selector the user declared (a file or a whole directory) is one logical lightweight-reader responsibility: one entry in the work order's `reader_assignments`. A directory stays one semantic source even though the runtime inventories and accounts for every physical file beneath it.
  - **Concurrency.** On Claude, prefer Haiku and run at most `concurrency` readers at once (default 8); later `wave`s wait for a free slot.
  - **How readers work.** Each reader uses ordinary file and navigation tools and returns one selector result: provenance-preserving facts that cite their `file`, plus a `files` entry (CATALOGED, INSPECTED or FAILED) for every pending file it owns. It reports the model that actually ran. It never writes helper scripts to automate cataloging and never makes Test Design decisions.
  - **Sharding.** Split an oversized selector into internal shards only when real context limits require it. Shards are submitted with the same `selector_id` and reconcile back into one selector catalog.
  - **Submission.** Submit with `pipeline.py reading-submit`, then run `pipeline.py reading-reconcile`, which refuses while any physical file is unaccounted.
  - **User preferences win.** Honor a worker count, a model, or "sequential" / "no subagents". For no subagents, restart with `--reading-strategy SEQUENTIAL` and read the sources yourself. Never claim a model or mode you did not use.
  - **Reuse.** Unchanged files reuse cached catalogs (`REUSED`); only changed files under a selector are read again.
  - **Semantic barrier.** While readers finish, you may prepare an authority-only normative skeleton: identifiers, titles and candidate obligations. The domain model, claims, Test Cases, Findings and Questions are decided, and Design is submitted, only after reconciliation.
- **You alone own the semantic synthesis**, working from the reconciled catalog, the evidence snapshots and `authority-text/`:
  - decomposing requirements into claims and deciding oracles;
  - judging the conflicts listed in the reconciliation;
  - writing `domain_model`: actors, entities, states, operations, invariants, permissions, integrations, events, dependencies, observables and failure surfaces;
  - everything downstream.
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
- Write **one procedure for both a novice human and an automation agent**. When the evidence supports it, each step says who acts, where, which single action, on which target, with which semantic data, and what becomes observable.
  - Whole steps such as "access the system", "perform the operation", "validate it", "check if it worked", "continue the flow" or "do everything required" are rejected.
  - Never invent selectors, test ids, labels, screens, routes, URLs, endpoints, credentials, DB columns, device commands, messages or timeouts. A missing one stays an unknown.
  - The canonical Test Case stays tool-agnostic. Preconditions → setup, test data → fixtures, action → operation, expected → assertion; see [method.md](references/method.md).
- Every step is one action with an observable expected result. Use one step only when one action completes the failure domain (`single_step_reason`); never compress a multi-action flow.
- READY never needs fabricated literal data. Record only real unknowns: material ones (`MISSING_ORACLE`, `AMBIGUOUS_POLICY`, `UNRESOLVED_PERMISSION`, `MISSING_EXECUTION_SURFACE`, `UNKNOWN_SETUP_PATH`, `EXTERNAL_DEPENDENCY_UNAVAILABLE`) make it NEEDS_REVIEW or BLOCKED; automation-only ones (`MISSING_FIXTURE`, `MISSING_SELECTOR`, `MISSING_ENVIRONMENT`) only affect automation readiness.
- Procedures come after the suite is frozen: they never add, delete, merge, retitle or re-oracle a test. The oracle step observes the designed expected result.
- Ground each procedure in the selected evidence: `evidence_refs` (source + section) or an honest path unknown (`MISSING_EXECUTION_SURFACE`, `UNKNOWN_SETUP_PATH`). Use visible labels, one imperative action per step, setup in preconditions, and no generic "log in" step unless authentication is what is tested. Work family batch by family batch from the work order's `evidence_index` and excerpts; do not reread the corpus per Test Case.
- Classify `automation.suitability` (`HIGH/MEDIUM/LOW/MANUAL_ONLY`) and `automation.layer` (`UI/API/SERVICE/INTEGRATION/HARDWARE/MIXED`) independently of readiness.

## Helper intents

Clarify at most five high-impact Questions per round (`ftd-clarify`). `ftd-check` audits a published suite read-only. `ftd-render` re-renders a validated run from canonical state (`python scripts/pipeline.py render --run <run>`). See [workflow.md](references/workflow.md).

## /ftd-chaos — post-suite pass (optional)

Generate the canonical suite first; run `/ftd-chaos` second. It is the real-world, adverse, field, physical and absurd-scenario pass over the frozen suite: operator mistakes, devices and manual work, recovery, external dependencies, load ideas and unexpected sequences, as far as this project's evidence supports. It never rewrites the suite. The public entry point is `scripts/workflow.py chaos --run <run> [--input-file ...]`; the internals stay in `scripts/challenge.py` under `<run>/challenges/<id>/`.

- **Context.** Reuse the parent run's persisted context (domain model, canonical cases, Findings, Questions, authority excerpts, evidence index) instead of rereading sources. For more evidence, run a real bounded lookup (`scripts/challenge.py lookup --source <path> --query "..."` or `--lines A-B`). Only an actual lookup counts toward `runtime_targeted_lookups`.
- **Seeds** come from the instructions file (items `instructions.md#seed-NNN`), from the parent's saved `normalized-request.json`, or from Markdown seed files. They are inspiration, never authority. Disposition every item honestly: `MATERIALIZED`, `ALREADY_COVERED` with a real `covered_by`, `MERGED`, `QUESTIONED` or `NOT_APPLICABLE`. Then go beyond the seeds.
- **Case rules.** New cases get `CH-*` ids, never `TC-*`, and are grounded like procedures, under the same ubiquitous-procedure rules. A physical, manual or non-automatable case stays in the plan. `STARTED → SUBMITTED → FINALIZED` is one-way; a mistake is corrected with a new chaos id.
- **Immutability.** The parent's canonical digest is checked at every step. A normative-looking discovery becomes an advisory `canonical_gap_candidate`, never a patch.
- **Outputs.** `finalize` writes the Manual/Physical/Field Test Plan and publishes `output/chaos/<id>/` (`chaos-cases.json`, `seed-dispositions.json`, `chaos-plan.md`, `chaos-plan.html`) in the requested formats.

## /ftd-azure — local Azure DevOps input

`/ftd-azure --run <run> --output json` converts validated FTD state into local JSON under `output/azure/`: the canonical suite plus all finalized chaos runs, or only those picked with `--chaos-id`.

- `azure-export-package.json` is grouped requirement by requirement, titled `identifier — official title`, with `Unassigned` last.
- `azure-preview.json` holds the create/update/unchanged diff and the Suite placements.
- Keys are `canonical:TC-001` and `chaos:<id>:CH-001`; older `challenge:` keys are migrated. A multi-requirement case is one work item with several placements.
- `scripts/azure_export.py` aggregates; `scripts/integrations/azure_devops.py` alone owns Azure mapping, Suites, diffing, idempotency and transport.
- It never contacts Azure DevOps. Live publication needs a future, explicit user request.

## Completion

Finalize produces `output/` (HTML report, JSON, Markdown per Test Case) and a verified manifest. Report honestly: identifier dispositions, gap metrics (`0 gaps` only when every gap dimension is zero), open Questions, Findings, readiness, and `baseline: NOT_APPLIED` unless a benchmark baseline was loaded. Output contract: [output-contract.md](references/output-contract.md). Gates and metrics: [validation.md](references/validation.md).
