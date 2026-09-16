---
name: functional-test-designer
description: Designs traceable functional manual tests from only the sources explicitly selected by the user, including requirements, code, technical documents, and existing QA assets. Use to resolve a bounded source scope, extract and audit Coverage Points, create independent executable test cases, validate JSON, and render per-case Markdown plus an offline HTML report.
---

# Functional Test Designer

Operate only on sources explicitly selected by the user. Selected paths are the complete content-analysis boundary: a selected directory is recursive only inside itself, and a selected file authorizes only that file. Produce source-grounded Coverage Points, independent manual Test Cases, validated JSON, per-case Markdown, and an offline HTML report using [references/output-contract.md](references/output-contract.md).

## Scope Boundary

Resolve natural-language selections into exact files, directories, or explicit globs before reading content.

- A selected directory permits recursive discovery only below that directory, never its siblings.
- A selected file permits only that file.
- Multiple selected paths form the allowed roots; no neighboring path is implied.
- Do not follow imports, includes, links, dependencies, references, or repository structure outside those roots.
- Metadata-only path discovery is allowed for resolution. Do not grep or inspect content outside scope.
- If a basename has multiple matches, ask one short disambiguation question before reading either match.
- Normalize paths and reject `..`, symlink, or junction escapes from the workspace or selected directory.
- Ignore `.git`, `.venv`, `venv`, `node_modules`, `dist`, `build`, `coverage`, `__pycache__`, and `.cache` during directory discovery.
- If another source seems necessary, identify its path and why it matters, then wait for explicit selection. Do not read it.

Use `scripts/resolve_scope.py` when deterministic path resolution is useful. It reads metadata only.

## Evidence Authority

Classify every selected source in `test-cases.json`:

- `FUNCTIONAL_AUTHORITY`: approved requirement, specification, or acceptance criteria.
- `IMPLEMENTATION_EVIDENCE`: selected source code or runtime configuration.
- `TEST_ASSET`: selected existing Test Case, test plan, script, or QA artifact.
- `TECHNICAL_CONTEXT`: selected ADR, API description, or technical documentation.
- `OTHER_SELECTED`: selected evidence that fits none of the above.

Functional authority defines normative expected behavior. Implementation evidence may improve executable context or reveal divergence, but never silently replaces a normative expected result. Existing Test Cases are artifacts to audit, not automatic truth. Test plans and scripts are coverage evidence. Technical documents are context unless the user explicitly establishes them as authority.

When selected sources disagree, record a finding with traceability and keep the authoritative oracle. If no functional authority exists and the task audits implementation, label derived behavior as implementation evidence. Never invent messages, statuses, fields, states, side effects, permissions, or recovery behavior. Use only synthetic, non-sensitive test data.

## Workflow

### 1. Resolve Scope and Read Sources Once

Resolve the user's selected roots, list the exact files in scope, and read only those files. Build a compact internal evidence map during the initial read so later stages do not repeatedly reopen sources. Track rereads when diagnostics are requested.

### 2. Normalize Evidence

Extract actors, rules, permissions, states, inputs, outputs, constraints, acceptance behavior, and existing coverage evidence.

- Assign stable `REQ-001`, `REQ-002`, ... IDs in source order.
- Preserve original identifiers and locations in `source_refs`.
- Separate normative authority from implementation and test evidence.
- Split compound requirements only where behaviors can fail independently.
- Mark unsupported or contradictory behavior `NEEDS_CLARIFICATION`; do not strengthen a source.

### 3. Extract and Audit Coverage Points

Decompose normative behavior into stable `CP-001`, `CP-002`, ... Coverage Points. A Coverage Point controls behavioral coverage; it does not automatically create a Test Case.

After the initial extraction, make a short second pass over the internal evidence map. Confirm that every normative clause, bullet, acceptance criterion, flow step, alternate, exception, postcondition, transition, restriction, observable outcome, explicit side effect, cancellation, reversal, finalization, permission, boundary, message, and state has a Coverage Point.

- Merge duplicates that describe the same behavior and retain all relevant `source_refs`.
- Keep separate points for effects that can fail independently.
- Route known behavior toward a TC and ambiguous behavior toward a Question.
- Do not create a second coverage artifact or another CP layer.

Every Coverage Point has exactly one disposition: `TEST_CASE`, `QUESTION`, or an explicitly justified `OUT_OF_SCOPE`. Never use `OUT_OF_SCOPE` to hide a gap.

### 4. Evaluate Testability and Questions

Check actor, starting state, trigger, normative rule, and observable result. A missing oracle becomes a focused Question. Create a `BLOCKED` case only when useful executable structure remains but the missing decision prevents a correct Pass/Fail result.

### 5. Apply Test Design Selectively

Read [references/test-design.md](references/test-design.md) only when ranges, partitions, states, interacting conditions, or combinatorial inputs justify it. BVA, EP, Decision Tables, State Transition, and Pairwise are reasoning tools, not output multiplication tools.

Use techniques to improve coverage and reduce redundant combinations. Pairwise specifically replaces unnecessary exhaustive combinations. Do not apply every technique or emit every analyzed value.

### 6. Design and Deduplicate Scenarios Early

Create candidate scenarios, then remove semantic duplicates before materializing TCs. Keep separate scenarios when behavior, risk, setup, flow, oracle, or evidence can fail independently. Assign stable `SCN-001`, `SCN-002`, ... IDs only after deduplication.

### 7. Generate Independent Test Cases

Assign stable `TC-001`, `TC-002`, ... IDs. Independent scenario means independent TC. Use multiple steps only for one coherent flow. There are no `subtests` and no `automation_candidate`.

Generate test data lazily with the TC that uses it; do not create a global test-data phase or catalog. Additional selected context may add setup or steps only when that evidence confirms a real executable flow.

For every step:

- write one concrete action;
- attach its corresponding observable expected result;
- use `expected_result: null` and `needs_clarification: true` when unsupported;
- link every clarification-pending step to a Question.

### 8. Write, Validate, and Render

Write final contract artifacts directly. Do not create per-run generator scripts or temporary source copies. Read schemas only if a validator failure is unclear.

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

Run in this order:

```bash
python scripts/validate_output.py output
python scripts/render_markdown.py output
python scripts/render_report.py output
```

The Markdown renderer reads validated JSON and changes no JSON. The HTML renderer reads each corresponding Markdown Mermaid block and displays that same linear flow. Fix all errors before completion.

### 9. Summarize

Report selected scope roots, resolved files, files opened outside scope, source rereads, temporary files, requirements, Coverage Points, findings, scenarios, TCs, steps, statuses, Questions, Markdown count, validator result, and HTML result. Files opened outside scope must be zero; any nonzero value is a scope violation.

When diagnostics are explicitly requested, follow [references/diagnostics.md](references/diagnostics.md). Record real observations only and no sensitive content.

## Completion Check

- Only explicitly selected source content was analyzed.
- Functional authority and other evidence roles remained distinct.
- The internal Coverage Extraction Audit found no unmapped normative clause.
- Known and ambiguous parts were split between TCs and Questions.
- Scenario candidates were deduplicated before TC generation.
- Test design improved coverage without inflating output.
- Every TC is independently reportable; coherent flows use ordered steps.
- JSON contains neither `subtests` nor `automation_candidate`.
- JSON validated before Markdown; Markdown existed before HTML.
- JSON, Markdown, and HTML cards correspond 1:1 by TC ID.
- Every Markdown ends with its Mermaid flow, and HTML uses the same flow.
