# Selected-source accounting and independent review

Mapping every structured input the shared core receives proves input consistency. It does not prove that the selected sources were comprehensively explored. These two gates answer the second question and fail closed.

## Source accounting ledger

Every resolved selected source gets exactly one explicit inspection disposition:

```text
INSPECTED_CONTENT
METADATA_ONLY
IRRELEVANT_WITH_REASON
DUPLICATE_EQUIVALENT_SOURCE
UNSUPPORTED_BINARY
FAILED_TO_READ
```

Accounting for a source is not the same as opening it. A binary, a generated file, or a byte-equivalent restatement may legitimately stay unread, but only with a recorded reason. A resolved source with no entry blocks the run, and an entry for a path outside the resolved scope is rejected.

Each entry records the source role, content type, inspection method, whether content was read, the reason when it was not, and privacy-safe counts for evidence records, source behaviors, test-asset behaviors, opportunities, divergences, and rereads. Never copy source content into the ledger.

Use `build_source_ledger` from `scripts/source_accounting.py`. The ledger produces the `resolved_selected_sources`, `sources_inspected_content`, `sources_metadata_only`, `sources_irrelevant_with_reason`, `sources_failed`, and `sources_unaccounted` metrics.

## Honest read and concurrency telemetry

Report what the host actually observed, or mark it unavailable. A fabricated `source_reads = 0` claims the selected sources were never opened when the agent in fact inspected them before invoking the shared core.

```text
source_read_telemetry_available = false
source_reads = null
source_rereads = null
source_max_concurrency = null
agent_reasoning_seconds = null
```

The same rule governs worker count, maximum concurrency, and agent reasoning duration. Use `read_telemetry`; supply `source_read_telemetry` on the request when the host can measure it.

## Independent source-first review

`source_first_claims` must not be a copy or reformat of the primary extracted Claim list. The review declares how it was produced:

```text
SUBAGENT_INDEPENDENT     a separate reviewer reads the Functional Authority
BOUNDED_SECOND_READING   one bounded second reading with anti-anchoring instructions
```

The review must withhold `final_scenario_count`, `final_test_case_count`, and `desired_suite_size`. A behavior carrying `derived_from_claim_id` is a copy and is rejected.

## Structural inventory before semantic normalization

The review inventories structural units before summarizing them: functional requirements, acceptance criteria, nested bullets, business rules and sub-rules, use cases, main and alternative flows, preconditions and postconditions, permissions, state transitions, error and rejection rules, timing rules, messages, audit requirements, integration rules, data constraints, and recovery rules.

A high-level Requirement object does not prove its child behaviors were extracted:

```text
1 requirement heading + N acceptance bullets  ≠  1 Claim by default
```

Every structural unit either produces at least one behavior or records a `no_behavior_reason`. A unit that silently loses its children blocks the run.

Comparing the independent behaviors with the materialized Clauses yields `SOURCE_COVERAGE_GAP` before Scenario Design. Use `audit_source_review_independence`, then `audit_source_claims` from [source-coverage-audit.md](source-coverage-audit.md).

## Atomicity reasons that contradict their own signal

`SINGLE_OBSERVABLE_OUTCOME` asserts one outcome. It cannot keep a source item or a post-split claim whose prose describes several independently observable outcomes. Use `INSEPARABLE_VALUE` or `INSEPARABLE_RELATION` when the observations genuinely cannot be separated, and split otherwise.

## Checkpoints

The real generation path persists `SOURCE_ACCOUNTING_COMPLETE` and `SOURCE_REVIEW_COMPLETE` alongside the existing checkpoints, so an interrupted run resumes while the source hashes still match.
