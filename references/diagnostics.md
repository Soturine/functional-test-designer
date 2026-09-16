# Execution Diagnostics

Use this procedure only when the user explicitly requests diagnostics. It measures the skill workflow and lives outside Test Case output.

## Start and Record

Start before resolving scope:

```bash
python scripts/diagnostics.py start diagnostics/run-metrics.json
```

Time actual work with `begin` and `end`, or use `skip` when a stage is genuinely unnecessary:

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
10. `json_write`
11. `validation`
12. `validation_fixes`
13. `markdown_render`
14. `html_render`
15. `final_summary`

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
- `scenario_candidates`
- `scenarios_after_dedup`
- `test_cases_generated`
- `steps_generated`
- `validator_runs`
- `validation_fix_rounds`
- `markdown_files_generated`

`selected_scope_roots` and `resolved_scope_paths` may contain normalized relative paths. Other metrics should normally be counts. Never record source text, client names, payloads, credentials, production data, or confidential identifiers.

## Finish

Address every stage, then run:

```bash
python scripts/diagnostics.py finish diagnostics/run-metrics.json --output output
```

The helper derives artifact totals, the slowest measured stage, `unattributed_seconds`, and `unattributed_percent`. It also emits `scope_proof` with roots, resolved paths, opened/out-of-scope/skipped files, reads, rereads, and temporary-file counts. `files_opened_outside_scope` is expected to be zero; any nonzero value sets `scope_violation: true`.

Add at most three observed optimization candidates with repeated `--candidate` arguments. Do not commit real run metrics; only synthetic diagnostics tests belong in the repository.
