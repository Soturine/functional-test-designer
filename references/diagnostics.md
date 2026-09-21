# Execution Diagnostics

Use this procedure only when the user explicitly requests diagnostics. It measures the skill workflow and lives outside Test Case output.

## Start and Record

Start before resolving scope:

```bash
python scripts/diagnostics.py start <artifact_root>/diagnostics/run-metrics.json
```

Time actual work with `begin` and `end`, or use `skip` when a stage is genuinely unnecessary. `begin` must happen before analysis or reasoning for that stage; materialize the result while the timer is active, then call `end`. Do not reason first and time only persistence:

```bash
python scripts/diagnostics.py begin diagnostics/run-metrics.json scope_resolution
python scripts/diagnostics.py end diagnostics/run-metrics.json scope_resolution \
  --done "Resolved explicitly selected paths." \
  --metric 'selected_scope_roots=["docs/requirements.md"]' \
  --metric 'resolved_scope_paths=["docs/requirements.md"]'
```

Use 1-5 short `--done` entries. Record metrics only when observable; never estimate.

An unobservable metric is reported as unavailable, not as zero. When the host cannot measure source reads, rereads, worker count, maximum concurrency, or agent reasoning duration, set `source_read_telemetry_available` to `false` and leave those metrics `null`. A fabricated zero claims the selected sources were never opened.

A diagnostics-enabled run describes the whole workflow. Record run wall clock, attributed stage wall clock, and the unattributed remainder, so a fast final materialization is never presented as the duration of the entire run.

The enforced shared path also reports selected-source accounting (`resolved_selected_sources`, `sources_inspected_content`, `sources_metadata_only`, `sources_irrelevant_with_reason`, `sources_failed`, `sources_unaccounted`), independent review (`primary_atomic_claims`, `independent_review_source_behaviors`, `structural_units_inventoried`, `source_behavior_gaps`), Test Asset inventory (`test_files_selected`, `test_functions_inventory_count`, `test_asset_business_behaviors`, `test_asset_technical_only_behaviors`, `test_asset_missing_dispositions`), opportunity discovery (`adversarial_opportunities`, `negative_opportunities`, `operator_error_opportunities`, `resilience_opportunities`, `recovery_opportunities`, `concurrency_opportunities`, `e2e_opportunities`, `characterization_risk_candidates`), step granularity (`one_step_cases`, `legitimate_one_step_cases`, `path_compression_warnings`), and readiness (`cases_missing_setup_acquisition`, `cases_missing_procedural_provenance`, `human_execution_ready`, `human_execution_not_ready`, `automation_execution_ready`, `automation_execution_not_ready`).

Never copy selected source content into diagnostics.

## Stages

1. `scope_resolution`
2. `source_read`
3. `evidence_normalization`
4. `coverage_point_extraction`
5. `coverage_extraction_audit`
6. `testability_and_questions`
7. `test_design_and_scenarios`
8. `early_deduplication`
9. `evidence_enrichment`
10. `execution_path_synthesis`
11. `test_case_generation`
12. `source_coverage_audit`
13. `source_coverage_recovery`
14. `source_coverage_verification`
15. `cross_rf_audit`
16. `json_write`
17. `validation`
18. `validation_fixes`
19. `markdown_render`
20. `html_render`
21. `final_summary`

Test data is generated with each TC, not timed as a separate phase.

## Metrics

Record these when naturally observable:

- `selected_scope_roots`
- `resolved_scope_paths`
- `files_opened`
- `files_opened_outside_scope`
- `files_skipped_out_of_scope`
- `source_reads`
- `source_rereads`
- `temporary_files_created`
- `normative_clauses_extracted`
- `normative_clauses_mapped`
- `unmapped_normative_clauses`
- `coverage_points`
- `testable_coverage_points`
- `scenario_candidates`
- `scenario_candidates_before_merge`
- `scenario_merge_candidates`
- `scenario_merges_applied`
- `scenarios_after_merge`
- `multi_cp_scenarios`
- `possible_scenario_overcompression_warnings`
- `scenarios_after_dedup`
- `independent_scenarios_preserved`
- `semantic_duplicates_removed`
- `test_cases_generated`
- `steps_generated`
- `individual_json_files_written`
- `json_bytes_written`
- `validator_runs`
- `validation_fix_rounds`
- `markdown_files_generated`
- `artifact_root`
- `output_path`
- `diagnostics_path`
- `artifact_root_source`
- `detailed_execution_evidence_available`
- `source_claims_identified`
- `source_claims_represented`
- `source_coverage_gaps`
- `recovered_source_gaps`
- `source_items`
- `atomic_source_claims_identified`
- `atomic_claims_deduplicated`
- `compound_source_items_split`
- `possible_compound_claim_warnings`
- `compound_claims_reviewed`
- `compound_claims_split`
- `compound_claims_kept_atomic`
- `referenced_normative_rules`
- `referenced_rules_resolved_in_scope`
- `referenced_rules_unresolved`
- `applicable_rule_claims`
- `applicable_rule_claims_represented`
- `evidence_map_hits`
- `evidence_map_misses`
- `source_files_opened_once`
- `source_files_reopened`
- `tc_generation_reuse_hits`
- `varied_execution_paths_available`
- `source_analysis_workers_started`
- `source_analysis_workers_completed`
- `source_analysis_max_concurrency`
- `source_analysis_groups`
- `source_analysis_group_barriers`
- `source_analysis_order_constraints`
- `source_analysis_parallel_groups`
- `source_analysis_serialized_groups`
- `evidence_records_generated`
- `evidence_records_by_role`
- `stage_wall_clock_seconds`
- `aggregate_worker_seconds`
- `procedural_tasks_enqueued`
- `procedural_tasks_completed`
- `procedural_max_concurrency`
- `procedure_ready`
- `procedure_gaps`
- `procedural_ambiguities`
- `procedural_divergences`
- `independent_branches_detected`
- `unsupported_steps`
- `new_tc_candidates`
- `new_tcs_appended`
- `pending_additive_follow_up`
- `procedural_wall_clock_seconds`
- `procedural_aggregate_worker_seconds`

The finish helper derives these objective metrics from final JSON; do not record them again in a stage:

- `test_cases_with_one_step`
- `test_cases_with_multiple_steps`
- `average_steps_per_test_case`
- `step_count_histogram`
- `multi_action_step_warnings`
- `possible_step_underspecification_warnings`
- `hidden_subtest_warnings`
- `possible_step_template_bias`
- `test_cases_with_execution_enrichment`
- `test_cases_with_multiple_source_roles`
- `test_cases_with_concrete_test_data`
- `abstract_action_warnings`
- `execution_path_questions`
- `functional_authority_contributions`
- `technical_context_contributions`
- `implementation_evidence_contributions`
- `test_asset_contributions`
- `rf_groups`
- `rf_groups_with_zero_gaps`
- `rf_groups_with_gaps`
- `cross_rf_tcs`
- `same_multi_rf_coverage`
- `duplicate_candidates`
- `similar_but_distinct`
- `automatic_merges` (always zero)
- `automatic_removals` (always zero)

`selected_scope_roots` and `resolved_scope_paths` are arrays of normalized paths. Destination metrics are strings; other metrics should normally be counts. Never record source text, client names, payloads, credentials, production data, or confidential identifiers.

Aggregation is explicit per metric: event counters such as reads and real validator executions use `sum`; generated artifact/state counts use the last authoritative stage; roots and paths use ordered set/array aggregation; destination fields use the last resolved value. Do not repeat `test_cases_generated` in `json_write`; record `individual_json_files_written` there. A summary that reads a validation result does not increment `validator_runs`. The helper rejects unknown metrics until an aggregation strategy is defined and verifies that scope values in `totals` and `scope_proof` match by value and type.

The helper derives step distribution, selected-role contributions, multi-role provenance, execution enrichment, concrete-data signals, abstract-action signals, and execution-path Questions from final JSON. Role contribution counts only TCs that actually cite a source with that role. When the evidence map objectively contains detailed execution paths, record `detailed_execution_evidence_available=true`; if at least 80% of a suite with five or more cases still has one step, the helper adds the non-blocking `POSSIBLE_EXECUTION_UNDER_SPECIFICATION` warning. This is not a quality score and does not force extra steps.

Compound-claim and multi-action heuristics are advisory and never rewrite output. `possible_step_underspecification_warnings` is the explicit metric name for the existing `POSSIBLE_MULTI_ACTION_STEP` audit; it does not create a duplicate warning type. Record `varied_execution_paths_available=true` only when selected evidence actually contains paths of different supported complexity; a uniform distribution then adds `POSSIBLE_STEP_TEMPLATE_BIAS`. Evidence-map counters measure real cache events, not estimated savings.

Scenario-independence metrics describe the candidate-first review; they are not scores or count targets. `scenario_merge_candidates` and `scenario_merges_applied` count only decisions with an objective internal reason such as `SHARED_EXECUTION_OBSERVATIONS`, `INSEPARABLE_SAME_EVENT`, `SHARED_PASS_FAIL_BOUNDARY`, or `TRUE_SEMANTIC_DUPLICATE`. `multi_cp_scenarios` is derived from final cases. A nonzero `possible_scenario_overcompression_warnings` adds the advisory `POSSIBLE_SCENARIO_OVERCOMPRESSION` warning and never rewrites output automatically.

The finish gate rejects fewer candidates than testable Coverage Points and requires `scenario_candidates_before_merge - scenario_merges_applied = scenarios_after_merge`. Each applied merge counts one actual candidate reduction, so N-to-1 merges contribute N-1. This is structural accounting, not a target ratio.

## Finish

Address every stage, then run:

```bash
python scripts/diagnostics.py finish <artifact_root>/diagnostics/run-metrics.json --output <artifact_root>/output
```

The helper derives artifact totals, the slowest measured stage, `unattributed_seconds`, and `unattributed_percent`. More than 20% unattributed time adds a non-blocking `HIGH_UNATTRIBUTED_TIME` warning; it does not fail the run. A large interval between stages that contains useful reasoning belongs inside the relevant stage timer.

It also emits `scope_proof` with roots, resolved paths, opened/out-of-scope/skipped files, reads, rereads, and temporary-file counts. `files_opened_outside_scope` is expected to be zero; any nonzero value sets `scope_violation: true`. Record source rereads honestly and add a short note when tooling or encoding forced one.

Add at most three observed optimization candidates with repeated `--candidate` arguments. Do not commit real run metrics; only synthetic diagnostics tests belong in the repository.
