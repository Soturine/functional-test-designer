# Functional Test Designer v2.2.1 — Corrective Additive Expansion Round

Work directly on the current `develop` branch of `Soturine/functional-test-designer`.

## Release baseline

Treat **v2.2.0** as the new stable baseline.

Do **not** redesign or weaken the parts that worked.

The MAG v2.2.0 benchmark established the baseline behavior that must be preserved:

- 143 normative atomic Acceptance TCs;
- 1 E2E;
- 144 total TCs;
- no destructive scenario merge;
- `actual_merges = 0`;
- Findings/Questions/implementation gaps do not delete normative TCs;
- normative requirement remains the Acceptance oracle;
- Scenario is a family/container, not a compression mechanism;
- canonical atomic view is preserved;
- pipeline ends at `VALIDATED`;
- no project-specific ad-hoc generator.

The purpose of v2.2.1 is **not** to redesign the v2.2 architecture.

The purpose is to fix the gaps exposed by the real MAG benchmark using **additive, regression-safe changes**.

---

# 1. Golden rule: preserve the normative baseline first

The normative atomic suite must be generated and frozen **before** any derived expansion.

Required order:

```text
Source Inventory
→ Normative Source Extraction
→ Atomic Claims
→ Clauses
→ Coverage Points
→ Normative Atomic Acceptance TCs
→ FREEZE BASELINE
→ Test Asset Challenge Set
→ Operator Error / Misuse Expansion
→ Risk / Chaos / Recovery / Concurrency Expansion
→ Characterization Expansion
→ Cross-Requirement Expansion
→ E2E Composition
→ Merge Candidate Discovery
→ Procedure Refinement
→ Final Validation
```

All post-baseline phases are **additive**.

They may:
- add TCs;
- add Findings;
- add Questions;
- add metadata;
- add links;
- add Scenario Families;
- add E2Es;
- add merge suggestions.

They must **not**:
- remove a normative TC;
- merge away a normative TC;
- replace a normative TC;
- change a normative Acceptance oracle;
- reduce normative atomic coverage.

Add a mandatory quality gate:

```text
BASELINE_PRESERVATION_VALID
```

It must prove:

```text
normative_atomic_before_expansion == normative_atomic_after_expansion
removed_normative_tests == 0
merged_away_normative_tests == 0
changed_normative_oracles == 0
```

If this fails, the run fails.

For the MAG regression benchmark, the known v2.2.0 baseline is 143 normative atomic Acceptance TCs. Do not hardcode 143 into generic production logic, but use the historical benchmark to detect regressions.

---

# 2. Do not optimize for a target TC count

Do not force:
- 145;
- 166;
- 200;
- 107;
- or any other number.

However, v2.2.1 must no longer allow a rigorous analysis to discover new meaningful behavior and then fail to materialize it.

Derived expansion must be additive.

If the run finds:
- operator-error opportunities;
- risk conditions;
- existing business-relevant test behaviors;
- characterization opportunities;
- E2E journeys;
- cross-requirement interactions;

then each must receive an explicit disposition.

Allowed dispositions:

```text
MATERIALIZED_AS_TC
ALREADY_COVERED_BY
CHARACTERIZATION_TC
EXPLORATORY_TC
QUESTION_REQUIRED
INVALID_OR_UNSUPPORTED
TECHNICAL_ONLY
DUPLICATE
OUT_OF_SCOPE
```

No silent dropping.

---

# 3. Fix source completeness without changing atomic generation

The v2.2.0 MAG benchmark preserved atomicity well, but the normative universe was still incomplete.

The source inventory must explicitly account for normative families, not only high-level selected roots.

For requirement documents, inventory must be capable of representing:

- RFs;
- RNs / business rules;
- acceptance criteria;
- use cases;
- main flows;
- alternative flows;
- exception flows;
- preconditions;
- postconditions;
- NFRs;
- performance constraints;
- security requirements;
- state-transition rules;
- integration contracts;
- ADR decisions where authoritative.

Do not treat:

```text
PDF = one inventory item
```

as sufficient proof of normative completeness.

A high-level selected source may contain many independently authoritative normative units.

Add explicit source-unit accounting:

```text
normative_sections_discovered
business_rules_discovered
use_cases_discovered
main_flows_discovered
alternative_flows_discovered
exception_flows_discovered
nfrs_discovered
security_constraints_discovered
performance_constraints_discovered
```

The source-completeness gate must fail if an authoritative family exists but was never dispositioned.

Do not alter the good atomic Claim → CP → TC behavior after those units are discovered.

---

# 4. Fix Use Case flow extraction

The MAG run incorrectly reduced use-case coverage to a small set of generic flow records.

A use case may contain:
- a main flow;
- multiple alternative flows;
- exception flows;
- preconditions;
- postconditions.

Each relevant flow must be independently inventoried and dispositioned.

Do not classify one entire CU only as `MAIN_FLOW`, `ALTERNATIVE_FLOW`, or `EXCEPTION_FLOW`.

A single CU may contribute several flow records.

Add validation:

```text
USE_CASE_FLOW_ACCOUNTING_VALID
```

It should compare extracted flows against the source structure and prevent `unaccounted_use_case_flows = 0` when the initial flow inventory is incomplete.

---

# 5. Make Risk Expansion actually materialize tests

In the MAG v2.2.0 benchmark the system discovered risk conditions but produced:

```text
derived_tests = 0
exploratory_tests = 0
operational_scenario_families = 0
```

Fix this.

Risk discovery and risk materialization must be separate, measurable stages:

```text
risk_candidates_discovered
risk_candidates_supported
risk_candidates_materialized
risk_candidates_already_covered
risk_candidates_exploratory
risk_candidates_rejected
risk_candidates_unresolved
```

Every supported risk candidate must receive a disposition.

No random chaos.

Use project evidence and system invariants.

Relevant categories include:

```text
NEGATIVE
OPERATOR_ERROR
MISUSE
CONCURRENCY
RACE_CONDITION
IDEMPOTENCY
RESILIENCE
RECOVERY
CHAOS
SECURITY
AUTHORIZATION
DATA_INTEGRITY
INTEGRATION
FIELD
HARDWARE_INTEGRATION
```

---

# 6. Add explicit Operator Error / Misuse Expansion

This must be a dedicated post-baseline phase.

The goal is to model realistic human operational mistakes, not only invalid form inputs.

Systematically ask:

```text
What if the operator uses the wrong resource?
What if two resources are inverted?
What if the operator performs the correct actions in the wrong order?
What if an action is repeated?
What if an action is omitted?
What if the physical action differs from the digital action?
What if the operator uses a stale document/session?
What if the operator crosses document/account/context boundaries?
What if the operator abandons an operation halfway through?
```

Generic misuse dimensions:

- wrong resource;
- wrong association;
- swapped resources;
- wrong sequence;
- repeated action;
- omitted action;
- stale operation;
- partial operation;
- cross-document mistake;
- cross-account mistake;
- physical/digital mismatch;
- accidental reversal;
- acknowledgement of wrong alert;
- duplicated manual fallback after automatic processing.

For a RFID/logistics domain, evidence may justify scenarios such as:

- correct box through wrong portal;
- wrong box through correct portal;
- boxes swapped between two outbound orders;
- barcode of Box A read while Box B physically moves;
- portal A/B selected in reverse;
- manual barcode read after RFID already processed the same box;
- same box repeatedly passed;
- operator abandons an outbound still in progress;
- wrong alert acknowledged;
- ineligible category used for direct transfer;
- physically incorrect return path.

Do not hardcode MAG-specific names into the framework.

Generalize these as misuse patterns.

---

# 7. Add real Chaos / Recovery expansion after baseline

Chaos and recovery must be additive and evidence-based.

Possible generic failure surfaces:

- middleware unavailable;
- network loss;
- process restart;
- backend restart;
- reader/device restart;
- response lost after successful commit;
- retry after timeout;
- duplicate delivery;
- out-of-order delivery;
- partial batch;
- shared cache unavailable;
- multi-worker race;
- concurrent resource claim;
- client/browser session loss;
- infrastructure interruption during an in-progress business operation.

When policy is defined, generate a test with the normative/derived oracle.

When exact business policy is not defined, generate an `EXPLORATORY` or `NEEDS_POLICY` test using safe invariants only, such as:

- no silent corruption;
- no duplicate business event;
- no unauthorized transition;
- operation remains traceable;
- partial failure is surfaced;
- state can be reconciled;
- already committed action is not silently repeated.

Do not invent recovery policy.

---

# 8. Make the existing-test challenge set useful

The MAG run discovered 668 existing test behaviors, including many potentially business-relevant behaviors, but promoted none.

Do not convert all existing tests into generated TCs.

Instead, existing tests are a **challenge set**.

For every discovered existing test behavior:

1. classify it;
2. normalize its behavioral intent;
3. compare it semantically with generated coverage;
4. disposition it.

Suggested classifications:

```text
TECHNICAL_ONLY
BUSINESS_RELEVANT
NORMATIVE_CONFIRMATION
CHARACTERIZATION_CANDIDATE
DERIVED_SCENARIO_CANDIDATE
SECURITY_CANDIDATE
CONCURRENCY_CANDIDATE
RECOVERY_CANDIDATE
DUPLICATE
```

For every `BUSINESS_RELEVANT` item, require one of:

```text
ALREADY_COVERED_BY <TC>
MATERIALIZED_AS_DERIVED_TC
MATERIALIZED_AS_CHARACTERIZATION_TC
QUESTION_REQUIRED
INVALID_OR_OUT_OF_SCOPE
```

Do not allow:

```text
business_relevant > 0
promoted = 0
possible_missing_scenarios = 0
```

without explicit evidence proving every item was already covered or invalid.

Add metrics:

```text
test_asset_behaviors_total
test_asset_business_relevant
test_asset_already_covered
test_asset_promoted_to_derived
test_asset_promoted_to_characterization
test_asset_questions
test_asset_rejected
test_asset_unresolved
```

---

# 9. Characterization must materialize when useful

v2.2.0 correctly separated Acceptance from current implementation behavior conceptually, but the MAG output produced zero Characterization TCs.

Fix materialization.

When a meaningful implementation behavior differs from the normative oracle:

- keep Acceptance TC unchanged;
- create/link Finding;
- create Characterization TC when preserving/documenting current behavior is useful.

Example pattern:

```text
Acceptance:
32-char identifier must be accepted according to requirement.

Finding:
implementation currently validates 24 chars.

Characterization:
24-char identifier is accepted by current implementation.
```

Do not create Characterization noise for every implementation detail.

Use it for behavior that matters to regression, migration, defect reproduction, legacy compatibility, or diagnosis.

---

# 10. Findings regression: preserve critical analysis quality

The MAG v2.2.0 run found fewer divergences than an earlier critical benchmark over equivalent evidence.

Do not optimize for a target number of Findings.

Instead improve cross-source contradiction detection.

Explicitly compare:

```text
normative requirement
vs user documentation
vs code
vs configuration
vs existing tests
```

Look for:

- different constants;
- different state transitions;
- timing differences;
- actor/permission mismatches;
- different data models;
- different defaults;
- undocumented implementation exceptions;
- implementation behavior broader/narrower than requirement;
- configuration overriding requirement.

Every candidate contradiction must be:
- confirmed and emitted as Finding;
- explained as non-conflict;
- or marked unresolved.

Do not silently ignore it.

---

# 11. Propagate Findings into test-data readiness

A known implementation divergence may invalidate the test data of unrelated TCs.

Example pattern:

```text
Requirement expects identifier format A.
Implementation currently only accepts format B.
Many TCs use format A merely as setup data.
```

Those TCs may never reach their intended behavior.

Add a post-Finding validation phase:

```text
TEST_DATA_REACHABILITY_VALID
```

For every TC, ask:

> Can this test data reach the failure domain the TC intends to exercise under the observed implementation?

If not:
- do not change the normative oracle;
- mark execution readiness appropriately;
- attach the Finding;
- provide alternate characterization fixture if useful;
- do not falsely mark as READY.

This must not delete the normative TC.

---

# 12. Improve Scenario Families without changing TCs

Scenario Families must be semantically meaningful contexts, not merely one family per RF.

Do not merge or remove tests.

Allow one requirement to produce multiple Scenario Families based on behavior context.

Example generic decomposition:

```text
RFID Requirement
├── Identification
├── Routing
├── Free-resource return
├── Wrong-resource handling
├── Deduplication
├── Authentication/isolation
└── Failure/recovery
```

Scenario reorganization must only change grouping metadata.

Add regression tests proving that Scenario Family refinement leaves canonical atomic TC IDs and normative oracles unchanged.

---

# 13. Merge Candidates must work, but remain advisory

Keep:

```text
actual_merges = 0
```

for canonical atomic output.

However, identify legitimate manual-execution merge candidates.

Good candidates share:
- the same business event;
- the same persisted object;
- the same setup;
- strongly related observations.

Examples:
- multiple mandatory fields of one audit event;
- multiple fields of one alert object;
- acknowledgement user + acknowledgement timestamp.

A merge candidate must never delete atomic tests.

Expose:

```text
merge_candidate_id
test_case_ids
reason
shared_business_event
manual_execution_benefit
automation_tradeoff
confidence
```

Render them visually in HTML.

---

# 14. Expand E2E composition

One generic E2E is insufficient when multiple business journeys are independently important.

Generate E2Es after the atomic baseline.

E2E must compose atomic TCs, never replace them.

Candidate journeys should be derived from:
- use cases;
- state models;
- cross-requirement workflows;
- operational process chains.

Examples of generic journeys:

```text
reservation → fulfillment → dispatch
return → inspection/cleaning → storage
wrong-resource event → alert → acknowledgement → completion
direct transfer between contexts
manual contingency
direct return → inbound synchronization
```

Every E2E `composes` reference must be semantically validated, not only syntactically present.

Add:

```text
SEMANTIC_COMPOSITION_VALID
```

A referenced atomic TC must actually represent a meaningful checkpoint in the E2E journey.

---

# 15. Improve evidence reference validation

The MAG benchmark contained evidence paths that did not physically exist.

Reference integrity must include two levels:

```text
INTERNAL_REFERENCE_INTEGRITY
EVIDENCE_REFERENCE_INTEGRITY
```

Validate:
- TC/CP/Question/Finding IDs;
- file path existence;
- line/range existence where applicable;
- source belongs to selected scope;
- evidence type matches the claimed evidence;
- stale/renamed paths are rejected.

Do not report `REFERENCE_INTEGRITY_VALID = PASS` if external evidence paths are invalid.

---

# 16. Improve semantic reference integrity

A syntactically valid link may still be semantically wrong.

Examples:
- E2E composes an unrelated atomic TC;
- Question points to the wrong TC;
- Finding links to a TC that does not exercise the conflicting behavior.

Add semantic checks where enough evidence exists.

Metrics:

```text
syntactic_reference_errors
evidence_path_errors
semantic_reference_warnings
semantic_reference_errors
```

---

# 17. Improve procedure generation without touching test identity

Do not modify the already-good atomic identity layer to improve procedures.

Procedure refinement happens after test design is frozen.

The MAG output had 3+ steps per TC but still used highly repeated boilerplate.

Improve the procedure-quality detector.

Detect repeated generic phrases such as:

```text
"The surface and test record are displayed according to the documented initial state."
"Open the record and confirm the initial state."
"Observe the result."
```

Metrics:

```text
unique_action_ratio
unique_expected_result_ratio
repeated_action_template_ratio
repeated_expected_template_ratio
generic_setup_step_count
claim_copied_verbatim_as_oracle_count
```

A test can share setup instructions, but the procedure should still help a human execute it.

Prefer:
- concrete object;
- concrete state;
- concrete action;
- concrete observable checkpoint.

Do not invent UI labels, routes or IDs unsupported by evidence.

---

# 18. Improve priority calibration

The MAG output flattened almost all tests to MEDIUM.

Add priority reasoning based on impact/risk, not test type alone.

Consider:
- business-flow blocking;
- integrity corruption;
- security/authorization;
- irreversible state;
- cross-account leakage;
- financial/inventory impact;
- auditability;
- concurrency/race impact;
- recovery impact;
- core happy path;
- supporting UI detail.

Do not imitate historical manual priorities blindly.

Add distribution diagnostics so pathological flattening is visible:

```text
priority_distribution
priority_entropy
critical_ratio
high_ratio
medium_ratio
low_ratio
priority_flattening_warning
```

---

# 19. Close the semantic-preprocessing provenance gap

v2.2.0 improved provenance inside the official orchestrator, but substantial semantic preprocessing still happened before the orchestrator received the generation request.

The user experienced ~46 minutes of work while the official pipeline timing covered only a small final portion.

Do not forbid model reasoning or source reading.

Instead represent preprocessing as official stages.

Required full-run provenance:

```text
SOURCE_SELECTION
SOURCE_READING
SOURCE_STRUCTURAL_INDEXING
NORMATIVE_UNIT_EXTRACTION
IMPLEMENTATION_EVIDENCE_EXTRACTION
TEST_ASSET_EXTRACTION
REQUEST_ASSEMBLY
ORCHESTRATOR_EXECUTION
EXPANSION
PROCEDURE_REFINEMENT
VALIDATION
RENDERING
```

Every stage must expose:
- start;
- end;
- duration when available;
- inputs;
- outputs;
- status;
- provenance.

The final diagnostics must distinguish:

```text
user_perceived_wall_time
source_analysis_time
request_assembly_time
official_pipeline_time
render_validation_time
```

If agent/source-reading timing is unavailable, say unavailable; do not invent values.

The pipeline must not claim a 4-second end-to-end run when the user actually waited ~46 minutes.

---

# 20. Do not optimize source reading in this round

Do **not** introduce aggressive source pruning, progressive deep-reading heuristics, or file-skipping optimizations in v2.2.1.

Quality/recall is more important than speed for this corrective round.

Performance optimization of source reading must be a separate future experiment with A/B regression proof.

Do not change source-selection breadth merely to improve runtime.

---

# 21. Fix renderer issues

Fix report defects without changing test semantics.

Examples exposed by MAG:
- valid requirement titles rendered as “Sem título extraído”;
- Cross-RF count shown as zero when cross-cutting opportunity exists;
- encoding corruption such as `?` replacing accented characters;
- superseded/intermediate runs not clearly marked.

Add renderer tests for:
- UTF-8/Portuguese text;
- requirement title extraction;
- Cross-RF counters;
- Scenario Family counters;
- Derived/Characterization/Exploratory counters;
- Merge Candidates;
- Operator Error;
- Chaos/Recovery;
- baseline vs additive layers.

---

# 22. Run-state hygiene

If a failed/intermediate run is retained, mark it explicitly:

```text
FAILED
SUPERSEDED
ABORTED
```

Do not leave multiple different runs as `VALIDATED` when only one is the published output for that benchmark attempt.

Public output should point to one canonical successful run.

---

# 23. New required metrics

Add at least:

## Baseline
```text
normative_atomic_before_expansion
normative_atomic_after_expansion
baseline_preserved
```

## Source completeness
```text
normative_sections_discovered
business_rules_discovered
use_cases_discovered
main_flows_discovered
alternative_flows_discovered
exception_flows_discovered
nfrs_discovered
```

## Expansion
```text
operator_error_candidates
operator_error_tests
risk_candidates_discovered
risk_candidates_materialized
chaos_tests
recovery_tests
concurrency_tests
resilience_tests
security_derived_tests
exploratory_tests
```

## Existing tests
```text
test_asset_business_relevant
test_asset_already_covered
test_asset_promoted_to_derived
test_asset_promoted_to_characterization
test_asset_unresolved
```

## Characterization
```text
characterization_candidates
characterization_tests
```

## E2E
```text
e2e_candidates
e2e_tests
semantic_composition_errors
```

## Procedures
```text
repeated_action_template_ratio
repeated_expected_template_ratio
unique_action_ratio
unique_expected_result_ratio
```

## Evidence
```text
invalid_evidence_paths
semantic_reference_errors
semantic_reference_warnings
```

## Timing
```text
user_perceived_wall_time
source_analysis_time
request_assembly_time
official_pipeline_time
render_validation_time
```

---

# 24. New quality gates

Add or strengthen:

```text
BASELINE_PRESERVATION_VALID
NORMATIVE_SOURCE_FAMILIES_COMPLETE
USE_CASE_FLOW_ACCOUNTING_VALID
RISK_DISPOSITION_COMPLETE
TEST_ASSET_CHALLENGE_VALID
TEST_DATA_REACHABILITY_VALID
EVIDENCE_REFERENCE_INTEGRITY_VALID
SEMANTIC_COMPOSITION_VALID
```

Keep all existing v2.2.0 gates.

Do not weaken existing gates to make the benchmark pass.

---

# 25. Regression tests/evals to add

At minimum:

1. Post-baseline expansion cannot remove a normative TC.
2. Post-baseline expansion cannot change normative oracle.
3. Operator Error candidate materializes as Derived TC.
4. Wrong-resource / swapped-resource patterns remain separate from normative TC.
5. Chaos candidate with known invariant materializes.
6. Chaos candidate with unknown policy becomes Exploratory.
7. Existing business-relevant test already covered links to existing TC.
8. Existing business-relevant uncovered test behavior becomes Derived/Characterization candidate.
9. Existing `TECHNICAL_ONLY` behavior is not promoted without reason.
10. Divergence can create Characterization while preserving Acceptance.
11. Finding can mark unrelated fixture as unable to reach intended failure domain.
12. Multiple flows from one CU are inventoried separately.
13. Alternative flow cannot disappear because main flow exists.
14. Scenario Family regrouping does not change atomic TC count.
15. Merge Candidate never removes canonical atomic tests.
16. E2E composition rejects semantically unrelated TCs.
17. Invalid evidence file path fails evidence-reference gate.
18. Repeated generic procedure templates trigger warning/failure threshold.
19. Priority flattening is detected.
20. UTF-8 Portuguese rendering remains intact.
21. Requirement title renders correctly.
22. Cross-RF report count reflects actual cross-cutting data.
23. Superseded run cannot remain the canonical published run.
24. Full-run timing distinguishes source analysis from orchestrator timing.
25. No source-reading optimization is introduced in this corrective release.

---

# 26. MAG regression benchmark

Use the same MAG corpus and scope as the v2.2.0 benchmark for direct comparability when available.

Do not change the selected evidence just to improve metrics.

The v2.2.0 reference result is:

```text
143 normative atomic Acceptance TCs
1 E2E
144 total
```

The next result does **not** need to exceed any fixed count.

However:

- the normative atomic baseline must be preserved unless a source-accounting correction proves a previous normative TC invalid;
- any baseline reduction must be reconciled explicitly, case by case;
- Questions, Findings, implementation gaps, Scenario grouping, shared setup and shared execution path are not valid reasons to remove normative TCs;
- new source units discovered from RN/CU/alternate-flow completeness may legitimately increase the normative baseline;
- Operator Error, Risk, Chaos, Characterization, Cross-RF and E2E must be additive.

The benchmark report must explicitly compare:

```text
v2.2.0 normative baseline
v2.2.1 normative baseline
added source-completeness tests
added operator-error tests
added risk/chaos/recovery tests
added characterization tests
added E2Es
merge candidates
findings
questions
```

Also reconcile against:
- the manual 107-TC MAG suite;
- the historical 166-TC benchmark;
- the v2.1.2 critical benchmark;
- other available historical outputs.

Do not rank by raw TC count.

---

# 27. Do not regress these v2.2.0 properties

Treat these as protected invariants:

```text
Atomic normative TC identity
No destructive scenario merging
Scenario Family semantics
Findings do not delete TCs
Questions do not delete TCs
Missing implementation does not delete TCs
Acceptance oracle remains normative
Acceptance != Characterization
E2E does not replace atomics
Canonical atomic output remains available
actual_merges = 0 in canonical atomic view
Schema 1.2 compatibility
Official orchestrator/checkpoints
No project-specific ad-hoc generator
Deterministic validation
```

Any change touching one of these areas requires explicit regression tests proving preservation.

---

# 28. Implementation strategy

Work incrementally.

Recommended sequence:

1. Snapshot current v2.2.0 behavior.
2. Add baseline-preservation gate.
3. Fix source-family completeness.
4. Fix CU flow accounting.
5. Fix risk disposition/materialization.
6. Add Operator Error/Misuse expansion.
7. Fix existing-test challenge-set disposition.
8. Materialize Characterization candidates.
9. Improve Findings contradiction pass.
10. Add test-data reachability.
11. Refine Scenario Families only as metadata.
12. Add advisory Merge Candidates.
13. Expand E2E composition.
14. Add evidence-path validation.
15. Add semantic composition validation.
16. Improve procedure-quality checks.
17. Improve priority calibration.
18. Extend provenance to preprocessing/wall time.
19. Fix renderer/encoding/run-state defects.
20. Add tests/evals after each behavior change.
21. Run complete regression suite.
22. Run synthetic benchmarks.
23. Run MAG benchmark.
24. Compare against v2.2.0.
25. Fix regressions.
26. Update docs/CHANGELOG/version only after behavior is proven.

Avoid broad refactors.

Prefer small changes with tests.

---

# 29. Versioning

Target this corrective release as:

```text
v2.2.1
```

unless implementation reveals a necessary incompatible public-contract change.

Do not bump to v2.3.0 merely because the benchmark generates more tests.

The intended change is additive/corrective over the v2.2 architecture.

---

# 30. Final report

At completion provide:

- starting commit;
- final commit;
- files changed;
- commits created;
- tests/evals added;
- all test results;
- quality gate results;
- v2.2.0 baseline-preservation proof;
- source-family completeness metrics;
- CU flow metrics;
- Operator Error metrics/examples;
- Risk/Chaos/Recovery metrics/examples;
- existing-test challenge-set dispositions;
- Characterization metrics/examples;
- Findings comparison;
- E2E composition metrics;
- Merge Candidate examples;
- evidence reference validation;
- procedure-quality metrics;
- priority distribution;
- full user-perceived timing breakdown;
- MAG benchmark comparison;
- reconciliation against manual 107 and historical benchmarks;
- remaining limitations.

Do not claim `0 gaps`, `complete`, or `fully covered` unless the strengthened gates prove it.

---

# Core goal

v2.2.0 is the stable atomic baseline.

v2.2.1 must **add intelligence around it without destabilizing it**.

The desired behavior is:

```text
GOOD NORMATIVE BASELINE
+
MORE COMPLETE SOURCE UNIVERSE
+
OPERATOR ERROR / MISUSE
+
RISK / CHAOS / RECOVERY / CONCURRENCY
+
EXISTING-TEST CHALLENGE SET
+
CHARACTERIZATION
+
CROSS-REQUIREMENT COVERAGE
+
REAL E2E COMPOSITION
+
BETTER PROCEDURES
+
BETTER EVIDENCE VALIDATION
+
HONEST FULL-RUN PROVENANCE
```

while preserving the atomic TCs and normative oracles that v2.2.0 finally got right.
