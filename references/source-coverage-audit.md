# Per-Requirement Source Coverage Audit

Read this after the candidate Test Case suite exists and before finalization. This is distinct from the clause-to-Coverage-Point audit: reconsult each selected normative source from the source outward, not from generated clauses backward.

For each RF/RN/requirement, preserve a Source Item with its requirement owner, source refs, and faithful source text. Run the executable atomicity review before Clause creation. Identify every independently observable normative claim, including bullets, acceptance criteria, alternatives, exceptions, transitions, restrictions, side effects, messages, audit records, and distinct search/filter dimensions. A bullet or sentence is not automatically one claim. Split observable `and` outcomes, `or` alternatives, and enumerated effects when one can be wrong while another remains correct. Do not split inseparable representations merely because punctuation or a connector exists.

Every Source Item records one decision:

```text
SPLIT -> two or more atomic claims
KEEP_ATOMIC -> exactly one claim + INSEPARABLE_VALUE |
               INSEPARABLE_RELATION | SINGLE_OBSERVABLE_OUTCOME
```

`SAME_SENTENCE`, `SAME_BULLET`, `SAME_REQUIREMENT`, `SAME_SCREEN`, `SAME_EVENT`, fewer tests, and simpler output are not valid reasons to keep source truth compressed. `SAME_EVENT` may justify a later Scenario merge, never a source-claim merge. Compound detection is a review signal, not a language parser or an automatic splitter. A suspicious source item or residual materialized claim must be split or explicitly kept for a valid semantic reason before Scenario Design.

A claim is not a Test Case count: several claims may share one independently reportable TC when their separate Clause and Coverage Point traceability remains intact. Review materialized clauses/CPs that still appear compound, but treat `POSSIBLE_COMPOUND_NORMATIVE_CLAIM` as a detection signal rather than an automatic rewrite. The executable review decision is the gate; the diagnostic warning alone is not proof of review.

Use `review_source_items`, `materialize_atomic_coverage`, `audit_atomic_chain`, and `audit_materialized_atomicity` from `scripts/source_coverage_audit.py` for the real Source Item -> Claim -> Clause -> CP boundary. The residual audit independently rejects suspicious materialized Claims or Clauses that lack a narrow reviewed disposition. Semantically equivalent claims may share one Clause only through an explicit equivalence key; retain all contributing provenance. Metrics must come from this independent inventory when it exists. Clause-plus-gap counts remain a presentation fallback for legacy outputs and are not valid proof that every source claim was identified.

Compare the fresh source inventory with materialized clauses and classify every claim as represented or as a source coverage gap. Run exactly one bounded recovery pass:

```text
source gap -> clause -> Coverage Point -> scenario -> testability/dedup ->
Test Case | Question | Finding | justified Out of Scope/Not Testable
```

Never create a TC directly from a gap and never loop recovery to manufacture coverage. Verify once after recovery. If a defensible gap remains, preserve it as a `COVERAGE_GAP` finding whose statement starts with `[SOURCE_COVERAGE_GAP]`; do not hide it or report complete source coverage.

The audit is semantic and source-grounded. Do not mechanically create claims for dimensions absent from the source, and do not let execution enrichment redefine requirement normalization, clauses, CPs, scenario identity, TC independence, oracle, status, or disposition unless a pre-existing defect is demonstrated.
