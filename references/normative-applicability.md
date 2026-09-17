# Applicable RN/CU Audit

Read this when a selected normative source explicitly declares applicable business rules, use cases, or related normative requirements.

Build a run-local applicability map from the declared relationship, for example `RF002 -> RN001, RN003, CU002`. Resolve a referenced item only from the already selected and indexed normative catalog. If it is absent, record the reference as unresolved; do not open another file, follow a link, search a sibling, or invent its content.

For each RF/RN audit, combine its local atomic claims with the claims of explicitly applicable resolved items. Normalize genuine semantic duplicates into one claim with all provenance. Do not infer applicability from proximity, matching vocabulary, or likely domain relationships.

When an applicable item contradicts the owner or another applicable authority, emit a `SOURCE_CONFLICT` Finding with both source refs. Do not silently choose an oracle. Keep unresolved counts and applicable-claim counts in diagnostics only when they were actually observed.
