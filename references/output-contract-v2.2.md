# Output Contract 2.2

Keep the existing public directory layout and JSON-as-truth model. Use exact `schema_version` value `2.2`; Markdown and offline HTML are deterministic projections.

The index retains sources, requirements, normative clauses, Findings, Coverage Points, scenarios, and Test Case entries. It adds:

- `source_inventory`: authority, family, inclusion/exclusion, and reason for every selected source;
- `merge_candidates`: non-destructive manual-compaction suggestions referring to existing atomic TCs;
- `quality_gates`: the eight independent final design gates.

A Scenario is a `SCENARIO_FAMILY`. Its `test_case_refs` may contain several canonical Test Cases; each TC still references exactly one family. A Coverage Point may target more than one TC when Acceptance, Characterization, Derived, or other independently diagnosable designs coexist.

Every TC carries `test_basis`, `primary_type`, `secondary_tags`, `execution_status`, reciprocal `question_refs` and `finding_refs`, optional `composes`, and automation-readiness hints. An E2E TC must compose existing atomic TCs and cannot replace them. Non-E2E TCs cannot use `composes` to hide a journey.

Questions classify their impact. Findings may list affected TCs and coverage disposition. Validators enforce reciprocal TC links, Scenario Family membership, CP targeting, E2E composition, merge-candidate references, source provenance, and all-PASS final quality gates.

Schema 1.2 remains supported as an explicit compatibility contract; never reinterpret a 1.2 artifact as 2.2 without migration.
