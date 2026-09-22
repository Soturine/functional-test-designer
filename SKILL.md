---
name: functional-test-designer
description: Designs traceable, executable functional Test Cases from only user-selected sources. Use for bounded evidence collection, atomic coverage, clarification, readiness audits, selected JSON/Markdown/HTML rendering, and preview-first Test Management export.
---

# Functional Test Designer

Design evidence-grounded functional tests from only the sources explicitly selected by the user. Natural language is the primary interface. `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, and `ftd-mcp` are optional aliases for the same shared intents and core.

## Non-negotiable boundaries

- A selected file authorizes only that file; a selected directory is recursive only below itself.
- Never follow imports, links, siblings, parents, or repository structure outside scope.
- Resolve ambiguous selections before reading content. Order instructions never expand scope.
- Keep `skill_root`, `source_root`, `workspace_root`, and exact `artifact_root` distinct. Never use the skill or source root as an implicit destination.
- Functional authority defines what should happen. Technical context explains how to reach it; implementation evidence shows what exists; QA assets reveal prior coverage. Inspection order never changes authority.
- Never invent an oracle, UI/API path, field, message, credential, identifier format, state, or side effect.
- JSON schema `2.2` is the current public truth; schema `1.2` remains a compatibility input/output contract. Other formats are projections.

Read [output-contract-v2.2.md](references/output-contract-v2.2.md) for current generation, [output-contract.md](references/output-contract.md) for legacy 1.2 compatibility, and [performance-orchestration.md](references/performance-orchestration.md) when resolving scope, destination, run state, checkpoints, or diagnostics.

## Pipeline

```text
Selected sources -> Scope lock -> Source accounting ledger -> Evidence collection/barrier
-> Source-family/unit inventory -> Independent source-first review
-> Atomic source claims -> Clauses -> Coverage Points
-> Normative Acceptance candidates -> Freeze baseline
-> Additive opportunity audit (Test Assets, misuse, risk, characterization, E2E)
-> Scenario families -> Atomic frozen Test identities
-> Procedural enrichment -> Readiness -> Validation
-> Canonical run state -> Selected public projections
```

With no explicit source order, analyze independent selected sources concurrently when safe. When the user says first/then/last, respect ordered barriers while retaining safe concurrency within each group. The principal agent owns semantic reconciliation.

Read these detailed contracts only when their stage is relevant:

- [source-accounting.md](references/source-accounting.md): selected-source ledger, honest read telemetry, independent source-first review, structural inventory.
- [source-coverage-audit.md](references/source-coverage-audit.md): source-first atomic extraction, clause/CP lineage, one bounded recovery.
- [adversarial-coverage.md](references/adversarial-coverage.md): Test Asset inventory, evidence-grounded risk matrix, resilience and recovery, bounded E2E, operational catalog.
- [test-design.md](references/test-design.md): contextual BVA, EP, state, decision-table, pairwise, and risk techniques.
- [evidence-enrichment.md](references/evidence-enrichment.md): selected-source Evidence Packs and provenance.
- [scenario-opportunities.md](references/scenario-opportunities.md): dispositions for normative, divergence, implementation, QA-asset, and bounded E2E opportunities.
- [high-recall-design.md](references/high-recall-design.md): v2.2 Scenario Families, test bases, non-destructive merge candidates, risk expansion, and quality gates.
- [additive-expansion.md](references/additive-expansion.md): v2.2.1 baseline preservation, source units, challenge sets, reachability, evidence references, and additive dispositions.
- [pipeline-integrity.md](references/pipeline-integrity.md): v2.2.2 runtime-owned gates, stage manifest, identifier/physical ledgers, Claim exercise, and publication integrity.
- [procedural-execution.md](references/procedural-execution.md) and [procedural-readiness.md](references/procedural-readiness.md): post-freeze steps and human/automation readiness.
- [cross-rf-audit.md](references/cross-rf-audit.md): advisory overlap analysis without automatic deletion or merge.

## Atomicity and identity

- Account for every resolved selected source before reasoning about its content; a source that stays unread needs a recorded reason, and a source with no disposition fails the run.
- Produce the source-first inventory as a genuinely separate reading that withholds the final scenario, Test Case, and suite-size counts. A reformatted copy of the primary claims is not a second opinion.
- Inventory structural units before summarizing them. One requirement heading plus N acceptance bullets is not one Claim by default, and a unit that yields no behavior records why.
- Extract atomic normative clauses before summarizing them into logical Requirements.
- Extract atomic source claims before Requirement normalization. Every claim must reach exactly one explicit destination.
- Review suspicious compound Claims and Clauses again after materialization; an upstream summary cannot bypass atomicity merely by arriving pre-compressed.
- Create one independently reviewable candidate per testable CP before grouping.
- Preserve every independently diagnosable candidate as an atomic canonical TC. Shared RF, actor, screen, setup, Evidence Pack, title, event, or navigation may create a merge suggestion but never destroys the atomic view.
- Freeze all normative Acceptance identities and oracles before any derived expansion. Every later phase is additive and must pass baseline preservation.
- Scenario Families organize related atomic, negative, boundary, derived, characterization, and E2E cases. E2E cases explicitly compose atomic TCs.
- Different triggers, actors, permissions, inputs, partitions, states, branches, platforms, or rerunnable Pass/Fail boundaries remain separate.
- Independent legacy subtests become TCs; sequential dependent subtests become steps. Never emit `subtests`.
- Freeze Test identity before procedural enrichment. Enrichment may change preconditions, test data, steps, provenance, observability, and presentation, but not silently redefine valid normative coverage, scenario identity, oracle, status, or disposition.

### 3. Extract and Audit Coverage Points

Map each atomic clause to one atomic Coverage Point or another explicit destination.
`unmapped_normative_clauses` is zero only after every clause-level destination is verified;
the existence of one CP for a Requirement proves nothing about its remaining clauses.

## Executability

Atomic does not mean single-step. Use the documented natural sequence from legitimate preconditions to trigger and observable outcome. Do not inflate steps or hide setup in preconditions. Preserve a one-step case when one supported action is sufficient.

Where setup is material, state how the record or starting state is obtained rather than only asserting that it exists; an unobtainable precondition is not executable. Keep the provenance of procedural detail that came from selected implementation, manual, or technical evidence.

Each step has one executable action and supported observable expected result. Unsupported detail stays visible as a Question, `NEEDS_REVIEW`, or `needs_clarification`; it is never guessed. Classify human and automation readiness without changing the suite to improve the counts.

Reject path compression when one vague action hides a selected-evidence sequence. A testable case is `READY` only when its procedure, data acquisition, trigger, and observations are supported well enough for execution; preserve its frozen identity while using `NEEDS_REVIEW` for material procedural blockers.

## Intents and completion

Read [commands.md](references/commands.md). Ordinary requests and command aliases must normalize to the same shared dispatcher: generation, clarification, read-only audit, rendering from canonical state, and preview-first external mapping.

For clarification, read [clarification.md](references/clarification.md). Record answers as `USER_CLARIFICATION`; conflicts with approved authority remain visible unless explicitly supplied as an authoritative correction.

For output selection, read [output-selection.md](references/output-selection.md). Persist one private canonical state when enabled and render only requested HTML, JSON, Markdown, diagnostics, and the optional operational scenario catalog. Do not publish dead cross-format links.

For integrations, read [mcp-integration.md](references/mcp-integration.md). MCP is transport, never canonical truth. Preview and validate first; require explicit approval for writes; never delete by default; detect external conflicts; use deterministic fallback exports when transport is unavailable.

Before completion:

- validate scope proof, atomic lineage, scenario/TC independence, Questions, Findings, and source provenance;
- account for every meaningful selected-evidence opportunity and link each divergence to coverage or an explicit non-executable disposition;
- account for every discovered Test Asset behavior, every evidence-supported risk condition, and every documented use-case flow, using characterization plus a focused Question wherever the expected behavior is undefined;
- confirm human/automation readiness classifications and reason codes;
- validate canonical state and selected projections;
- validate the ordered run manifest, canonical digest, publication digests, and runtime-owned gate evidence; never accept a final gate verdict from a generation request;
- confirm render did not reread project sources;
- preserve schema `2.2` plus `1.2` compatibility, exact artifact destination, offline HTML, Mermaid parity, and zero `subtests`;
- report real diagnostics only, without source content, answers, credentials, or secrets, marking unobservable read, concurrency, and reasoning telemetry as unavailable instead of zero.
