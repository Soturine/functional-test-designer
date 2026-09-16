# Output Contract 1.0

Write UTF-8 JSON with two-space indentation. All paths are relative to the output directory and use `/` separators. Use the exact `schema_version` value `1.0`.

## Directory Layout

```text
output/
|-- test-cases.json
|-- questions.json
`-- test-cases/
    |-- TC-001.json
    `-- TC-XXX.json
```

Do not write temporary analysis, source copies, or confidential data into `output/`.

## Index: `test-cases.json`

The index is the compact traceability catalog and file manifest.

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-09-16T12:00:00Z",
  "sources": ["docs/requirements.md"],
  "requirements": [
    {
      "id": "REQ-001",
      "statement": "A customer can cancel an order before invoicing.",
      "status": "NEEDS_CLARIFICATION",
      "source_refs": [
        {"source": "docs/requirements.md", "reference": "Cancellation"}
      ]
    }
  ],
  "scenarios": [
    {
      "id": "SCN-001",
      "title": "Cancel an order before invoicing",
      "type": "HAPPY_PATH",
      "requirement_refs": ["REQ-001"]
    }
  ],
  "test_cases": [
    {
      "id": "TC-001",
      "title": "Cancel an order before invoicing",
      "status": "BLOCKED",
      "requirement_refs": ["REQ-001"],
      "scenario_refs": ["SCN-001"],
      "file": "test-cases/TC-001.json"
    }
  ]
}
```

Requirement status is `TESTABLE` or `NEEDS_CLARIFICATION`. Scenario type is one of `HAPPY_PATH`, `NEGATIVE`, `BOUNDARY`, `PERMISSION`, `STATE_TRANSITION`, `RECOVERY`, or `EXPLORATORY`.

## Individual Test Case

Each index entry has one file named after its ID. Keep steps reusable across subtests; put only the varying input and expected result in each subtest.

```json
{
  "schema_version": "1.0",
  "id": "TC-001",
  "title": "Submit quantities within the permitted range",
  "status": "READY",
  "priority": "HIGH",
  "type": "FUNCTIONAL",
  "objective": "Confirm that documented valid boundary quantities are accepted.",
  "requirement_refs": ["REQ-002"],
  "scenario_refs": ["SCN-002"],
  "source_refs": [
    {"source": "docs/requirements.md", "reference": "AC-2"}
  ],
  "preconditions": ["The tester is signed in as an authorized customer."],
  "test_data": [
    {"name": "order", "description": "A synthetic order eligible for quantity changes."}
  ],
  "steps": [
    {
      "step": 1,
      "action": "Open the quantity editor for the synthetic order.",
      "expected_result": "The quantity control is available.",
      "needs_clarification": false
    },
    {
      "step": 2,
      "action": "Enter the quantity specified by the current subtest and submit the change.",
      "expected_result": "The submitted quantity is accepted.",
      "needs_clarification": false
    }
  ],
  "subtests": [
    {
      "id": "ST-001",
      "title": "Minimum valid quantity",
      "input": 1,
      "expected_result": "The submitted quantity is accepted.",
      "needs_clarification": false
    },
    {
      "id": "ST-002",
      "title": "Maximum valid quantity",
      "input": 10,
      "expected_result": "The submitted quantity is accepted.",
      "needs_clarification": false
    }
  ],
  "postconditions": ["The order retains the last accepted quantity."],
  "cleanup": ["Restore or remove the synthetic order."],
  "tags": ["order", "boundary", "valid-partition"],
  "automation_candidate": true,
  "notes": []
}
```

Use `READY`, `NEEDS_REVIEW`, or `BLOCKED` for status. A `null` expected result always requires `needs_clarification: true`. A non-null expected result must be supported by the source; `needs_clarification` may still be true when only part of the observation is known.

Use a separate test case instead of a subtest when setup, action sequence, permission, state transition, risk, or oracle changes materially.

## Questions: `questions.json`

```json
{
  "schema_version": "1.0",
  "questions": [
    {
      "id": "Q-001",
      "related_test_cases": ["TC-001"],
      "requirement_refs": ["REQ-001"],
      "source_refs": [
        {"source": "docs/requirements.md", "reference": "Cancellation"}
      ],
      "question": "What observable final state confirms that the order was cancelled?",
      "reason": "The source permits cancellation but does not define the resulting state or another observable outcome.",
      "blocking": true
    }
  ]
}
```

Questions must resolve a specific missing decision. Link a question to every affected test case; use an empty `related_test_cases` array only when the gap prevented creation of any case.

## Consistency Invariants

- IDs are unique within their collection and match their prefixes.
- Every test-case `requirement_refs` value exists in the index requirement catalog.
- Every test-case `scenario_refs` value exists in the index scenario catalog.
- Every scenario references existing requirements.
- Index metadata and individual case metadata agree.
- Every indexed file exists, and no unindexed `TC-*.json` file is present.
- Step numbers start at 1, increase by 1, and are unique.
- Every question reference resolves to an indexed entity.
- Blocking questions linked to a test case require that case to be `BLOCKED`.
- A `READY` case has no step or subtest needing clarification.

The schemas enforce document shape. `scripts/validate_output.py` additionally enforces uniqueness, paths, referential integrity, file presence, and cross-file status rules.
