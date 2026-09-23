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

After the baseline is frozen, go looking for failure. For each dimension record what you considered, not only what you kept. Derived tests need an authority invariant as oracle; characterization tests record current implementation behavior as such; exploratory tests use only safe invariants and ask a Question. Existing tests challenge the suite: each business-relevant test is either semantically covered, promoted, questioned, or explained. E2E journeys compose real atomic stages.

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

## Scenario Families and merge candidates

Families organize tests by business area (`family` on each test). They never change a test's identity. Merge candidates are advisory manual-execution groupings computed by the runtime from shared actor/state/trigger or a shared `event`; canonical atomic tests never change.
