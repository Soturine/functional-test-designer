# High-rigor, high-recall design (v2.2)

For the corrective additive layer introduced in v2.2.1, also read [additive-expansion.md](additive-expansion.md).

Establish the complete selected-source universe before claiming coverage. Classify every selected source by authority and family, disposition every referenced authoritative source, then perform the independent structural review and atomic Claim → Clause → Coverage Point gates.

Scenario is an organizational family, not a compression target. Every independently diagnosable candidate remains a canonical atomic Test Case. Shared setup or a shared event may create a merge suggestion for manual review, but `actual_merges` stays zero in the atomic view. E2E cases are explicit compositions and never replace their atomic members.

Classify test intent:

- `ACCEPTANCE`: authoritative normative oracle;
- `CHARACTERIZATION`: observed implementation oracle, with any divergence linked;
- `DERIVED`: defensible invariant or risk reasoning;
- `EXPLORATORY`: useful investigation with no invented exact oracle;
- `REGRESSION`: preserved defect or behavior coverage;
- `E2E`: continuous journey composing atomic Test Cases.

Questions and Findings may coexist with a Test Case. Missing implementation or an execution detail changes execution status, not test-design existence. Only an unresolved normative expected result blocks the oracle, and even then the design record remains visible.

Risk expansion follows selected evidence across state, data, user error, integration, concurrency, recovery, physical/operational, and security dimensions. Do not instantiate a category mechanically. Undefined policy becomes `EXPLORATORY`, `NEEDS_REVIEW`, or a Question; never fabricate a recovery rule.

Overall PASS requires independent schema, cross-file, source-inventory, normative-coverage, oracle-safety, reference-integrity, procedure-quality, and pipeline-provenance gates. Findings, Questions, and blocked execution may coexist with a PASS for test-design quality.
