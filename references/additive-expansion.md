# Additive expansion (v2.2.1)

Inventory authoritative material below the file level. Account separately for requirements, business rules, acceptance criteria, use cases and each main/alternative/exception flow, pre/postconditions, NFRs, security, performance, state transitions, contracts, and authoritative ADR decisions found in selected sources.

Build and freeze the normative Acceptance suite before expansion. Preserve its TC IDs, Requirement/CP lineage, objectives, and normative oracles. Operator Error/Misuse, risk, recovery, concurrency, Characterization, Cross-Requirement, and E2E phases may only append cases or metadata. `BASELINE_PRESERVATION_VALID` fails on removal, renumbering, destructive merge, or oracle mutation.

Every additive opportunity receives exactly one disposition: materialized TC, existing coverage, Characterization, Exploratory, Question, invalid/unsupported, technical-only, duplicate, or out of scope. A supported materialized opportunity needs a profile and Evidence Pack. Undefined policy remains Exploratory with a focused Question and safe invariants only.

Selected Test Assets are a challenge set, never authority. Every business-relevant behavior links to existing coverage, a Derived/Characterization case, a Question, or an explicit rejection. Findings can make setup data unable to reach a target failure domain; retain the Acceptance oracle and mark execution readiness instead of deleting the TC.

Before final validation, verify physical evidence paths against selected scope, semantic E2E composition, Test Data reachability, procedure-template quality, priority distribution, and complete full-run provenance. Pre-orchestrator timing that the host cannot observe must be reported as unavailable, never zero.
