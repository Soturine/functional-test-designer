# Contextual Test Design

Use a technique only when it reveals meaningful coverage. Techniques shape reasoning; they do not dictate the number of output test cases.

## Selection Guide

| Signal in the source | Technique | Lean output rule |
| --- | --- | --- |
| Numeric, length, date, or count limits | Boundary Value Analysis (BVA) and Equivalence Partitioning (EP) | Cover representative valid/invalid partitions and relevant edges as subtests when the flow and oracle are shared. |
| Several conditions determine one outcome | Decision table | Collapse equivalent rules; create separate cases only for distinct outcomes or risks. |
| Status or workflow controls valid actions | State transition | Cover important valid and invalid transitions; avoid repeating the same transition for cosmetic data changes. |
| Many independent parameters | Pairwise | Generate a minimal pair-covering set, then remove rows that add no unique behavioral coverage. |
| Poorly understood or high-risk area | Risk-based exploratory scenarios | Add focused charters or questions; do not invent deterministic expected results. |

## Consolidation Examples

A documented valid range of 18 through 65 may be analyzed with `17, 18, 19, 64, 65, 66`. It does not require six test cases. A lean result may be:

- one valid-values case with subtests for 18 and 65;
- one invalid-values case with subtests for 17 and 66.

Omit 19 and 64 when they prove no behavior beyond the same valid partition. Add them only when a distinct risk or rule justifies them.

For pairwise, treat each generated row as a candidate data variation. Group rows under one case when the setup, action, and oracle are the same. Split only when a row exercises a distinct permission, workflow, failure, or expected behavior.

## Guardrails

- A technique may suggest a question or scenario, but never supplies a missing oracle.
- Do not mechanically apply every technique to every feature.
- Do not claim exhaustive coverage from pairwise or representative partitions.
- Preserve explicit source examples when they carry business meaning, even if another value shares the same partition.

