# v2.3.0 Simplification Report

## Did this release make the framework simpler?

Yes. The runtime is about half the code, a quarter of the modules and under a third of the gates. The entry point went from a large pre-authored semantic request to "these sources, with these roles". The QA reasoning moved back to the model, and the runtime keeps only the invariants whose failure makes a suite invalid. Generated quality went up on the MAG benchmark rather than down (see below).

| | v2.2.2 (`109d865`) | v2.3.0 |
| --- | ---: | ---: |
| Script modules (excluding `__init__`) | 41 | 11 |
| Script lines | 10,113 | 5,240 |
| Quality gates | 28 | 8 |
| Reference documents | 22 files / 972 lines | 6 files / ~300 lines |
| `SKILL.md` lines | 103 | 85 |
| Test files / test functions | 43 / 408 | 11 / 137 |
| Semantic request fields the user/agent had to pre-author | 9+ | 0 (sources + roles) |
| Model stages | implicit, spread over many helpers | 3 explicit JSON stages |

The test count dropped because most old tests exercised removed modules. The new tests target invariants: the 24 regressions required by the release plus the addenda, all run against six multi-domain packs.

## What was removed

- **Modules:** `additive_expansion`, `benchmark_reconciliation`, `canonical_state`, `clarification`, `cross_rf_audit`, `cross_source_contradictions`, `diagnostics`, `evidence_map`, `execution_quality`, `generation_orchestrator`, `normative_applicability`, `parallel_evidence`, `pipeline_integrity`, `procedural_execution`, `procedural_pipeline`, `procedural_readiness`, `quality_gates`, `reference_integrity`, `render_markdown`, `render_operational_scenarios`, `render_report`, `requirement_groups`, `resolve_artifacts`, `resolve_scope`, `risk_coverage`, `risk_expansion`, `run_independence_benchmark`, `run_operational_benchmarks`, `run_state`, `run_synthetic_e2e`, `scenario_independence`, `scenario_opportunities`, `semantic_regression`, `source_accounting`, `source_coverage_audit`, `source_inventory`, `suite_check`, `test_asset_inventory`, `workflow_entrypoints`. `validate_output` became `validation` and `azure_devops_adapter` became `integrations/azure_devops`.
- **Request fields** (now rejected): `source_items`, `source_units`, `opportunities`, `risk_conditions`, `use_case_flows`, `test_asset_inventory`, `scenario_profiles`, `evidence_packs`, `selected_evidence`. The model derives these inside the stages instead of receiving them pre-chewed.
- **Gates:** 28 overlapping gates became 8, each with a stated reason (`references/validation.md`). What used to be a gate but only measured taste (priority spread, step templates, one-step ratio) is now a metric or a warning.
- **Old benchmark fixtures** and a corrective-expansion prompt document that described a workflow that no longer exists.

## Compatibility kept on purpose

- Natural-language requests and the `ftd-gen/clarify/check/render/mcp` aliases, multiple files and directories, source order, formats, diagnostics, prior clarifications and exact destination (addendum 2 tests).
- Public schema 2.2, with new fields optional. Schema 1.2 suites validate and render (`examples/expected-output`).
- `LEGACY_GATE_NAMES`: the validator accepts suites recorded with the 28 v2.2.x gate names.
- `index.source_inventory` is accepted as an alternative to `identifier_dispositions`.

## Is the semantic core still LLM-driven?

Yes. The model writes the domain model, requirements, atomic claims, Acceptance tests, dispositions, Questions, Findings, the whole second pass (17 dimensions, operator patterns, failure surfaces, test-asset intents, characterization, E2E journeys) and every procedure. The runtime never generates a scenario, an oracle or a step.

## Which responsibilities remain deterministic?

Scope resolution and source roles, reading and digesting sources once, authority identifier and official-title extraction, locale inference, static discovery of test assets (AST for Python, `it`/`test` for JS), id assignment, stage validation, the frozen-baseline comparison, coverage and readiness derivation, gap metrics, canonical assembly, rendering, the hash-chained manifest and publication proof.

## Which heuristics were removed or avoided?

- **Removed:** keyword-based risk expansion, rule tables that turned requirement words into scenarios, template procedure synthesis, lexical "opportunity" mining and automatic scenario merging.
- **Avoided:** domain keyword lists, per-domain rule engines, and any count target ("generate N tests").
- **Kept as cheap checks that only count or compare, never interpret:**
  - compound-oracle signals;
  - structural item counts for over-compression;
  - containment/Jaccard alignment for coverage claims;
  - locale detection by function words;
  - abstract-step patterns.

  Each one asks the model for a reason or a fix. It never rewrites content.
- **Known noise:**
  - The compound-verb signal can flag a trigger verb. The model answers with `indivisible_contract`.
  - Authority excerpts can absorb a use case's postconditions, which inflates structural counts. The model answers with `structure_reviews`.

  Both answers are recorded and auditable.

## How is hardcoding prevented?

- Production code carries universal vocabulary only: roles, dimensions, patterns, surfaces and unknown kinds.
- A regression test scans `scripts/` for benchmark-project vocabulary and fails on any hit. It allows only the bare word `box`, which the renderer uses for SVG geometry.
- A scan run on this release finds none: the only matches for "box" are SVG layout geometry and CSS `box-sizing`.
- Identifier conventions are a generic pattern that `--id-pattern` can override.
- Every rule is exercised across six unrelated domains.

## Which multi-domain fixtures prove generality?

`benchmarks/domains/`, run by `python scripts/benchmark.py packs` (all PASS):

| Pack | Locale | Shape | TCs |
| --- | --- | --- | ---: |
| A `saas-accounts` | en | invitations, roles, cross-account isolation | 12 |
| B `logistics-storage` | pt-BR | storage positions, physical/digital mismatch | 11 |
| C `erp-sales-orders` | es | orders, credit, partial commit, shared policy | 9 |
| D `iot-line-monitoring` | en | no identifiers at all, device/network surfaces | 9 |
| E `aerospace-inspection` | pt-BR | inspection sign-off, wrong component | 10 |
| F `api-refunds` | en | API contract, existing tests as challenge set | 9 |

## Did any benchmark-specific concept enter production code?

No. Production code carries universal vocabulary only. Regression coverage uses synthetic benchmark markers and six unrelated synthetic fixtures to catch accidental coupling between runtime behavior and benchmark data.

## Release verification

- Six synthetic multi-domain packs pass through the official pipeline.
- The fixtures cover SaaS, logistics, ERP, IoT, aerospace maintenance and API behavior in English, Portuguese and Spanish.
- Production modules contain no fixture names or synthetic benchmark markers.
- Public schema 2.2 remains the generated format and schema 1.2 remains supported for validation/rendering.
- The staged manifest, canonical digest and publication digests remain runtime-owned.

## Remaining gaps

- Synthetic fixtures prove framework invariants and cross-domain behavior; project-specific acceptance still requires the selected project's own sources.
- Procedure wall time measures elapsed stage time and does not expose token-level model timing.
- A validated run cannot be finalized twice. Re-rendering goes through `pipeline.py render`, and changed semantic payloads require a new run.
