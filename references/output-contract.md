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
|   |-- organization.json      groups, memberships and order (references, never case copies)
|   |-- execution-plan.md      every group with its cases in execution order (MARKDOWN)
|   `-- operational-scenarios.md (only with OPERATIONAL)
|   |-- chaos/<chaos-id>/      (/ftd-chaos) chaos-cases.json, seed-dispositions.json,
|   |                          chaos-plan.md, chaos-plan.html (per requested format)
|   `-- azure/                 (/ftd-azure) azure-export-package.json, azure-preview.json
|-- diagnostics/               (only with DIAGNOSTICS)
`-- .ftd/
    |-- runs/<run-id>/         private: run.json, normalized-request.json, sources.json,
    |                          authority-text/, evidence/, reading/ (task-plan, results/,
    |                          source-catalog, reconciliation), stages/, run-manifest.json,
    |                          run-state.json, work-order.json, canonical-suite.json,
    |                          run-metrics.json, challenges/<chaos-id>/ (internal chaos state)
    |-- catalog-cache/         validated reader catalogs, keyed by source key + digest + role
    `-- text-cache/            extracted source text, keyed by content digest
```

## Index (`test-cases.json`)

Required: `schema_version`, `generated_at`, `sources`, `requirements`, `normative_clauses`, `findings`, `coverage_points`, `scenarios`, `test_cases`, `merge_candidates`, `quality_gates`, and either `identifier_dispositions` (v2.3) or the legacy `source_inventory`.

v2.3 additions:

- `output_locale`, `locale_source` (`EXPLICIT`, `FUNCTIONAL_AUTHORITY`, `USER_REQUEST`, `FALLBACK_AMBIGUOUS`).
- `sources[]`: one record per physical source — `path`, `role`, `authority`, `status` (`READ`, `TRANSCRIBED`, `METADATA_ONLY`, `UNSUPPORTED`, `FAILED`), `reason`, `content_digest`.
- `requirements[]`: `source_identifier`, `source_title` (exactly as the authority states it), `source_statement`, `kind`.
- `identifier_dispositions[]`: every authority identifier with `disposition` in `COVERED_BY_ATOMIC_TC`, `COVERED_BY_MULTIPLE_ATOMIC_TCS`, `QUESTION_REQUIRED`, `BLOCKED_EXTERNAL_DEPENDENCY`, `NOT_TESTABLE_WITH_REASON`, `SUPERSEDED_BY_AUTHORITY`, plus `claim_refs`, `test_refs`, `requirement_refs`, `question_refs`, `reason`.
- `findings[]`: `id`, `type`, `statement`, `requirement_refs`, `source_refs`, `related_test_cases`, `coverage_disposition` and, since 2.4 (optional, additive), `question_refs` — the Questions that must resolve a `QUESTION` Finding.
- `expansion_summary[]`: per dimension `candidates_considered`, `materialized`, `already_covered`, `question_required`, `not_applicable`.
- `gap_metrics`: the six honest gap dimensions.
- `baseline_comparison`: `{"status": "NOT_APPLIED"}` unless a benchmark baseline was applied.
- `quality_gates`: the 8 gates of [validation.md](validation.md). Suites published by v2.2.x keep their 28-gate list and still validate.

`scenarios[]` are Scenario Families (`type: SCENARIO_FAMILY`) with `test_case_refs` equal to their members. `merge_candidates[]` are advisory and never remove a Test Case.

## Test Case (`test-cases/TC-XXX.json`)

Core fields as in 2.2: `id`, `title`, `status`, `priority`, `type`, `objective`, `requirement_refs`, `scenario_refs` (one family), `coverage_point_refs`, `source_refs`, `preconditions`, `test_data`, `steps[{step, action, expected_result, needs_clarification}]`, `postconditions`, `cleanup`, `tags`, `notes`, `test_basis` (`ACCEPTANCE`, `DERIVED`, `CHARACTERIZATION`, `EXPLORATORY`, `E2E`), `primary_type`, `execution_status`, `question_refs`, `finding_refs`, `composes`, `automation_candidate`, `automation_layer`, `automation_tool_hint`, `deterministic`, `priority_reason`, `claim_exercise_map` (Acceptance), `atomicity_exception` (indivisible contracts), `e2e_stage_map` (E2E).

v2.3 additions: `automation_suitability` (`HIGH`, `MEDIUM`, `LOW`, `MANUAL_ONLY`), `automation_readiness` (`READY`, `NEEDS_FIXTURE`, `NEEDS_SELECTOR`, `NEEDS_ENVIRONMENT`, `NEEDS_POLICY`, `BLOCKED_EXTERNAL_DEPENDENCY`, `NOT_APPLICABLE`), `readiness_blockers`, `failure_domain`, `source_identifiers`, `expansion_dimension`, `expansion_checklist_item`, `single_step_reason`. `automation_blocker` is no longer emitted.

v2.4 additions (optional, additive):

- `state_contract`: `SELF_CLEANING` when `cleanup` restores state, otherwise `REQUIRES_FIXTURE_RESET` — the executor (or harness) resets the fixtures described in `test_data` before the next case.
- `execution_variants[{kind, description}]`: other ways to run the same case (`PHYSICAL_DEVICE`, `SIMULATED_DEVICE`, `MANUAL_FIELD`). A variant adds the case to an execution view; it never creates a second Test Case.
- `request_contract{method, endpoint, parameters, body, fixture_pool, varies, measurements}`: the request a load or concurrency experiment repeats, described without tool syntax and without thresholds the design does not state.

There are never `subtests`: independent variants are separate Test Cases; dependent actions are steps.

## Organization (`organization.json`)

How the same cases are grouped for execution. Nothing here copies a case; `diagnostics.cloned_cases` is always 0.

- `groups[]`: `id`, `kind` (`FUNCTIONAL`, `TRANSVERSAL`, `EXECUTION_VIEW`), `label` (run locale), `identifier`, `flow_reference`, `order_source` and ordered `members[{case, origin, via, order, chaos_run_id?}]`.
  - A `FUNCTIONAL` group holds the cases of one functional requirement. Its order follows explicit guidance, then the main flow of the use case the requirement is exercised with (`USE_CASE_MAIN_FLOW`); an alternative-flow case sits right after the step it branches from; otherwise the canonical order (`CANONICAL_ORDER`) is kept.
  - `TRANSVERSAL` holds rule-only cases. Execution views (`E2E`, `LOAD_CONCURRENCY`, `PHYSICAL_DEVICE`, `CHAOS_RESILIENCE`, `MANUAL_FIELD`) are derived from each case's semantic category (primary type, automation layer, execution variants, chaos execution tags), never from where it came from. `MANUAL_FIELD` is omitted when it would repeat the physical view.
  - `origin` is `CANONICAL` or `POST_SUITE`. A finalized chaos case joins its related case's group right after it, and its execution views; it keeps its `CH-*` identity.
- `memberships`: case key (`TC-001` or `<chaos-id>:CH-001`) → `[{group, order}]`.
- `post_suite_cases[]`: references (`key`, `id`, `chaos_run_id`, `parent_run_id`, `title`) only.

The HTML report shows the same organization as views: by requirement (default, in placement order), families, each execution view and all. A card counts the unique cases of its group, and chaos cases open in the same modal with their own body.

## Questions (`questions.json`)

`id`, `question`, `reason`, `blocking`, `impact`, `requirement_refs`, `source_refs`, `related_test_cases`. A blocking Question keeps its Test Cases out of `READY`. A step with `needs_clarification` requires a related Question.

## Validation

`python scripts/validation.py <output-dir> [--manifest <run>/run-manifest.json]` checks the schemas and every cross-file invariant (ids, references both ways, CP destinations, family membership, E2E composition, gate completeness, generic titles such as `header`).
