# Changelog

## 2.3.0

Simplification, quality recovery and model-first design.

- Consolidated 41 script modules into 11 (`common`, `sources`, `design`, `expansion`, `procedures`, `validation`, `pipeline`, `render`, `workflow`, `benchmark`, `integrations/azure_devops`) and 28 gates into 8 (`SCOPE_VALID`, `SOURCE_COVERAGE_VALID`, `NORMATIVE_BASELINE_VALID`, `ADDITIVE_EXPANSION_VALID`, `PROCEDURE_QUALITY_VALID`, `EVIDENCE_AND_REFERENCE_VALID`, `PIPELINE_INTEGRITY_VALID`, `PUBLICATION_VALID`). References went from 22 files to 6.
- Selected sources are the entry point. The model submits three stages (`design`, `expansion`, `procedures`) as JSON inside the official manifest; the runtime owns scope, identifiers, ids, validation, canonical state and publication. Pre-authored semantic request fields are rejected.
- The semantic core stays LLM-driven and domain-agnostic: universal reasoning dimensions, a project-derived `domain_model`, 14 operator-error patterns and 15 failure surfaces interpreted in the project's own terms. No project vocabulary lives in production code; six multi-domain packs (A–F) prove generality.
- Added `output_locale` with its source, official identifier titles (never `RF001 — header` as a test title), explicit identifier dispositions and a runtime-derived identifier ledger.
- Made the 17-dimension second pass mandatory, with operator-error and chaos/recovery checklists, existing tests as a semantic challenge set, characterization, and E2E journeys composed of real atomic stages for every use case.
- Split `automation_suitability` from `automation_readiness`. READY no longer requires literal data: only material unknowns affect execution status.
- Added a priority rubric, simple Scenario Families, advisory merge candidates, honest six-dimension `gap_metrics` ("0 gaps" only when all are zero) and benchmark-only baselines that report `NOT_APPLIED` when not loaded.
- Preserved the public workflow: natural language first, `ftd-gen/clarify/check/render/mcp`, multiple files and directories, source order, output formats, diagnostics, prior clarifications and exact destination.
- Cross-requirement traceability: `related_identifiers` keeps every authoritative relationship in `requirement_refs`/`source_identifiers`, shown as chips on the collapsed HTML card.
- Semantic guards (no new gate family): a `structure_reviews` reason is required when a multi-item authority unit becomes one claim; copied intents are rejected; happy-path tests cannot cover adversarial scenarios; converging test assets must share a failure domain or oracle; one Question across several failure surfaces needs a `shared_policy`.
- Procedures are grounded and cheap: they run on frozen identities, cite `evidence_refs` or declare the path gap, reject generic authentication boilerplate, work in family batches from an indexed evidence context with zero source rereads, and report `procedure_generation_seconds`, `targeted_source_lookups`, `procedures_requiring_additional_evidence` and related diagnostics.
- Public schema stays 2.2 (additive optional fields); schema 1.2 suites still validate and render; legacy gate names are still accepted by the validator.

## 2.2.2

- Added an ordered, hash-chained runtime manifest for every official generation stage, canonical state, and published artifact.
- Made gate results runtime-owned and rejected request-supplied quality verdicts.
- Added atomic CP-to-Acceptance, Claim-to-Step/assertion, source-identifier, use-case-flow, Scenario Family, E2E-stage, automation, priority, and historical-baseline gates.
- Added official physical-source, identifier, claim-exercise, and Test Asset challenge diagnostics.
- Added publication tamper detection and an official validator mode using `--manifest`.
- Preserved public schema 2.2, schema 1.2 compatibility, additive expansion, canonical atomic TCs, and advisory-only merge candidates.

## 2.2.1

- Added a mandatory frozen normative baseline and a preservation gate before additive expansion.
- Added below-file normative-unit and use-case-flow accounting.
- Required explicit dispositions and materialization for supported risk, misuse, Test Asset, and characterization opportunities.
- Added physical evidence-reference, semantic E2E-composition, and Test Data reachability gates.
- Added procedure-template, priority-distribution, full-run provenance, and additive-layer diagnostics.
- Added advisory merge-candidate IDs/details, renderer counters, UTF-8 title fallback, and terminal run-state hygiene.
- Preserved public schema 2.2, schema 1.2 compatibility, atomic Acceptance identities, normative oracles, and zero destructive merges.

## 2.2.0

- Added an authority-aware source-universe gate before atomic extraction.
- Made the canonical design atomic-first: Scenario Families organize multiple independent Test Cases without deleting them.
- Replaced destructive shared-execution merging with non-destructive merge-candidate metadata.
- Added Acceptance, Characterization, Derived, Exploratory, Regression, and E2E test bases.
- Added explicit execution status, primary test taxonomy, automation hints, reciprocal Question/Finding links, and E2E composition.
- Added independent quality gates, expanded diagnostics, benchmark reconciliation, and stronger cross-reference validation.
- Updated Markdown and offline HTML to expose test basis, blocked states, merge candidates, E2E composition, automation candidates, and separate test-basis counters.
- Preserved schema 1.2 validation and rendering as a compatibility path.
