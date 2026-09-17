# Output Contract 1.2

Write UTF-8 JSON with two-space indentation. Paths are relative to the output directory and use `/` separators. Use the exact `schema_version` value `1.2`.

## Files and Order

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
|-- test-cases/
|   `-- TC-XXX.json
`-- test-cases-md/
    `-- TC-XXX.md
```

Write JSON directly, validate it, render Markdown, then render HTML. Markdown and HTML are derived presentation and never repair or modify JSON. Do not put source copies, diagnostics, temporary files, or confidential data in `output/`.

## Index

`test-cases.json` contains selected sources and their roles, normalized requirements, atomic normative clauses, findings, Coverage Points, deduplicated scenarios, and the TC manifest. Clause materialization is required.

```json
{
  "schema_version": "1.2",
  "generated_at": "2026-09-16T12:00:00Z",
  "sources": [
    {"path": "docs/requirements.md", "role": "FUNCTIONAL_AUTHORITY"},
    {"path": "src/order_service.py", "role": "IMPLEMENTATION_EVIDENCE"}
  ],
  "requirements": [
    {
      "id": "REQ-001",
      "statement": "Submitting a draft order changes it to SUBMITTED.",
      "status": "TESTABLE",
      "source_refs": [{"source": "docs/requirements.md", "reference": "Submit order"}]
    }
  ],
  "normative_clauses": [
    {
      "id": "CLAUSE-001",
      "requirement_ref": "REQ-001",
      "normalized_claim": "Submitting a draft order changes it to SUBMITTED.",
      "authority": "FUNCTIONAL_AUTHORITY",
      "source_refs": [{"source": "docs/requirements.md", "reference": "Submit order"}],
      "destination_type": "COVERAGE_POINT",
      "destination_id": "CP-001"
    }
  ],
  "findings": [
    {
      "id": "FND-001",
      "type": "IMPLEMENTATION_DIVERGENCE",
      "statement": "Selected code sets PROCESSING instead of the required SUBMITTED state.",
      "requirement_refs": ["REQ-001"],
      "source_refs": [
        {"source": "docs/requirements.md", "reference": "Submit order"},
        {"source": "src/order_service.py", "reference": "submit_order"}
      ]
    }
  ],
  "coverage_points": [],
  "scenarios": [],
  "test_cases": []
}
```

Source roles are `FUNCTIONAL_AUTHORITY`, `IMPLEMENTATION_EVIDENCE`, `TEST_ASSET`, `TECHNICAL_CONTEXT`, and `OTHER_SELECTED`. Finding types are `IMPLEMENTATION_DIVERGENCE`, `SOURCE_CONFLICT`, `COVERAGE_GAP`, and `INFORMATION`.

Functional authority owns normative expected results. Other selected sources can add evidence and execution context. They cannot silently change the oracle.

TC `source_refs` list every selected source that materially contributed to its oracle, preconditions, test data, steps, observability, or relevant branch analysis, and omit sources that did not contribute. Execution enrichment may add operational intermediate expected results supported by those refs; it does not create new normative behavior.

## Coverage Points

Each Coverage Point represents one independently meaningful behavior and has one disposition:

- `TEST_CASE`: `target_refs` contains one or more `TC-XXX` IDs.
- `QUESTION`: `target_refs` contains one or more `Q-XXX` IDs.
- `OUT_OF_SCOPE`: `target_refs` is empty and `reason` records the user's explicit exclusion.

Several Coverage Points may target one TC when they are observations in the same coherent flow. The internal Coverage Extraction Audit adds missing points to this same catalog; it creates no second artifact or layer.

Each clause records `source_refs`, `normalized_claim`, `authority`, `destination_type`, and `destination_id`. A CP may also record `clause_refs` for bidirectional traceability. Each clause mapped to a CP names exactly that CP as its destination. Clauses sent directly to a Question or Finding reference that destination; `OUT_OF_SCOPE` and `NOT_TESTABLE` use a null destination plus a reason.

## Test Case Entry

Every entry identifies its exact JSON and Markdown artifacts:

```json
{
  "id": "TC-001",
  "title": "Submit a draft order",
  "status": "READY",
  "requirement_refs": ["REQ-001"],
  "scenario_refs": ["SCN-001"],
  "coverage_point_refs": ["CP-001"],
  "file": "test-cases/TC-001.json",
  "markdown_file": "test-cases-md/TC-001.md"
}
```

## Individual Test Case

Each `test-cases/TC-XXX.json` contains `schema_version`, ID, title, status, priority, type, objective, requirement/scenario/Coverage Point/source references, preconditions, local test data, ordered steps, postconditions, cleanup, tags, and notes.

Use `READY`, `NEEDS_REVIEW`, or `BLOCKED` for status and `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` for priority. Every step owns its Action and Expected Result. A `null` expected result requires `needs_clarification: true` and a related Question. There are no `subtests` or `automation_candidate` fields.

## Questions

`questions.json` uses schema version `1.2`. Each Question has a stable `Q-XXX` ID, affected TCs and requirements, selected source references, one actionable question, its reason, and a blocking flag. Use an empty `related_test_cases` array when a missing oracle prevents a meaningful TC.

## Markdown and Mermaid

`scripts/render_markdown.py` writes one Markdown file for each indexed TC. It includes title, status, priority, type, objective, preconditions, test data, all steps and expected results, postconditions, cleanup, traceability, and the JSON artifact path.

`## Fluxo do Teste` is the final section. Its final fenced `mermaid` block is a linear action-to-expected-result flow in step order. It does not invent branches or results. A missing result is labeled as requiring clarification.

Markdown derives a `Requirement group` label from an original `RF...` identifier in requirement source refs, falling back to `REQ-XXX`. It does not add that label to JSON.

## HTML

`report.html` is offline and has Summary, Test Cases, Questions, and Coverage navigation. Each TC card shows objective, preconditions, test data, steps, the visual flow extracted from that TC's Markdown, links to the exact JSON and Markdown artifacts, and technical traceability. The renderer converts the verified Mermaid source into deterministic inline SVG; it does not bundle or claim to use Mermaid.js. It loads no CDN and shows no raw JSON by default.

The flow section follows the steps, remains locally scrollable on narrow screens, and offers an accessible `Ampliar fluxo` modal that closes by button, overlay, or `Esc`. A local rendering failure leaves the steps and Markdown link available.

The Test Cases section groups cards by the same derived functional requirement label. A multi-requirement TC appears once under the first normative requirement in source order and lists the other labels as related. A case explicitly tagged `e2e`, `end-to-end`, or `cross-rf` may appear once under `Cross-RF / End-to-End`. Grouping never changes JSON IDs, paths, counts, or links.

For N indexed cases there must be exactly N JSON files, N Markdown files, and N HTML cards, all aligned by TC ID and step content.

## Consistency Invariants

- IDs and selected source paths are unique.
- Every source reference points to a declared selected source.
- Finding references point to existing requirements and selected sources.
- Every testable requirement has at least one Coverage Point.
- Every materialized normative clause has exactly one valid destination; Requirement-level coverage is not a proxy.
- Every Coverage Point has a valid destination and bidirectional TC links agree.
- Every TC maps to existing scenarios, requirements, and Coverage Points.
- Every scenario maps to exactly one TC and every TC has exactly one primary scenario.
- Index metadata and individual case metadata agree.
- Every indexed JSON exists; unindexed TC JSON is invalid.
- JSON and Markdown paths match the TC ID.
- Steps start at 1 and increase consecutively.
- Blocking Questions linked to a TC require that TC to be `BLOCKED`.
- A `READY` case has no clarification-pending step.

Schemas validate document shape. `scripts/validate_output.py` enforces JSON cross-file invariants. Renderers enforce JSON/Markdown/HTML correspondence.
