# Procedural Execution Synthesis

Read this reference only after final Scenarios have produced immutable Test identities. This stage answers **how to execute**; it does not reconsider **what to test**.

## Frozen Boundary

Freeze the TC ID, title, objective, material preconditions, test-data partition, assertions, execution boundary, Scenario relation, requirement refs, Coverage Point refs, normative source refs, and normative oracle before synthesis. `scripts/procedural_execution.py` accepts that immutable identity plus one in-scope Evidence Pack. Its identity guard rejects changes to those relations or replacement of the final normative oracle.

If an action is actually an independent variant, report `INDEPENDENT_BRANCH_DETECTED` to the main authority. Do not split or merge frozen tests. One bounded feedback pass may append a new independently justified Scenario and TC without modifying the existing suite.

## Procedural Model

Represent supported actions internally with only the detail available from selected evidence:

- action and target;
- input from local test data;
- dependency on the preceding state;
- supported intermediate observation;
- evidence source for that observation.

Preconditions describe the starting state and Test Data supplies values; neither is a substitute for executable actions. After the first action, each action retained in the same TC must depend on state produced by its predecessor. Shared navigation may be copied from one cached Evidence Pack into several cases, but branching cases keep their independent identities.

## Authority Boundary

Functional authority owns the final Expected Result. Technical context, implementation evidence, QA assets, and procedural manuals may support navigation, inputs, intermediate checkpoints, and observability. They never replace the normative result.

An intermediate Expected Result is emitted only with selected evidence. When an intermediate checkpoint is required but unsupported, use `expected_result: null`, set `needs_clarification: true`, and link the resulting review state to the existing Question mechanism. Never invent a modal, field, message, route, or visual state.

## Natural Granularity

Use one meaningful operational action per Step. Split a documented sequence such as navigation, search, selection, input, trigger, and observation when each action advances the procedural state. Do not split pointer movement, focus changes, or individual keystrokes without test value.

One Step remains correct when one supported action reaches the result from established preconditions, such as sending one malformed request and observing its response. There is no minimum Step count.

The advisory step audit flags a summary action when it contains several operational verbs or independent variants. It never rewrites the case and does not act as a quality score.
