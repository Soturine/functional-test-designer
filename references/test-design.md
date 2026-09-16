# Contextual Test Design

Read this reference only when ranges, states, interacting conditions, or many combinations justify a formal technique. Techniques improve scenario selection; they do not create extra output structures, multiply Test Cases, or supply missing expected results.

Test Design techniques are reasoning tools, not output multiplication tools. Analyze broadly, then eliminate redundant scenarios, keep coherent observations together, and preserve separate TCs only for behavior, risk, flow, evidence, or Pass/Fail results that are genuinely independent. Prefer a few strong TCs to many nearly identical ones.

## Selection Guide

| Source signal | Technique | Output rule |
| --- | --- | --- |
| Numeric, length, date, or count limit | Boundary Value Analysis and Equivalence Partitioning | Analyze the full neighborhood, then select representative valid and invalid executions without emitting every value. |
| Several conditions determine an outcome | Decision table | Collapse equivalent rules; retain separate TCs for distinct outcomes or evidence. |
| State or workflow controls valid actions | State transition | Cover important valid and invalid transitions as independent cases where they have their own Pass/Fail. |
| Many independent parameters | Pairwise | Select a smaller pair-covering combination set; each selected execution may become an independent TC. |
| Poorly understood or high-risk behavior | Risk-based grilling | Create focused scenarios or Questions without inventing deterministic oracles. |

## Independence Rule

Create another TC when a condition can fail independently, create an independent bug, require separate evidence, or use different setup or oracle. Before adding a step, ask whether it can be executed and evaluated without earlier steps. If it can and owns a verifiable result, it is an independent TC. Use multiple steps only when they form one sequential business flow and later steps depend on state created earlier.

There are no subtests in output. For a legacy QA input, first classify every named subtest: independently executable/reportable variants become separate TCs, while state-dependent actions in one sequential business flow become steps. Steps are actions and observations within the Test Case, not hidden test variations.

## BVA and EP

For an inclusive range 1 through 10, analysis may consider `0, 1, 2, 9, 10, 11`. Do not emit all six automatically. Select values that add meaningful coverage. One result may be four independent cases when each boundary requires separate evidence:

- accept minimum 1;
- accept maximum 10;
- reject below-minimum 0;
- reject above-maximum 11.

Omit 2 and 9 when they prove no behavior beyond the same valid partition. When the source and reporting needs allow one coherent data-driven execution, representative values may instead share one TC's local test data and steps. Do not encode them as `subtests`.

## Pairwise

Use pairwise to reduce a Cartesian product, not to combine independent results into one case. Each selected row can become its own TC when it represents one independent execution. Remove a row only when it adds no unique coverage or risk.

## Coverage and Deduplication

Coverage Points retain every normative behavior even when several points map to one coherent TC. Deduplicate only when behavior, setup, essential action, expected result, oracle, and evidence are all equivalent. Do not merge different permissions, actors, inputs, transitions, bounds, failure modes, recovery paths, or oracles merely to minimize the case count. Deduplication removes duplicates; it does not compress independent Pass/Fail results.

## Guardrails

- A technique may suggest a scenario or Question, never a missing oracle.
- Do not apply every technique mechanically.
- Do not claim exhaustive coverage from pairwise or representative partitions.
- Preserve explicit source examples when they carry business meaning.
