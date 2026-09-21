# Procedural readiness

Human readiness asks whether a newcomer can start from legitimate preconditions, obtain or identify data, follow concrete ordered actions, trigger the behavior, distinguish assertions, and observe the result without guessing documented details.

Automation readiness is a stricter translation audit, not browser execution. Blockers include abstract trigger/navigation, placeholders without deterministic acquisition, missing observation, procedure gaps, hidden subtests, unresolved branches, and ambiguous identity boundaries.

`PATH_COMPRESSION` applies when selected evidence supports several dependent operations but a case hides them in one objective-like action. Do not infer it from step count alone: a genuinely single-action path remains legitimate. Require a supported execution surface when one is material, and use concrete synthetic data or a deterministic acquisition rule instead of labels such as "valid record".

A precondition that names a record is not a way to obtain one. When setup is material, the Evidence Pack declares a strategy and a concrete rule:

```text
SETUP_BY_FIXTURE
SETUP_BY_API
SETUP_BY_UI
REUSE_EXISTING_WITH_QUERY_RULE
PRESEEDED_ENVIRONMENT
```

A generic acquisition rule reads like "select an existing record in state Pending with at least N available units and record its identifier before execution". Never hardcode customer or production identifiers. A missing strategy or rule raises `MISSING_SETUP_ACQUISITION`; a preseeded environment without provenance raises `MISSING_SETUP_PROVENANCE`.

Procedural steps that depend on selected implementation, manual, or technical evidence keep that provenance. Normative refs carry the oracle; procedural refs carry navigation, labels, endpoint behavior, device detail, and setup. An action traceable to no selected source raises `MISSING_PROCEDURAL_PROVENANCE`. All three codes are material, so they also prevent a case from being presented as simply `READY`. Schema `2.2` exposes execution status and automation metadata while acquisition/procedural provenance remains grounded in the Evidence Pack and readiness audit; schema `1.2` remains compatible.

`READY` means semantically valid and executable at the evidence-supported level. A material procedure, surface, data-acquisition, trigger, or observation gap makes the public case `NEEDS_REVIEW`; an unresolved normative oracle remains `BLOCKED`. This status alignment must not mutate frozen TestIdentity or normative coverage.

Readiness is classified after Test identity freeze. Never add steps, merge/split cases, or weaken an oracle merely to improve readiness counts. A dry Automation Plan may contain the boundary, setup, data, ordered actions, assertions, cleanup, blockers, and provenance; do not invent selectors or runner code.
