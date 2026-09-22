# Pipeline integrity (v2.2.2)

The official runtime owns every quality verdict. A generation request may supply
evidence and reviewed semantic inputs, but never final gates, final counts, or a
claim that coverage/provenance passed.

Every run writes `.ftd/runs/<run-id>/run-manifest.json`. Its ordered records cover
source selection and accounting, source units, Claims, Clauses, Coverage Points,
the frozen normative baseline, additive reviews, Scenario/E2E composition,
procedure, validation, rendering, and publication. Each record carries input and
output IDs/digests, timestamps, generator/stage versions, and a hash-chain link.
The manifest is bound to the private canonical suite and to the exact published
file hashes. Missing, reordered, modified, or manually replaced artifacts fail the
official integrity validator.

Schema 2.2 runs also enforce:

- exactly one Acceptance TC per testable atomic CP, unless an explicit
  `INDIVISIBLE_CONTRACT` records the shared failure domain and claim IDs;
- an observable Claim→CP→TC→Step/assertion map, with specific evidence for
  performance, device, authorization, concurrency, and idempotency tests;
- configurable identifier accounting below file level;
- observable use-case-flow dispositions and semantic E2E stage maps;
- runtime-derived automation readiness with a blocker whenever it is false;
- evidence-backed priority reasons and visible distribution warnings;
- exact Scenario Family CP membership and advisory-only merge candidates.

Diagnostics materialize privacy-safe physical-source, source-identifier,
Claim-exercise, and Test Asset challenge artifacts. Host timing that is not
observable remains unavailable; engine timing is measured by the runtime.
