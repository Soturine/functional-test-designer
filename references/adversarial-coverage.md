# Adversarial, resilience and E2E coverage

Atomic Coverage Point coverage does not prove workflow coverage, and a passing happy path does not prove the workflow survives a real operator, device, integration, concurrent process, or environment. These passes are evidence-grounded reviews, never generators.

## Test Assets are a challenge set, never authority

When selected sources include tests, plans, or existing cases, inventory them mechanically rather than hand-picking a recognizable few. `discover_python_test_assets` in `scripts/test_asset_inventory.py` parses the file statically and records test files, classes, functions, statically visible parametrization, docstrings, and high-signal constants. It never imports or executes the inspected code.

Every discovered behavior needs one classification:

```text
BUSINESS_RELEVANT
TECHNICAL_ONLY
DUPLICATE_EXISTING_COVERAGE
IMPLEMENTATION_CHARACTERIZATION
POSSIBLE_MISSING_SCENARIO
OUT_OF_SCOPE_WITH_REASON
```

Do not convert every unit test into a functional Test Case. A `TECHNICAL_ONLY` behavior cannot be promoted at all, and a promoted behavior still requires Functional Authority support. When the ledger declares a selected `TEST_ASSET`, an empty inventory blocks the run.

## Risk review matrix

Ask how the documented workflow can fail, then keep only what the selected evidence supports. Dimensions reviewed:

```text
actor · authorization · object_identity · starting_state · value_boundary
sequence_order · duplicate_replay · concurrency · integration · device
location · time_timeout · interruption_recovery · cross_account_tenant
unexpected_object
```

This is a review matrix, not one Test Case per dimension. Only material, evidence-supported combinations become candidates, and risk must never suppress valid canonical coverage to reduce suite size.

Each risk condition declares its class and its evidence:

```text
operator mistakes      NEGATIVE · MISUSE · OPERATOR_ERROR · ADVERSARIAL_OPERATIONAL · SECURITY
runtime disruption     RESILIENCE · FAULT_INJECTION · RECOVERY
other                  CONCURRENCY · DATA_INTEGRITY
flow                   E2E · CROSS_CUTTING
```

There is no separate public object for these. Every accepted scenario is an ordinary Test Case that travels the same pipeline: evidence, atomic behavior or characterization candidate, independent execution boundary, frozen identity, procedure.

## Never invent the expected behavior

Each condition declares `oracle_support`:

```text
NORMATIVE          Functional Authority defines the expected invariant
CHARACTERIZATION   the behavior is observable but has no normative owner
UNDEFINED          the selected evidence does not define what should happen
```

`UNDEFINED` cannot become a normative scenario. It becomes a characterization candidate or a Question, and a characterization candidate must link a focused Question. A `NORMATIVE` condition promoted to a new scenario still needs `normative_support_refs`. When there is no normative owner, do not fake Requirement traceability: use characterization or risk provenance and mark `NEEDS_REVIEW` where the oracle is incomplete.

## E2E and cross-requirement review

Documented main, alternative, and exception flows are each reviewed on their own. An alternative flow is never assumed to be covered by the main flow. Every flow gets one disposition:

```text
E2E_SCENARIO
COVERED_BY_ATOMIC_SCENARIOS
QUESTION
NOT_TESTABLE
OUT_OF_SCOPE
```

An `E2E_SCENARIO` must be one continuous independently rerunnable execution whose checkpoints trace to at least two atomic Coverage Points. Atomic tests localize defects; E2E tests give workflow confidence. Neither replaces the other, and E2E coverage never erases atomic cases or creates combinatorial suites.

Use `audit_risk_matrix` and `audit_flow_coverage` from `scripts/risk_coverage.py` together with [scenario-opportunities.md](scenario-opportunities.md).

## Operational scenario catalog

`operational-scenarios.md` is an optional deterministic projection of canonical state. It is a review catalog, not a second Test Case model: each family links Test Cases that already exist, and any detail the selected evidence does not supply is shown as unsupported rather than invented. See [output-selection.md](output-selection.md).

## Organizational views without duplication

One canonical Test Case can appear in a requirement-backed suite and in a risk-oriented static suite. `build_suite_mapping` in `scripts/azure_devops_adapter.py` maps memberships from existing tags without cloning the semantic Test Case and without changing schema `1.2`.
