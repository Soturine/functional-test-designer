# Evidence Enrichment and Execution Paths

Read this reference after atomic scenarios exist whenever selected non-normative sources may contribute execution detail, test data, observability, risk, or existing coverage. Work only from the compact evidence map built from explicitly selected sources; do not reopen every source per TC or expand scope.

## Evidence Pack

For each scenario, assemble an internal Evidence Pack; do not create a public file. Record:

- normative oracle: authority, requirement, clause, and Coverage Point;
- execution path: selected-source evidence for route, screen, form, action, API, payload, sequence, or administrative operation;
- preconditions: actor, permission, entity, initial state, configuration, dependency, or prior record;
- test-data constraints: format, length, range, enum, relationship, date, state, identifier, and known invalid values;
- observability: visible status, message, record, history, response, selected log, report, or related entity;
- implementation branches: observable conditions, validation, fallback, conflict, exception, feature flag, or residual behavior;
- existing test assets: setup, regressions, variations, edge cases, and legacy subtests;
- divergences: differences between authority and other evidence.

Functional authority defines required business outcomes. Technical context can support how to reach and observe them. Implementation evidence can support the observed path and reveal branches or divergence. Test assets can support existing setup, regression risk, and exercised paths. None of those roles silently becomes normative authority.

Add a source to a TC's `source_refs` only when it actually supports that TC's precondition, data, step, observation, branch analysis, or oracle. Do not copy every selected source into every case.

## Opportunity Triage

For an observable branch or edge case found outside functional authority:

1. If an applicable normative oracle exists, design an ordinary scenario linked to it.
2. If only observed implementation behavior exists, do not create a normative clause or CP. Use existing `NEEDS_REVIEW`, Question, Finding, tags, and notes as appropriate.
3. If it contradicts authority, create a Finding and retain the authoritative expected result; a related TC may coexist with the Finding.
4. If it is internal and has no observable risk or outcome, do not create a TC.

Finalize Questions only after searching all pertinent selected evidence. Ask only for information still absent.

## Execution Path Synthesis

Start from legitimate preconditions, follow the supported path to the trigger, and end at an observable result. A tester with basic product knowledge should not need to guess a path already documented in the selected evidence.

Scenario identity and the normative oracle must already be frozen. Use the internal procedural synthesis contract in [procedural-execution.md](procedural-execution.md); execution enrichment may not alter an existing Test Case, its Scenario relations, requirement refs, Coverage Point refs, or normative oracle. A procedural worker can only report a late independent candidate. The main authority may append a separately justified Scenario and TC during one bounded additive pass; it never removes, merges, renumbers, or rewrites frozen cases.

- Atomic TC does not mean single-step TC. Keep dependent navigation and actions in the same case.
- A condition with independent setup, execution, evidence, oracle, or Pass/Fail remains a separate TC.
- Do not repeat authentication or expensive setup as steps when they are legitimate preconditions.
- Do not hide the entire path in a precondition such as “flow already completed to the last screen.”
- Do not inflate steps with cursor movement, obvious browser mechanics, or observations that add no operational value.
- Avoid objective-like actions such as “execute the flow,” “perform the process,” or “validate functionality” when concrete selected evidence exists.
- Operational expected results may describe a supported intermediate screen, modal, response, or state. They remain observed execution evidence, not new business requirements.
- If no path is supported, use only the defensible level of action. Never invent a menu, button, route, field, endpoint, or payload. Create a focused Question or `NEEDS_REVIEW` case only when the missing path prevents execution.

Use natural step granularity. One step is valid when one coherent action reaches the result from the preconditions. Split a documented sequence when order, intermediate state, or distinct failure points matter; do not compress `open, select, enter, confirm` into one action. Conversely, do not inflate cursor movement, individual keystrokes, or obvious mechanics into steps. There is no target number of steps.

Build each selected source entry and scenario-family Evidence Pack once in the run-local evidence map. Reuse shared actor, setup, navigation, constraints, observability, and source refs across related TCs, then specialize only scenario-specific parts. Reopen a source only for truncation, unresolved ambiguity, or a verification detail not retained in the map. Batch design by RF/scenario family while validating every TC independently.

Evidence reuse optimizes context retrieval, not Scenario or Test Case count. A shared requirement, family, actor, setup, navigation, source, or Evidence Pack never justifies merging independently reportable Pass/Fail boundaries.

## Test Data

Use concrete synthetic values when selected constraints make them defensible: explicit boundaries, lengths, enums, states, and formats. Apply BVA/EP selectively and record a technique tag only when it materially shaped the case.

When the format is incomplete, use an honest placeholder such as `<valid test document>` instead of fabricating a plausible business identifier. Never generate real credentials, tokens, personal data, customer email addresses, or private identifiers.

## Enrichment Regression Boundary

Evidence Enrichment normally changes preconditions, local test data, ordered steps, source provenance, observability, tags/notes, and presentation. It must not silently change valid requirement normalization, normative clauses, Coverage Points, scenario identity, TC independence, normative oracle, status, or disposition. Change those only to fix a demonstrated pre-existing defect, and update the normative regression baseline deliberately with the reason.

Before materialization, check every TC:

1. Which independent behavior does it prove, and which authority owns the oracle?
2. Which selected sources support its execution path and observations?
3. Are setup and test data concrete enough without invention?
4. Do ordered actions reach the trigger, and is every result observable?
5. Should any condition be another TC, or has any independent condition been compressed?
6. Was useful selected evidence ignored, or was unsupported information added?

Do not claim exhaustive test-space coverage merely because all extracted clauses have destinations.
