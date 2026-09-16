# Contextual Test Design

Read this reference only when ranges, states, interacting conditions, or many combinations justify a formal technique. Techniques improve scenario selection; they do not create extra output structures or supply missing expected results.

## Selection Guide

| Source signal | Technique | Output rule |
| --- | --- | --- |
| Numeric, length, date, or count limit | Boundary Value Analysis and Equivalence Partitioning | Select meaningful valid and invalid representatives; give independently reportable boundaries separate TCs. |
| Several conditions determine an outcome | Decision table | Collapse equivalent rules; retain separate TCs for distinct outcomes or evidence. |
| State or workflow controls valid actions | State transition | Cover important valid and invalid transitions as independent cases where they have their own Pass/Fail. |
| Many independent parameters | Pairwise | Select a smaller pair-covering combination set; each selected execution may become an independent TC. |
| Poorly understood or high-risk behavior | Risk-based grilling | Create focused scenarios or Questions without inventing deterministic oracles. |

## Independence Rule

Create another TC when a condition can fail independently, create an independent bug, require separate evidence, or use different setup or oracle. Use multiple steps in one TC when the steps form one coherent business flow.

There are no subtests. Steps are actions and observations within the Test Case, not hidden test variations.

## BVA and EP

For an inclusive range 1 through 10, analysis may consider `0, 1, 2, 9, 10, 11`. Do not emit all six automatically. Select values that add meaningful coverage. A reasonable result can be four independent cases:

- accept minimum 1;
- accept maximum 10;
- reject below-minimum 0;
- reject above-maximum 11.

Omit 2 and 9 when they prove no behavior beyond the same valid partition. Keep the four chosen cases independent because each boundary has its own execution evidence and Pass/Fail.

## Pairwise

Use pairwise to reduce a Cartesian product, not to combine independent results into one case. Each selected row can become its own TC when it represents one independent execution. Remove a row only when it adds no unique coverage or risk.

## Coverage and Deduplication

Coverage Points retain every normative behavior even when several points map to one coherent TC. Deduplicate only semantically equivalent cases. Do not merge different permissions, transitions, bounds, recovery paths, or oracles merely to minimize the case count.

## Guardrails

- A technique may suggest a scenario or Question, never a missing oracle.
- Do not apply every technique mechanically.
- Do not claim exhaustive coverage from pairwise or representative partitions.
- Preserve explicit source examples when they carry business meaning.

