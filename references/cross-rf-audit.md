# Cross-Requirement Audit

Run this once after the suite is stable. Compare semantic signatures across RF/RN groups using behavior, setup, essential action, test data, oracle, coverage, evidence roles, and status. Titles alone are not evidence.

Classify observations as:

- `SAME_MULTI_RF_COVERAGE`: one TC legitimately traces to multiple requirements;
- `DUPLICATE_CANDIDATE`: two TCs appear semantically equivalent and require human review;
- `SIMILAR_BUT_DISTINCT`: shared trigger/oracle or surface wording hides a material difference such as boundary, actor, state, permission, evidence, or risk.

This audit is advisory. It never merges, deletes, renumbers, or rewrites a TC. `automatic_merges` and `automatic_removals` must remain zero.
