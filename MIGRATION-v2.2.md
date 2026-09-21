# Migrating from schema 1.2 to 2.2

Schema 1.2 remains readable and renderable. New generation defaults to schema 2.2; legacy fixtures and callers can explicitly remain on 1.2.

The major semantic change is the Scenario relation. In 1.2, a Scenario is materialized by exactly one Test Case. In 2.2, a Scenario is a family/context and may reference several atomic Test Cases through `test_case_refs`. Sharing setup, navigation, or a business event produces `merge_candidates` metadata and never removes canonical atomic cases.

Every 2.2 Test Case adds:

```text
test_basis
primary_type
secondary_tags
execution_status
question_refs
finding_refs
composes
automation_candidate
automation_layer
automation_tool_hint
deterministic
```

The index adds `source_inventory`, `merge_candidates`, and eight independent `quality_gates`. Questions classify `impact`; Findings may link affected Test Cases and a coverage disposition. E2E cases list the atomic Test Cases they compose.

Status migration is additive: `READY` and `NEEDS_REVIEW` remain; schema 2.2 also distinguishes requirement, implementation, environment, test-data, and external-dependency blockers. A blocked design remains represented.
