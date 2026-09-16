# Diagnostic Mode

Use this procedure only when the user requests `Diagnostic: true`. Diagnostics measure the skill workflow, not the product under test, and live outside the Test Case output.

## Start

Before reading the source:

```bash
python scripts/diagnostics.py start diagnostics/run-metrics.json
```

For each macro stage, start and finish real wall-clock timing around actual work:

```bash
python scripts/diagnostics.py begin diagnostics/run-metrics.json source_read
python scripts/diagnostics.py end diagnostics/run-metrics.json source_read \
  --done "Read one requirements document." \
  --metric source_files=1
```

Use 1-5 short `--done` entries. Add metrics only when naturally available; values accept JSON scalars or strings. Use `--note` for a concise non-sensitive qualification.

If a stage is genuinely unnecessary or grouped into another stage, record it explicitly:

```bash
python scripts/diagnostics.py skip diagnostics/run-metrics.json validation_fixes \
  --done "No validation fixes were required."
```

## Macro Stages

Record these stages without adding artificial work:

1. `source_read`
2. `requirements_normalization`
3. `coverage_point_extraction`
4. `testability_and_questions`
5. `test_design_and_scenarios`
6. `test_data_design`
7. `test_case_generation`
8. `deduplication`
9. `json_write`
10. `validation`
11. `validation_fixes`
12. `html_render`
13. `final_summary`

## Finish

After validation and rendering, address every stage with `end` or `skip`, then finish:

```bash
python scripts/diagnostics.py finish diagnostics/run-metrics.json --output output
```

The helper derives output totals and the slowest measured stage from real timing. Add at most three optimization candidates with repeated `--candidate` options, and only when supported by the observed run. It never estimates missing timing. If a host cannot provide trustworthy wall-clock timing, leave `elapsed_seconds` as `null`, set `timing_available: false`, and explain the limitation in `notes`.

## Privacy and Git

Record counts, durations, short descriptions of work, and structural outcomes. Never copy requirement text, client names, payloads, credentials, production data, or source documents into diagnostics. Do not commit a real `diagnostics/run-metrics.json`; only synthetic tests belong in the repository.
