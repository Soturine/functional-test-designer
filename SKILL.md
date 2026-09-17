---
name: functional-test-designer
description: Designs traceable functional manual tests from only the sources explicitly selected by the user, including requirements, code, technical documents, and existing QA assets. Use to resolve a bounded source scope, extract and audit Coverage Points, create independent executable test cases, validate JSON, and render per-case Markdown plus an offline HTML report.
---

# Functional Test Designer

Operate only on sources explicitly selected by the user. Selected paths are the complete content-analysis boundary: a selected directory is recursive only inside itself, and a selected file authorizes only that file. Produce source-grounded Coverage Points, independent manual Test Cases, validated JSON, per-case Markdown, and an offline HTML report using [references/output-contract.md](references/output-contract.md).

## Roots and Artifact Destination

Keep four roots distinct:

- `skill_root` locates this skill's instructions, scripts, schemas, references, tests, and examples.
- `source_root` contains the selected sources and is input only.
- `workspace_root` is the trusted working directory for the run, when one is safely known.
- `artifact_root` is the exact destination explicitly supplied by the user.

Before the first write, resolve and validate the destination with `scripts/resolve_artifacts.py`. Prefer the exact explicit `artifact_root`, otherwise a trusted `workspace_root`; if neither is available, ask where to write. Never infer the destination from the current working directory, never use `skill_root` as a fallback, and never use `source_root` unless the user explicitly selected it as the artifact destination. Treat the supplied path as the final artifact root: do not append `functional-test-designer` or create a sibling directory named after the skill.

Write only `artifact_root/output` and, when requested, `artifact_root/diagnostics`. Pass those resolved paths to every script rather than relying on their CLI defaults. Record `artifact_root`, `output_path`, `diagnostics_path`, and `artifact_root_source` (`explicit_user_path`, `workspace`, or `prompted`) in diagnostics.

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

Functional authority defines normative expected behavior, but it is not the only useful design evidence. Technical context can explain how to reach and observe a behavior. Implementation evidence can make execution concrete and reveal branches or divergence. Existing Test Cases are artifacts to audit for setup, regressions, edge cases, and coverage, not automatic truth. All selected roles may enrich Test Design; only appropriate authority can establish mandatory business behavior.

When selected sources disagree, record a finding with traceability and keep the authoritative oracle. If no functional authority exists and the task audits implementation, label derived behavior as implementation evidence. Never invent messages, statuses, fields, states, side effects, permissions, or recovery behavior. Use only synthetic, non-sensitive test data.

## Workflow

### 1. Resolve Scope and Read Sources Selectively

Resolve the user's selected roots and inventory paths/metadata before opening content. Use the read plan from `scripts/resolve_scope.py`: prioritize relevant textual requirements, functional documentation, code, configuration, and tests; keep common binaries metadata-only by default. Open images only when they contain essential behavior absent from text and vision is available. Read CSS only for relevant visual behavior and migrations only for relevant constraints, states, schema changes, or compatibility. Treat semantically equivalent bilingual documents as one normalized claim with both source refs. Read in bounded batches and build a compact evidence map so later stages do not repeatedly reopen sources. Track reads and rereads when diagnostics are requested.

### 2. Extract Clauses, Then Normalize Evidence

Extract atomic normative clauses before summarizing them into logical Requirements, starting from atomic normative source claims. A bullet or sentence may contain one or many claims. Split `and` outcomes, `or` alternatives, and enumerated effects when one could be wrong while another remains correct; do not split inseparable representations mechanically. Preserve every claim and clause source ref even when several belong to one `REQ-XXX`.

- Assign stable `REQ-001`, `REQ-002`, ... IDs in source order.
- Preserve original identifiers and locations in `source_refs`.
- Separate normative authority from implementation and test evidence.
- Split independent verbs, outcomes joined by `and`, alternatives joined by `or`, filter dimensions, permissions, timing limits, boundaries, states, transitions, search, detail, and export behavior. `alerts and records` is two clauses; `finalize, reverse, or cancel releases the link` is three clauses.
- Equivalent translations become one clause with all source refs; a real difference becomes a finding.
- Mark unsupported or contradictory behavior `NEEDS_CLARIFICATION`; do not strengthen a source.

### 3. Extract and Audit Coverage Points

Map each clause to a stable, atomic `CP-001`, `CP-002`, ... Coverage Point or another explicit destination. A Coverage Point represents one observable behavior or one specific outcome; if two parts could fail independently, split them. A Coverage Point controls behavioral coverage; it does not automatically create a Test Case.

After the initial extraction, make a short second pass over each authorized normative passage in the internal evidence map. For every independent clause or observable effect, ask whether a Coverage Point exists. Inspect effects joined by `and`, `or`, `also`, `when`, `after`, `on finalization`, `on cancellation`, and `on reversal`, plus normative verbs such as must, prevents, releases, records, alerts, keeps, removes, and updates. Confirm that every normative clause, bullet, acceptance criterion, flow step, alternate, exception, fallback, postcondition, transition, restriction, observable outcome, explicit side effect, permission, boundary, message, and state has a Coverage Point.

- Merge duplicates that describe the same behavior and retain all relevant `source_refs`.
- Keep separate points for effects that can fail independently.
- Expand explicit alternatives separately: finalization, reversal, and cancellation do not cover one another.
- Route known behavior toward a TC and ambiguous behavior toward a Question.
- When an event has a partial oracle, preserve known effects as ordinary coverage and ask only about the missing effects.
- Do not create a second coverage artifact or another CP layer.

Every clause has exactly one destination: Coverage Point, Question, explicitly justified Out of Scope/Not Testable, or an appropriate conflict Finding. Every Coverage Point has exactly one disposition: `TEST_CASE`, `QUESTION`, or an explicitly justified `OUT_OF_SCOPE`. `unmapped_normative_clauses` is zero only after this clause-level audit; the existence of any CP for a Requirement proves nothing about its other clauses. Never use `OUT_OF_SCOPE` to hide a gap.

### 4. Evaluate Testability and Candidate Questions

Check actor, starting state, trigger, normative rule, and observable result. Record candidate gaps, but finalize Questions only after Evidence Enrichment searches all pertinent selected sources. A missing oracle becomes a focused Question that asks only for absent information and does not repeat known outcomes. Create a `BLOCKED` case only when useful executable structure remains but the missing decision prevents a correct Pass/Fail result.

### 5. Apply Test Design Selectively

Read [references/test-design.md](references/test-design.md) only when ranges, partitions, states, interacting conditions, or combinatorial inputs justify it. BVA, EP, Decision Tables, State Transition, and Pairwise are reasoning tools, not output multiplication tools.

Use techniques to improve coverage and reduce redundant combinations. Pairwise specifically replaces unnecessary exhaustive combinations. Do not apply every technique or emit every analyzed value.

### 6. Design and Deduplicate Scenarios Early

Create atomic candidate scenarios from atomic Coverage Points, then remove only genuine semantic duplicates before materializing TCs. Two candidates are duplicates only when behavior, relevant setup, essential action, expected result, oracle, and required evidence are all the same. Keep them separate when any difference changes an independent Pass/Fail result, including actor, permission, input, boundary, state, transition, error, recovery, retry, finalization, reversal, or cancellation. Assign stable `SCN-001`, `SCN-002`, ... IDs only after deduplication. Do not optimize for a lower TC count.

### 7. Enrich Evidence and Synthesize Execution Paths

Read [references/evidence-enrichment.md](references/evidence-enrichment.md) when selected technical context, implementation evidence, or QA assets can contribute execution detail, data, observability, branches, or prior coverage. Build each selected-source entry and shared scenario-family Evidence Pack once, then reuse it during generation, enrichment, and audits. For every final scenario, consult this compact in-scope evidence map before materialization. Do not create a public cache or reopen every file per TC.

Keep the normative oracle anchored to functional authority while using genuinely contributing selected evidence for preconditions, concrete local test data, ordered actions, intermediate observations, opportunity analysis, Findings, and minimal Questions. Add those contributing sources to the TC's `source_refs`; never add decorative provenance.

Synthesize a reproducible path from legitimate preconditions through dependent actions to the scenario trigger and observable result. Atomicity does not imply one step. Preserve a legitimate one-step case when one supported action reaches the result; preserve multiple steps when each depends on prior state. Do not inflate steps or invent UI/API details when no selected source supports them.

Use natural step granularity, never a fixed step template. Split a documented operational sequence when order, intermediate state, or separate failure points matter. Keep one coherent action together and never split cursor movement or keystrokes merely to increase the count.

Evidence Enrichment normally changes execution fields and presentation, never valid normative normalization, clauses, CPs, scenario identity, TC independence, oracle, status, or disposition. Treat such a change as a regression unless it fixes a demonstrated pre-existing defect.

### 8. Generate Independent Test Cases

Assign stable `TC-001`, `TC-002`, ... IDs. Independent scenario means independent TC. Before adding an action as another step, ask: "Can this action be executed and evaluated without the previous steps in this TC?" If yes and it has its own verifiable result, create another TC. Keep multiple steps only when later actions depend on state produced by earlier actions in one sequential flow.

Create another TC when a condition can fail alone, produce its own bug or Pass/Fail, require separate evidence, use different setup, actor, permission, input, boundary, transition, failure, or oracle, or be executed separately in a Test Runner. Never hide independent unauthenticated, invalid-input, not-found, permission, boundary, or failure scenarios as steps of one TC. There are no `subtests` and no `automation_candidate`.

Generate test data lazily with the TC that uses it; do not create a global test-data phase or catalog. Additional selected context may add setup or steps only when that evidence confirms a real executable flow.

When a selected legacy QA asset contains `subtest`, `sub-test`, `subteste`, `subcaso`, or nested conditions, classify every item. Convert it to an independent TC when it has its own setup, input, oracle, evidence, bug, or Pass/Fail and does not depend on preceding state. Convert it to an ordered step only when it is part of one sequential flow and depends on state produced earlier. Account for every input subtest; never emit a `subtests` field.

For every step:

- write one concrete action;
- attach its corresponding observable expected result;
- use `expected_result: null` and `needs_clarification: true` when unsupported;
- link every clarification-pending step to a Question.

### 9. Audit Source Coverage and Cross-Requirement Overlap

Read [references/source-coverage-audit.md](references/source-coverage-audit.md). After the candidate suite exists, perform one source-first per-RF/RN audit, one bounded recovery pass through the full design pipeline, and one verification pass. Do not treat complete clause mapping as proof that every source claim was extracted.

When a selected normative source explicitly declares applicable RN/CU/related requirements, read [references/normative-applicability.md](references/normative-applicability.md). Include resolved in-scope claims in the owning RF/RN audit, record unresolved references without leaving scope, deduplicate equivalent claims with provenance, and turn authority conflicts into Findings.

Then read [references/cross-rf-audit.md](references/cross-rf-audit.md) and run one advisory semantic comparison over the stable suite. Report multi-RF coverage, duplicate candidates, and similar-but-distinct cases; never merge or remove automatically.

Derive presentation names from official source references as `RF001 — Official title` or `RN001 — Official title`. When the identifier is present without an extractable title, use `RF001 — Sem título extraído`; otherwise fall back to the normalized `REQ-XXX`. These names are presentation only and do not change JSON.

### 10. Write, Validate, and Render

Finish semantic generation for all TCs in memory before writing. The `json_write` stage performs deterministic serialization only: aggregate JSON, individual JSON, byte/file counts. Do not reopen sources, call external reasoning, or regenerate each TC during this stage. Write final contract artifacts directly; do not create per-run generator scripts or temporary source copies. Read schemas only if a validator failure is unclear.

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
python scripts/validate_output.py <artifact_root>/output
python scripts/render_markdown.py <artifact_root>/output
python scripts/render_report.py <artifact_root>/output
```

The Markdown renderer reads validated JSON and changes no JSON. The HTML renderer reads each corresponding Markdown Mermaid block and displays that same linear flow. Fix all errors before completion.

### 11. Summarize

Derive the final summary from run state, diagnostics, and final JSON; do not reopen sources or repeat semantic analysis. Report selected scope roots, resolved files, files opened outside scope, source rereads, temporary files, requirements, Coverage Points, findings, scenarios, TCs, steps, statuses, Questions, Markdown count, validator result, and HTML result. Files opened outside scope must be zero; any nonzero value is a scope violation.

When diagnostics are explicitly requested, follow [references/diagnostics.md](references/diagnostics.md). Begin each stage before its reasoning starts, materialize its result while the timer is active, and end it afterward. Record real observations only and no sensitive content.

## Completion Check

- Only explicitly selected source content was analyzed.
- Functional authority and other evidence roles remained distinct.
- The internal Coverage Extraction Audit found no unmapped normative clause.
- Every materialized normative clause has exactly one explicit destination.
- Known and ambiguous parts were split between TCs and Questions.
- Scenario candidates were deduplicated before TC generation.
- Test design improved coverage without inflating output.
- Every TC is independently reportable; coherent flows use ordered steps.
- Each TC is executable at the detail supported by selected evidence; no documented path is collapsed into an abstract action.
- TC source refs include every source role that actually contributed and no decorative sources.
- Evidence Enrichment did not silently redefine valid normative coverage or scenario identity.
- Source-first coverage was audited independently of clause mapping, recovered once, and verified once.
- Every explicitly applicable in-scope RN/CU contributed its claims; unresolved references did not expand scope.
- Step counts reflect supported path complexity rather than a fixed template.
- Evidence and shared scenario-family setup were reused without reducing coverage.
- Cross-RF analysis was advisory; no TC was automatically merged or removed.
- JSON contains neither `subtests` nor `automation_candidate`.
- JSON validated before Markdown; Markdown existed before HTML.
- JSON, Markdown, and HTML cards correspond 1:1 by TC ID.
- Every Markdown ends with its Mermaid flow, and HTML uses the same flow.
