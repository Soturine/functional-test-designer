---
name: functional-test-designer
description: Converts requirements, PRDs, user stories, acceptance criteria, and specifications into traceable, executable manual functional test cases and validated JSON. Use when source documents must be analyzed for testability, gaps, test data, and risk-based coverage before manual execution or a future test-management adapter. Do not use to automate tests, report bugs, or verify an implementation against requirements.
---

# Functional Test Designer

Create a compact, source-grounded manual test pack from one or more requirement documents. Produce the JSON artifacts described in [references/output-contract.md](references/output-contract.md), then run the validator. Do not require another skill or the source repository.

## Non-Negotiable Rules

- Treat the source as authoritative. A question, hypothesis, scenario, or risk is not a requirement or an oracle.
- Never invent messages, status codes, internal states, fields, side effects, permissions, or recovery behavior.
- When an essential expected result is unsupported, set it to `null`, mark `needs_clarification: true`, create a precise question, and assign `BLOCKED` when the missing oracle prevents execution.
- Use `NEEDS_REVIEW` when a case remains useful but a material detail needs human confirmation. Use `READY` only when the case is executable as written.
- Test-design techniques are reasoning tools, not output multiplication tools. Consolidate redundant coverage and use subtests for small variations of the same behavior.
- Keep separate cases when they represent distinct behavior, risk, setup, permission, state transition, or recovery flow.
- Use synthetic, non-sensitive test data by default.

## Workflow

### 1. Read and Bound the Sources

Locate the user-designated requirement sources and read only relevant files. Record each source path. Identify the requested feature scope and explicit exclusions. Do not build format-specific parsers when the host can already read the document.

### 2. Normalize Requirements

Extract functional rules, actors, permissions, constraints, states, inputs, outputs, and acceptance criteria.

- Preserve original identifiers in `source_refs`.
- Assign stable local `REQ-001`, `REQ-002`, ... identifiers in source order.
- Split a compound statement only when its parts can be tested independently.
- Do not silently rewrite or strengthen the source.
- Record unsupported or contradictory behavior as questions, not inferred facts.

### 3. Evaluate Testability and Ask Useful Questions

For each requirement, determine whether actor, starting state, trigger, rule, and observable result are supported. Probe only relevant gaps, such as:

- empty, null, minimum, maximum, and off-by-one inputs;
- permissions and calls made in the wrong state or order;
- repetition, duplicate submission, concurrency, and conflicting updates;
- unavailable dependencies, timeout, partial failure, retry, and recovery;
- undefined final state or behavior after failure.

Do not ask what the source already answers. Deduplicate questions by the decision they resolve and link each question to affected requirements and test cases.

### 4. Design Lean Coverage

Read [references/test-design.md](references/test-design.md) when the feature contains ranges, partitions, interacting conditions, workflows, or many independent combinations. Select only techniques that add coverage.

Create stable `SCN-001`, `SCN-002`, ... scenarios and map them to local requirement IDs. Cover positive, negative, permission, state, boundary, and recovery behavior according to actual risk and source support.

Before creating test cases:

1. Merge scenarios that prove the same behavior with the same setup and oracle.
2. Convert small data variations into flat `subtests` when action and expected behavior are shared.
3. Remove combinations already represented by an equivalent partition or pairwise row.
4. Keep separate cases for materially different behaviors or risks.

Prefer a few strong cases over many nearly identical cases.

### 5. Design Test Data

For each case, specify only data that affects execution or coverage: representative valid values, boundary and invalid values, roles, initial states, and required setup. Derive values from documented constraints. If a constraint is unknown, describe the needed characteristic without fabricating a precise value.

### 6. Write Executable Manual Cases

Assign local `TC-001`, `TC-002`, ... identifiers. Each case must have one clear objective and trace to requirements and scenarios.

- Write each step as one concrete user or tester action.
- Pair every action with an observable, source-supported expected result.
- Use verbs such as access, enter, select, submit, query, and observe.
- Put setup in `preconditions`, not hidden in steps.
- Use `subtests` only for shallow variations; do not create nested variation trees.
- Do not use vague fillers such as "verify it works" or invent text merely to make a field non-null.

### 7. Write and Validate Output

Read [references/output-contract.md](references/output-contract.md) and write:

```text
output/
|-- test-cases.json
|-- questions.json
`-- test-cases/
    `-- TC-XXX.json
```

Use paths relative to the output directory. Generate valid JSON, then run:

```bash
python scripts/validate_output.py output
```

Fix every validation error before reporting completion. Summarize source coverage, case counts by status, unresolved blocking questions, and the output path without duplicating the JSON in prose.

## Completion Check

- Every test case maps to at least one requirement and scenario.
- Every index entry maps to exactly one present case file with the same ID.
- Questions are specific, non-redundant, and source-grounded.
- Test data and steps are executable by a human tester.
- Unsupported expected results remain visibly unresolved.
- Test-design coverage has been consolidated rather than mechanically expanded.
- All JSON passes schema and cross-file validation.

