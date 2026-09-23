# Validation, gates and metrics

A stage that violates an invariant is rejected before anything is recorded, so a published suite carries only passing gates. The gates exist because their failure makes the suite invalid; everything else is a metric or a warning.

| Gate | Protects |
| --- | --- |
| `SCOPE_VALID` | Only selected sources were read; each physical source has one record (role, authority, status, reason, digest). |
| `SOURCE_COVERAGE_VALID` | Every authority identifier is exercised by atomic tests or explicitly dispositioned. |
| `NORMATIVE_BASELINE_VALID` | Every testable claim has an atomic Acceptance test with an oracle; expansion left the frozen baseline untouched. |
| `ADDITIVE_EXPANSION_VALID` | Every dimension, operator pattern, failure surface, test asset and use-case journey was evaluated with a valid disposition; coverage claims are semantically aligned. |
| `PROCEDURE_QUALITY_VALID` | Every test has an executable procedure in the run locale; readiness derives from material unknowns only. |
| `EVIDENCE_AND_REFERENCE_VALID` | Evidence references point inside the selected scope; Questions and Findings link back to their tests. |
| `PIPELINE_INTEGRITY_VALID` | Stages ran in order and every recorded stage file matches the hash-chained manifest. |
| `PUBLICATION_VALID` | Public files validate against the schemas, render from canonical state only and match the publication digests. |

## Integrity

`run-manifest.json` records `SOURCE_SELECTION → SEMANTIC_EXTRACTION → TEST_DESIGN → EXPANSION → PROCEDURES → VALIDATION → RENDER → PUBLICATION`. Each record chains the previous digest and binds the digests of the stored stage payload/result. The canonical state is built only from recorded results; rendering reads only canonical state. `python scripts/pipeline.py verify --run <run>` (or `scripts/validation.py <output> --manifest <run>/run-manifest.json`) proves the chain, the canonical digest and every published file.

## Honest gap metrics

`gap_metrics` keeps six separate dimensions: `unmapped_extracted_claims`, `unaccounted_normative_units`, `uncovered_use_case_flows`, `unresolved_business_test_assets`, `unresolved_questions`, `blocked_normative_tests`. The summary reads `0 gaps` only when all six are zero.

## Metrics and warnings (never gates)

`run-metrics.json` reports counts by basis, dimension, status, suitability and readiness; priority distribution (with a flattening warning above 90%); average steps and one-step ratio; identifier coverage by kind; Findings, Questions, families, merge candidates; per-stage wall time and rejections; procedure diagnostics (`procedures_generated`, `procedures_with_evidence_refs`, `procedures_requiring_additional_evidence`, `targeted_source_lookups`, `procedure_generation_seconds`, `average_procedure_generation_seconds`, `runtime_source_reads`, `runtime_source_rereads`, `source_integrity_checks`). Warnings include priority flattening, possible multi-action steps and `PROCEDURE_BOILERPLATE` (more than half of all steps share a template).

## Historical baselines (benchmark only)

`finalize --baseline <file>` compares normative intents, Findings, challenge dispositions and families with a historical baseline and reports `PRESERVED`, `ADDED`, `REMOVED_WITH_REASON`, `UNEXPLAINED_REGRESSION`. Without a loaded baseline the suite shows `NOT_APPLIED`, never `PASS`. `scripts/benchmark.py` also reconciles previously confirmed Findings and external (e.g. manual) suites; none of this affects normal generation.
