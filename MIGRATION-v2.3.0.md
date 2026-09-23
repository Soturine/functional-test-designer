# Migrating from v2.2.2 to v2.3.0

## What stays the same

- Natural-language requests and the `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, `ftd-mcp` aliases.
- Selecting several files and directories, explicit source order, output formats, diagnostics, prior clarifications and an exact artifact destination.
- Public Test Case schema `2.2`. New fields are optional. Schema `1.2` suites still validate and render.
- `output/` layout: `test-cases.json`, `questions.json`, `report.html`, `test-cases/TC-XXX.json`, `test-cases-md/TC-XXX.md`.
- Suites that record the 28 v2.2.x gate names are still accepted by the validator.

## What changed

### Scripts

| v2.2.2 | v2.3.0 |
| --- | --- |
| `validate_output.py` | `validation.py` (same CLI, including `--manifest`) |
| `render_markdown.py`, `render_report.py`, `render_operational_scenarios.py` | `render.py` |
| `resolve_scope.py`, `resolve_artifacts.py`, `source_inventory.py`, `source_accounting.py`, `test_asset_inventory.py` | `sources.py` |
| `generation_orchestrator.py`, `pipeline_integrity.py`, `canonical_state.py`, `run_state.py`, `diagnostics.py` | `pipeline.py` |
| `workflow_entrypoints.py`, `clarification.py`, `suite_check.py` | `workflow.py` |
| `azure_devops_adapter.py` | `integrations/azure_devops.py` |
| `benchmark_reconciliation.py`, `run_independence_benchmark.py`, `run_operational_benchmarks.py`, `run_synthetic_e2e.py` | `benchmark.py` |
| 19 other semantic and gate modules (`additive_expansion`, `risk_expansion`, `quality_gates`, `scenario_independence`, `procedural_*`, …) | folded into `design.py`, `expansion.py`, `procedures.py`, `validation.py` or removed |

### Generation contract

- Generation starts from **selected sources with roles**. The model submits three stages as JSON (`pipeline.py submit --stage design|expansion|procedures`), and each is validated before it is recorded in the manifest. See `references/stage-contracts.md`.
- Requests that carry pre-authored semantics are rejected: `source_items`, `source_units`, `opportunities`, `risk_conditions`, `use_case_flows`, `test_asset_inventory`, `scenario_profiles`, `evidence_packs`, `selected_evidence`.
- Gates are 8 and always runtime-owned. Runs keep the ordered manifest `SOURCE_SELECTION → SEMANTIC_EXTRACTION → TEST_DESIGN → EXPANSION → PROCEDURES → VALIDATION → RENDER → PUBLICATION`.

### New optional fields

- Test Case: `automation_suitability`, `automation_readiness`, `readiness_blockers`, `expansion_dimension`, `expansion_checklist_item`, `failure_domain`, `source_identifiers`, `single_step_reason`.
- Index: `output_locale`, `locale_source`, `identifier_dispositions` (which replaces `source_inventory` for v2.3 runs), `expansion_summary`, `gap_metrics`, `baseline_comparison`. Requirements carry `source_identifier`, `source_title`, `source_statement` and `kind`, and sources carry `status`, `reason` and `content_digest`.

### Behavior you may notice

- Test titles describe behavior. The official identifier title lives on the requirement, and the identifiers show as chips on the HTML card.
- Text follows the run's `output_locale`, which defaults to the authority's language.
- More Test Cases: the baseline is atomic, and the second pass materializes operator-error, chaos/recovery, characterization and E2E tests. Count is never a target.
- `READY` no longer requires literal data. `automation_readiness` is reported separately.
- `baseline_comparison` shows `NOT_APPLIED` unless a benchmark baseline was loaded (`finalize --baseline`).
