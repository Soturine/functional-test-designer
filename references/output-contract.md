# Output contract (public schema 2.2)

v2.3 publishes schema `2.2` with additive optional fields. Schema `1.2` suites remain readable, validatable and renderable; new generation always emits `2.2`. JSON is the truth; Markdown and HTML are projections rendered from canonical state.

```text
<artifact-root>/
|-- output/
|   |-- test-cases.json        index
|   |-- questions.json
|   |-- report.html            offline, no external runtime
|   |-- test-cases/TC-XXX.json
|   |-- test-cases-md/TC-XXX.md (Mermaid flow last, identical to the HTML flow)
|   `-- operational-scenarios.md (only with OPERATIONAL)
|-- diagnostics/               (only with DIAGNOSTICS)
`-- .ftd/runs/<run-id>/        private: run.json, sources.json, authority-text/, stages/,
                               run-manifest.json, run-state.json, work-order.json,
                               canonical-suite.json, run-metrics.json
```

## Index (`test-cases.json`)

Required: `schema_version`, `generated_at`, `sources`, `requirements`, `normative_clauses`, `findings`, `coverage_points`, `scenarios`, `test_cases`, `merge_candidates`, `quality_gates`, and either `identifier_dispositions` (v2.3) or the legacy `source_inventory`.

v2.3 additions:

- `output_locale`, `locale_source` (`EXPLICIT`, `FUNCTIONAL_AUTHORITY`, `USER_REQUEST`, `FALLBACK_AMBIGUOUS`).
- `sources[]`: one record per physical source — `path`, `role`, `authority`, `status` (`READ`, `TRANSCRIBED`, `METADATA_ONLY`, `UNSUPPORTED`, `FAILED`), `reason`, `content_digest`.
- `requirements[]`: `source_identifier`, `source_title` (exactly as the authority states it), `source_statement`, `kind`.
- `identifier_dispositions[]`: every authority identifier with `disposition` in `COVERED_BY_ATOMIC_TC`, `COVERED_BY_MULTIPLE_ATOMIC_TCS`, `QUESTION_REQUIRED`, `BLOCKED_EXTERNAL_DEPENDENCY`, `NOT_TESTABLE_WITH_REASON`, `SUPERSEDED_BY_AUTHORITY`, plus `claim_refs`, `test_refs`, `requirement_refs`, `question_refs`, `reason`.
- `expansion_summary[]`: per dimension `candidates_considered`, `materialized`, `already_covered`, `question_required`, `not_applicable`.
- `gap_metrics`: the six honest gap dimensions.
- `baseline_comparison`: `{"status": "NOT_APPLIED"}` unless a benchmark baseline was applied.
- `quality_gates`: the 8 gates of [validation.md](validation.md). Suites published by v2.2.x keep their 28-gate list and still validate.

`scenarios[]` are Scenario Families (`type: SCENARIO_FAMILY`) with `test_case_refs` equal to their members. `merge_candidates[]` are advisory and never remove a Test Case.

## Test Case (`test-cases/TC-XXX.json`)

Core fields as in 2.2: `id`, `title`, `status`, `priority`, `type`, `objective`, `requirement_refs`, `scenario_refs` (one family), `coverage_point_refs`, `source_refs`, `preconditions`, `test_data`, `steps[{step, action, expected_result, needs_clarification}]`, `postconditions`, `cleanup`, `tags`, `notes`, `test_basis` (`ACCEPTANCE`, `DERIVED`, `CHARACTERIZATION`, `EXPLORATORY`, `E2E`), `primary_type`, `execution_status`, `question_refs`, `finding_refs`, `composes`, `automation_candidate`, `automation_layer`, `automation_tool_hint`, `deterministic`, `priority_reason`, `claim_exercise_map` (Acceptance), `atomicity_exception` (indivisible contracts), `e2e_stage_map` (E2E).

v2.3 additions: `automation_suitability` (`HIGH`, `MEDIUM`, `LOW`, `MANUAL_ONLY`), `automation_readiness` (`READY`, `NEEDS_FIXTURE`, `NEEDS_SELECTOR`, `NEEDS_ENVIRONMENT`, `NEEDS_POLICY`, `BLOCKED_EXTERNAL_DEPENDENCY`, `NOT_APPLICABLE`), `readiness_blockers`, `failure_domain`, `source_identifiers`, `expansion_dimension`, `expansion_checklist_item`, `single_step_reason`. `automation_blocker` is no longer emitted.

There are never `subtests`: independent variants are separate Test Cases; dependent actions are steps.

## Questions (`questions.json`)

`id`, `question`, `reason`, `blocking`, `impact`, `requirement_refs`, `source_refs`, `related_test_cases`. A blocking Question keeps its Test Cases out of `READY`. A step with `needs_clarification` requires a related Question.

## Validation

`python scripts/validation.py <output-dir> [--manifest <run>/run-manifest.json]` checks the schemas and every cross-file invariant (ids, references both ways, CP destinations, family membership, E2E composition, gate completeness, generic titles such as `header`).
