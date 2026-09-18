# Central-authority parallel pipeline

Use this reference when several selected sources can be inspected concurrently,
when the user requests a natural inspection order, or when frozen Test Cases can
receive procedural enrichment in parallel.

## Source inspection

The agent interprets the user's ordinary-language request into ordered groups of
selected files. The deterministic engine enforces that normalized plan.

- With no explicit order, place all independent selected sources in one group.
- Sources in one group may be inspected concurrently with one owner per file.
- A later group starts only after every worker in the preceding group completes.
- An instruction file may define the groups but is not product evidence or
  functional authority unless the user separately and explicitly assigns it that role.
- A plan never expands selected scope and inspection order never changes source role
  or normative priority.

Workers return provenance-rich `EvidenceRecord` values. They may identify claims,
navigation, constraints, uncertainty, or possible conflict, but they cannot decide
the final normative oracle, Clause, Coverage Point, Scenario, or Test Case. The main
agent performs semantic reconciliation only after the final evidence barrier.

Use `analyze_selected_sources` for the ordinary one-group case and
`analyze_source_inspection_plan` when ordered groups were requested. Do not expose
these alternatives as user-facing modes.

## Scenario cohesion and freeze

Source Claim, Clause, and Coverage Point atomicity remain unchanged. Test Case
cohesion is evaluated separately at the independently rerunnable execution boundary.
Several Coverage Points may share one Test Case only when they are traceable
assertions observed from the same execution signature and no independent rerun is
required. Different triggers, branches, inputs, partitions, permissions, starting
states, platforms, timing boundaries, or reset requirements remain separate.

Freeze the Test Case identity before procedural work. The frozen identity includes
its objective, material preconditions, test-data partition, assertions, normative
oracle, source lineage, Scenario, Coverage Points, and execution boundary.

## Procedural synthesis

Procedural workers consume immutable identities and selected-source Evidence Packs.
They may add ordered operator actions, supported intermediate observations, concrete
data, contributing provenance, and presentation detail. Prefer visible labels and
verified paths. Do not invent a menu, control, endpoint, credential, or identifier.

Each worker returns exactly one structured result: `PROCEDURE_READY`,
`PROCEDURE_GAP`, `PROCEDURAL_AMBIGUITY`, `DIVERGENCE`,
`INDEPENDENT_BRANCH_DETECTED`, or `UNSUPPORTED_STEP`. A gap or ambiguity preserves
the Test Case and normative oracle, marks unsupported execution honestly, and creates
a minimal Question when needed. A divergence preserves the normative expected result
and records a Finding.

Reject hidden subtests: one action must not compress separately rerunnable variants.
Multiple traceable assertions from a single trigger are not hidden subtests.

## Bounded additive feedback

After all procedural workers finish, the main agent may perform one reconciliation
pass. Existing Test Cases, IDs, Scenario identities, Coverage Points, and normative
oracles are immutable. A sufficiently authoritative independently rerunnable branch
may be appended as a new Scenario and Test Case. Never remove, merge, renumber, or
silently rewrite an existing case, and never recurse into an unbounded feedback loop.
