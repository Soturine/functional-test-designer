# Selected-evidence scenario opportunities

After normative atomic coverage and before final candidate design, account for every meaningful observable behavior in all explicitly selected evidence. This audit is bounded by selected-source scope and does not crawl imports, neighboring documentation, or external systems.

Build one structured opportunity record with source role, source refs, observable condition or branch, applicable Requirement/CP refs, authority status, testability, oracle availability, and exactly one disposition:

```text
COVERED_BY_EXISTING_SCENARIO
NEW_NORMATIVE_SCENARIO
DIVERGENCE_SCENARIO
IMPLEMENTATION_CHARACTERIZATION
QUESTION
FINDING
NOT_TESTABLE
OUT_OF_SCOPE
```

Only functional authority can support a normative scenario. Implementation and technical evidence may expose observable branches, execution knowledge, characterization targets, risks, or divergences; they never silently become the normative oracle. A selected QA asset is a challenge set: map supported behavior through the normal pipeline, characterize implementation-only behavior, preserve conflicts as Findings, and keep unsupported behavior explicit.

Every divergence links to normative coverage, a characterization candidate, a focused Question, or a justified non-testable disposition. Keep Expected Result grounded in authority while the Finding records observed implementation.

Consider bounded cross-requirement and E2E opportunities only when selected evidence supports one continuous independently rerunnable execution. Trace its checkpoints to atomic CPs and never use E2E coverage to erase atomic cases or create combinatorial suites.

Use `audit_scenario_opportunities` from `scripts/scenario_opportunities.py` before and after Scenario Cohesion. The first pass validates roles and dispositions; the second validates concrete Scenario, Finding, and Question links.
