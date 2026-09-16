---
name: functional-test-designer
description: Converts requirement documents into traceable Coverage Points, independent executable manual test cases, validated JSON, and an offline HTML report. Use for greenfield functional test design when requirements are the only functional authority. Do not use backlog, source code, implementations, existing tests, or project history as generation sources.
---

# Functional Test Designer

Operate only in `GREENFIELD_REQUIREMENTS_ONLY` mode. Turn user-designated requirement documents into source-grounded manual test cases using the V1.1 contract in [references/output-contract.md](references/output-contract.md). Validate the JSON and render a friendly offline report.

## Authority and Scope

- Treat the requirement document as the only functional authority.
- Do not inspect or use backlog items, source code, APIs, databases, implementations, commits, issues, existing test cases, test plans, execution history, or automation as input.
- Do not use observed implementation behavior to fill a requirement gap or expected result.
- Preserve: requirement != hypothesis; question != requirement; scenario != requirement; risk != expected result; implementation != contract.
- Never invent messages, status codes, internal states, fields, side effects, permissions, or recovery behavior.
- Use only synthetic, non-sensitive test data.

If a necessary oracle is absent, route the behavior to a Question. Create a `BLOCKED` case only when useful executable structure remains but the missing oracle prevents a correct Pass/Fail decision.

## Optional Diagnostic Mode

When the user requests `Diagnostic: true`, read [references/diagnostics.md](references/diagnostics.md) before reading the source. Start the timer immediately and record real wall-clock time for the macro stages. Do not estimate missing timings or record requirement text, names, payloads, credentials, or other sensitive content.

## Workflow

### 1. Read Requirement Sources

Locate and read only the requirement documents designated by the user. Record source paths, original identifiers, explicit scope, and explicit exclusions. Do not build parsers when the host can read the format.

### 2. Normalize Requirements

Extract actors, rules, permissions, states, inputs, outputs, constraints, and acceptance behavior.

- Assign stable local `REQ-001`, `REQ-002`, ... IDs in source order.
- Preserve original identifiers and locations in `source_refs`.
- Split compound requirements only where their behaviors can be evaluated independently.
- Mark unsupported or contradictory behavior `NEEDS_CLARIFICATION`; do not strengthen the source.

### 3. Extract Coverage Points

Decompose every normative behavior into a stable `CP-001`, `CP-002`, ... Coverage Point. A Coverage Point controls behavioral coverage; it is not automatically a Test Case.

Route every Coverage Point to exactly one disposition:

- `TEST_CASE`: one or more independent TCs cover the behavior.
- `QUESTION`: the behavior lacks a sufficient oracle and points to one or more Questions.
- `OUT_OF_SCOPE`: the user explicitly excluded the behavior; include a specific reason and no target.

Never use `OUT_OF_SCOPE` to hide a gap. No Coverage Point may disappear or remain without a valid destination.

### 4. Evaluate Testability and Ask Questions

Check actor, starting state, trigger, normative rule, and observable result. Probe only relevant gaps such as bounds, null/empty input, permissions, invalid order/state, repetition, concurrency, unavailable dependencies, partial failure, retry, and recovery.

Questions must resolve a specific decision, remain source-grounded, avoid duplication, and link to affected requirements and cases.

### 5. Select Test Design Only When Useful

Read [references/test-design.md](references/test-design.md) only when the requirements contain ranges, partitions, states, multiple interacting conditions, many combinations, or another concrete need for a design technique. Otherwise continue without loading it.

Use techniques to choose better scenarios and remove redundant combinations. They must not invent oracles, create extra structures, or hide independent behaviors.

### 6. Create Scenarios and Independent Test Cases

Assign stable `SCN-001`, `SCN-002`, ... scenario IDs and `TC-001`, `TC-002`, ... case IDs.

Create a separate TC when a condition:

- needs its own Pass/Fail result;
- can fail or produce a bug independently;
- requires independent evidence;
- has different setup, action sequence, risk, or oracle.

Use multiple steps in one TC when they form one coherent flow. There are no subtests in V1.1. Do not compress independent boundaries, permissions, or failure modes into one case merely to reduce volume.

### 7. Write Test Data, Priority, and Steps

Specify only data that affects execution: representative values, roles, states, boundaries, and required setup. Derive exact values from documented constraints.

Choose priority from source evidence or this fallback:

- `CRITICAL`: central flow, integrity, critical security, or central blocker.
- `HIGH`: important mandatory business rule.
- `MEDIUM`: alternative flow, important validation, or insufficient priority evidence.
- `LOW`: non-blocking edge or performance concern.

For every step:

- write one concrete, executable action;
- write its corresponding observable, source-supported expected result;
- use `expected_result: null` and `needs_clarification: true` when unsupported;
- create a related Question for every clarification-pending step.

Do not use vague actions such as "verify it works". Do not create one giant expected result after several actions.

### 8. Deduplicate Without Hiding Behavior

Remove true duplicates and combinations that add no coverage. Keep separate cases for independently reportable behavior. Several Coverage Points may map to one TC when they are observations in the same coherent execution flow.

### 9. Write, Validate, and Render

Read [references/output-contract.md](references/output-contract.md), then write the V1.1 JSON. Treat schemas as validator internals: do not read them before generation unless validation fails and the error is insufficient.

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
`-- test-cases/
    `-- TC-XXX.json
```

Run in this order:

```bash
python scripts/validate_output.py output
python scripts/render_report.py output
```

Fix all validation errors before rendering or reporting completion. The renderer must never change JSON or repair content.

### 10. Summarize

Report counts for requirements, Coverage Points, scenarios, Test Cases, steps, statuses, and questions; state validator and HTML results. In diagnostic mode, finish the metrics file and include only real timing in a compact `Stage | Time | Work | Result` table.

## Completion Check

- Requirements were the only generation source.
- Every testable behavior has a Coverage Point with a valid destination.
- Every TC traces through Coverage Points, scenarios, and requirements.
- Each independently reportable behavior has its own TC.
- Every step has Action and Expected Result; unsupported results remain visible.
- No generated JSON contains `subtests` or `automation_candidate`.
- JSON validation passes before the offline HTML is rendered.
- Diagnostic metrics, when requested, remain outside the TC output and contain no sensitive content.

