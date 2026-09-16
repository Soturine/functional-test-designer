---
name: designing-functional-tests
description: Designs risk-based functional test plans, manual test cases, regression slices, and automation handoff packs from requirements, URLs, or exploratory notes.
---

# Designing Functional Tests

Turn product intent into tester-ready coverage rather than directly generating automation.

## Core Rules

- Missing behavior becomes a question or an explicit assumption.
- Risk decides depth.
- Keep each case focused on one behavior.
- Use stable scenario and test-case IDs.
- Write observable expected results.

## Workflow

1. Frame the requested plan, manual cases, or regression slice.
2. Confirm the feature, actor, starting state, and observable outcome.
3. Map happy, negative, boundary, permission, recovery, and state coverage according to risk.
4. Prioritize critical business paths before expanding coverage.
5. Produce tester-ready cases using `resources/manual-test-cases-template.md` or a plan using `resources/test-plan-template.md`.
6. Record assumptions and open questions instead of inventing behavior.

## Definition of Done

- Scope and risk are clear.
- Missing information is visible.
- Each scenario or case has a stable ID.
- Another tester can execute the output without a live explanation.

