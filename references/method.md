# The QA method

The runtime is a deterministic shell around your reasoning. It locks scope, reads sources, indexes authority identifiers, validates each stage, and publishes. It never interprets the business: which scenarios exist, how the domain can fail, which mistakes operators make, which contradictions matter and how a tester executes a case are your decisions.

## Reasoning dimensions

Use universal dimensions and fill them with the project's own values:

| Dimension | Ask |
| --- | --- |
| Actor / permission | Who acts? Who must not be able to? |
| Entity / resource | What objects exist and what identifies them? |
| State | Which states and transitions exist; which are forbidden? |
| Operation / input / output | What triggers behavior, with which inputs, producing which observable outputs? |
| Invariant | What must always hold (uniqueness, limits, totals, isolation)? |
| Sequence / event | What order is assumed? What if it changes, repeats or stops midway? |
| Integration / dependency | What outside the system does behavior rely on? |
| Failure surface | What in THIS architecture can fail, duplicate, arrive late or restart? |
| Observable | Where can a tester see that it worked or failed? |

The same method yields "wrong pallet into a storage position" in a logistics project, "wrong component on a work order" in aerospace maintenance, "wrong customer on an invoice" in an ERP and "wrong account in a mobile app". None of these interpretations belongs in the framework.

## Normative design

1. Read authority first; implementation, technical context and test assets enrich how to reach and observe behavior, never what must happen.
2. Inventory structure before summarizing: each identifier, acceptance bullet, rule, flow, pre/postcondition is a unit. Business rules and transversal constraints are units of their own.
3. Split each unit into claims until one claim is one independently diagnosable obligation. Keep an observation together only when it is indivisible (one record, one message with its code).
4. Design one Acceptance test per failure domain with an explicit oracle. Do not compress independent behaviors because they share setup; do not split one indivisible observation to inflate counts.
5. Give every identifier an outcome. Ambiguity becomes a Question; divergence between authority and implementation becomes a Finding linked to the tests it affects.

## Expansion

After the baseline is frozen, go looking for failure. For each dimension record what you considered, not only what you kept. Derived tests need an authority invariant as oracle; characterization tests record current implementation behavior as such; exploratory tests use only safe invariants and ask a Question. Existing tests challenge the suite: each business-relevant test is either semantically covered, promoted, questioned, or explained. They come from explicit `TEST_ASSET` selections and from conventional test files inside selected implementation trees — a facet of the file, never a change of its role, and never authority. E2E journeys compose real atomic stages.

## Procedures

Stage A decided *what* to test; stage B decides *how to execute it*. **Test design decides what must be tested. Procedure generation only explains how to execute it.** Procedures run after identities are frozen: they cannot add, delete, merge, retitle or re-oracle a test.

Write only the detail needed to run the case: real starting context, semantic fixtures with clear properties, one action per step, an observable result per step, cleanup when relevant. Readiness is about material unknowns, not about literal database ids. Automation suitability (how well the case lends itself to automation) and automation readiness (what is still missing to automate it) are different questions.

Write steps the way a good product manual does, for the person who uses the screen rather than the person who maintains the code:

- **Imperative action plus what the tester sees.** "Click **Save**." followed by the visible outcome, not "the save handler runs".
- **Visible labels, quoted exactly as the evidence shows them**, in the language the product displays. Component, template, route or class names appear only on integrator/API steps, where the published contract is the vocabulary.
- **Setup is not action.** Reaching the starting state belongs in preconditions and test data; steps start where the behavior under test starts.
- **Side effects after the confirming action.** Observe what changed (state, balance, record, message) in a step after the one that commits it.
- **Never invent controls.** A menu, button, message, limit or permission that no selected evidence shows becomes an unknown (`MISSING_EXECUTION_SURFACE`, `UNKNOWN_SETUP_PATH`, `MISSING_SELECTOR`) or a Question, never prose.
- **Cite the path.** `evidence_refs` names the source and section each procedure relies on. Evidence is looked up once per section and shared by the family batch, never reread per Test Case.
- **The oracle step observes the designed expected result.** Navigation evidence can add steps; it never changes what the test asserts.

### One procedure for humans and automation agents

There is one canonical procedure, not a human version and a separate AI version. It must work for:

- a tester who has never seen the product;
- an agent that later turns the same Test Case into Playwright, TestSprite, API, Postman, k6 or JMeter automation.

When the evidence supports it, every step communicates:

- **WHO:** the actor, role, session or execution context.
- **WHERE:** the execution surface or subsystem.
- **WHAT:** one atomic action.
- **TARGET:** the resource, entity, device or object acted on.
- **DATA:** the semantic fixture or value.
- **EXPECTED:** the immediate observable result.

This is not a sentence template. Write natural language in the run's locale, for example: *"As USER_ROLE_A, on the order entry surface the evidence documents, select ITEM_A and submit the order for ACCOUNT_A."* → *"The order appears in the documented pending state."*

Whole steps that name no actor, target or observable are rejected. Examples: "access the system", "perform the operation", "validate it", "check if it worked", "continue the flow", "do everything required". When the evidence genuinely cannot resolve the concrete action, keep the known intent and declare `MISSING_EXECUTION_SURFACE` / `UNKNOWN_SETUP_PATH`.

Never invent any of these unless the selected evidence shows them:

- CSS selectors, test ids, button labels, screen names;
- routes, URLs, API endpoints;
- credentials, database columns, device commands;
- messages, timeouts, performance thresholds.

A missing locator is a `MISSING_SELECTOR` unknown: the case stays executable by a human, and automation readiness shows the gap. Use portable semantic fixtures (`OPERATOR_A`, `USER_WITHOUT_PERMISSION`, `ENTITY_ACTIVE_A`, `DEVICE_A`, `ACCOUNT_B`) and describe their properties in `test_data`.

The canonical Test Case stays tool-agnostic and maps naturally to any automation tool:

| Canonical field | Automation concept |
| --- | --- |
| Preconditions | setup / beforeEach / fixtures |
| Test data | fixtures / factories / payloads |
| Step action | UI, API or device operation |
| Step expected result | assertion |
| Postconditions | final-state verification |
| Cleanup | teardown |
| `evidence_refs` | grounding and context for the translator |
| `automation.layer` | likely adapter type |
| Unknowns / blockers | automation gap |

No Playwright selectors, TestSprite syntax or load-tool scripts belong in a canonical Test Case. A load or performance idea without a normative threshold becomes an exploratory characterization scenario plus a Question asking for the acceptance threshold.

### Self-contained at execution time

During generation the selected evidence grounds the procedure. After generation the procedure carries the meaning: a tester or automation agent executing it reads only the Test Case, never the requirements, source code or FTD internals. So each procedure states, when evidence supports it:

- **Resources and fixtures:** who `ACTOR_A` is (role, session, tenant or account), which properties `ENTITY_A` has, how fixtures relate to each other, which device or environment takes part.
- **Starting state:** the state each resource is in before the first step.
- **Steps:** who, where, what, target, data, expected — plus what evidence to collect when the observation is physical or asynchronous (timestamp, device identity, observed identifier, resulting state).
- **Postconditions and cleanup:** the resulting state and how the environment returns to a reusable state.

**One observable outcome per step.** An expected result says what becomes observable — a status, a counter, a state, a message, a record — never only that the request was sent or processed, and never "X or Y": when the policy could go either way, the unknown is declared instead.

**Fixtures are defined where they are used.** Every fixture a procedure names appears in its test data with the same role and properties everywhere in that procedure.

**Controlled conditions are grounded or declared.** Restarting a service, cutting a connection, powering off a device or keeping a tag or label from being read needs evidence that says how (the step is listed in an `evidence_ref`'s `supports`). Otherwise keep the scenario's intent — "a traversal in which the identifier is not captured" — and declare `UNKNOWN_SETUP_PATH` or `MISSING_EXECUTION_SURFACE`; never guess a technique (covering, shielding, distance, orientation, a command). Such a case is honestly not READY. Manual, physical and hardware cases stay in the suite, written for a human.

**Capacity is characterized, not invented.** An expected result asserts a load, latency or capacity number only when the designed Test Case states it. Otherwise separate the *experiment configuration* (a declared, progressively increasing load and the stop rule, in the action or test data) from the *result*: record request count and rate, throughput, latency, errors and timeouts, lost or duplicated operations and integrity failures, and report the observed saturation or degradation point, linking the Question that asks for the threshold.

## Scenario Families and merge candidates

Families organize tests by business area (`family` on each test). They never change a test's identity. Merge candidates are advisory manual-execution groupings computed by the runtime from shared actor/state/trigger or a shared `event`; canonical atomic tests never change.
