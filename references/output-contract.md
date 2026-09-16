# Output Contract 1.1

Write UTF-8 JSON with two-space indentation. Paths are relative to the output directory and use `/` separators. Use the exact `schema_version` value `1.1`.

## Files

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
`-- test-cases/
    |-- TC-001.json
    `-- TC-XXX.json
```

`report.html` is derived presentation, not source data. Do not write analysis notes, source copies, diagnostics, or confidential data into `output/`.

## Index

`test-cases.json` contains requirements, Coverage Points, scenarios, and the TC file manifest:

```json
{
  "schema_version": "1.1",
  "generated_at": "2026-09-16T12:00:00Z",
  "sources": ["docs/requirements.md"],
  "requirements": [
    {
      "id": "REQ-001",
      "statement": "A customer can cancel an order before invoicing.",
      "status": "NEEDS_CLARIFICATION",
      "source_refs": [{"source": "docs/requirements.md", "reference": "Cancellation"}]
    }
  ],
  "coverage_points": [
    {
      "id": "CP-001",
      "requirement_ref": "REQ-001",
      "statement": "The observable result of cancellation must be defined.",
      "source_refs": [{"source": "docs/requirements.md", "reference": "Cancellation"}],
      "disposition": "QUESTION",
      "target_refs": ["Q-001"]
    }
  ],
  "scenarios": [],
  "test_cases": []
}
```

Requirement status is `TESTABLE` or `NEEDS_CLARIFICATION`. Scenario type is `HAPPY_PATH`, `NEGATIVE`, `BOUNDARY`, `PERMISSION`, `STATE_TRANSITION`, `RECOVERY`, or `EXPLORATORY`.

## Coverage Point Dispositions

Each Coverage Point represents one normative behavior and has exactly one disposition:

- `TEST_CASE`: `target_refs` contains one or more `TC-XXX` IDs.
- `QUESTION`: `target_refs` contains one or more `Q-XXX` IDs.
- `OUT_OF_SCOPE`: `target_refs` is empty and `reason` explains the user's explicit exclusion.

Several Coverage Points may target the same TC when they are observations in one coherent flow. One Coverage Point may target several TCs when separate execution contexts are necessary.

## Test Case Entry

Every index entry includes `coverage_point_refs` and points to one file:

```json
{
  "id": "TC-001",
  "title": "Reject a quantity below the minimum",
  "status": "READY",
  "requirement_refs": ["REQ-002"],
  "scenario_refs": ["SCN-002"],
  "coverage_point_refs": ["CP-002", "CP-003"],
  "file": "test-cases/TC-001.json"
}
```

## Individual Test Case

```json
{
  "schema_version": "1.1",
  "id": "TC-001",
  "title": "Reject a quantity below the minimum",
  "status": "READY",
  "priority": "MEDIUM",
  "type": "FUNCTIONAL",
  "objective": "Confirm that quantity 0 is rejected without changing the existing quantity.",
  "requirement_refs": ["REQ-002"],
  "scenario_refs": ["SCN-002"],
  "coverage_point_refs": ["CP-002", "CP-003"],
  "source_refs": [{"source": "docs/requirements.md", "reference": "Quantity"}],
  "preconditions": ["A DRAFT order line has quantity 5."],
  "test_data": [{"name": "quantity", "description": "Below-minimum value: 0."}],
  "steps": [
    {
      "step": 1,
      "action": "Set the quantity to 0 and submit the change.",
      "expected_result": "The value is rejected and the quantity remains 5.",
      "needs_clarification": false
    }
  ],
  "postconditions": ["The quantity remains 5."],
  "cleanup": ["Remove the synthetic order."],
  "tags": ["quantity", "boundary"],
  "notes": []
}
```

Use `READY`, `NEEDS_REVIEW`, or `BLOCKED` for status and `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` for priority. There is no `subtests` or `automation_candidate` field in V1.1.

Every step owns its Action and Expected Result. A `null` expected result requires `needs_clarification: true` and a related Question.

## Questions

```json
{
  "schema_version": "1.1",
  "questions": [
    {
      "id": "Q-001",
      "related_test_cases": [],
      "requirement_refs": ["REQ-001"],
      "source_refs": [{"source": "docs/requirements.md", "reference": "Cancellation"}],
      "question": "What observable result confirms successful cancellation?",
      "reason": "The source permits cancellation but defines no observable outcome.",
      "blocking": true
    }
  ]
}
```

Use an empty `related_test_cases` array when the missing oracle prevents creation of a meaningful case.

## Consistency Invariants

- IDs are unique and use their declared prefixes.
- Every testable requirement has at least one Coverage Point.
- Every Coverage Point references an existing requirement and source.
- Every Coverage Point has a valid `TEST_CASE`, `QUESTION`, or explicit `OUT_OF_SCOPE` destination.
- TC and Coverage Point links agree in both directions.
- Every TC maps to existing scenarios and requirements, and index metadata matches its file.
- Every indexed file exists; unindexed TC JSON files are invalid.
- Step numbers start at 1 and increase consecutively.
- Blocking Questions linked to a TC require that TC to be `BLOCKED`.
- A `READY` case has no clarification-pending step.

The schemas validate document shape. `scripts/validate_output.py` enforces uniqueness, paths, file presence, referential integrity, and cross-file rules.
