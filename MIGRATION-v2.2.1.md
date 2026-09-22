# Migrating from v2.2.0 to v2.2.1

The public output schema remains `2.2`; schema `1.2` compatibility is unchanged. The shared generation request is stricter: schema 2.2 runs must provide below-file `source_units` plus independently produced `source_unit_expectations`, and every evidence-supported risk must have an additive disposition. Selected Test Assets use explicit challenge-set dispositions when present.

Generation now freezes normative Acceptance identities before additive candidates. Existing normative IDs and oracles therefore remain stable while Derived, Characterization, Exploratory, and E2E cases are appended. Quality-gate consumers must accept the eight new v2.2.1 gates in addition to the original eight.

Newly generated merge candidates include `merge_candidate_id`; older schema 2.2 candidates without it remain valid. They remain advisory and never alter the canonical atomic cases. Diagnostics add source-family, baseline, expansion, evidence, procedure, priority, and full-run timing fields; unavailable host timing is represented as `null`.
