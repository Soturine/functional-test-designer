# Per-Requirement Source Coverage Audit

Read this after the candidate Test Case suite exists and before finalization. This is distinct from the clause-to-Coverage-Point audit: reconsult each selected normative source from the source outward, not from generated clauses backward.

For each RF/RN/requirement, identify every independently observable normative claim, including bullets, acceptance criteria, alternatives, exceptions, transitions, restrictions, side effects, messages, audit records, and distinct search/filter dimensions. A bullet or sentence is not automatically one claim. Split observable `and` outcomes, `or` alternatives, and enumerated effects when one can be wrong while another remains correct. Do not split inseparable representations merely because punctuation or a connector exists.

A claim is not a Test Case count: several claims may share one independently reportable TC when their separate Clause and Coverage Point traceability remains intact. Review materialized clauses/CPs that still appear compound, but treat `POSSIBLE_COMPOUND_NORMATIVE_CLAIM` as an advisory warning rather than an automatic rewrite.

Compare the fresh source inventory with materialized clauses and classify every claim as represented or as a source coverage gap. Run exactly one bounded recovery pass:

```text
source gap -> clause -> Coverage Point -> scenario -> testability/dedup ->
Test Case | Question | Finding | justified Out of Scope/Not Testable
```

Never create a TC directly from a gap and never loop recovery to manufacture coverage. Verify once after recovery. If a defensible gap remains, preserve it as a `COVERAGE_GAP` finding whose statement starts with `[SOURCE_COVERAGE_GAP]`; do not hide it or report complete source coverage.

The audit is semantic and source-grounded. Do not mechanically create claims for dimensions absent from the source, and do not let execution enrichment redefine requirement normalization, clauses, CPs, scenario identity, TC independence, oracle, status, or disposition unless a pre-existing defect is demonstrated.
