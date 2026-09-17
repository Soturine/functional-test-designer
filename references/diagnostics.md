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

## Stages

1. `scope_resolution`
2. `source_read`
3. `evidence_normalization`
4. `coverage_point_extraction`
5. `coverage_extraction_audit`
6. `testability_and_questions`
7. `test_design_and_scenarios`
8. `early_deduplication`
9. `test_case_generation`
10. `evidence_enrichment`
11. `execution_path_synthesis`
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
- `scenario_candidates`
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

The finish helper derives these objective metrics from final JSON; do not record them again in a stage:

- `test_cases_with_one_step`
- `test_cases_with_multiple_steps`
- `average_steps_per_test_case`
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

## Finish

Address every stage, then run:

```bash
python scripts/diagnostics.py finish <artifact_root>/diagnostics/run-metrics.json --output <artifact_root>/output
```

The helper derives artifact totals, the slowest measured stage, `unattributed_seconds`, and `unattributed_percent`. More than 20% unattributed time adds a non-blocking `HIGH_UNATTRIBUTED_TIME` warning; it does not fail the run. A large interval between stages that contains useful reasoning belongs inside the relevant stage timer.

It also emits `scope_proof` with roots, resolved paths, opened/out-of-scope/skipped files, reads, rereads, and temporary-file counts. `files_opened_outside_scope` is expected to be zero; any nonzero value sets `scope_violation: true`. Record source rereads honestly and add a short note when tooling or encoding forced one.

Add at most three observed optimization candidates with repeated `--candidate` arguments. Do not commit real run metrics; only synthetic diagnostics tests belong in the repository.
