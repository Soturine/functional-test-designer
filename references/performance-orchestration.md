# Performance orchestration

Inventory metadata first and selectively read useful in-scope text. Keep binaries metadata-only unless essential. Build a compact run-local evidence map, assign one owner per source, and require a reason for every reread.

Use concurrency only when the runtime actually supports it and tasks have no semantic dependency. Otherwise run serially and record the fallback reason. Respect explicit ordered source groups with barriers; inspection order never changes authority. Procedural workers may run independently only after Test identities are frozen.

Persist privacy-safe checkpoints for resolved scope, evidence barrier, source atomicity, frozen scenarios, procedure, and validation. Hash selected sources and invalidate downstream checkpoints when inputs change. Resume from the last valid checkpoint without persisting source content or secrets.

A validated checkpoint may render requested projections directly from matching canonical state. Record created, resumed, and invalidated events with reasons. If an intermediate checkpoint lacks sufficient structured payload for honest continuation, invalidate it instead of pretending to resume.

Measure wall time and aggregate worker time separately. Attribute stage work honestly; do not invent unavailable model-reasoning duration. Serialization/rendering must not hide semantic work or reopen sources.

The normal generation path must use `scripts/generation_orchestrator.py`; do not generate per-project Python programs. Persist structured data under `.ftd/runs/<run-id>/` and keep diagnostics free of raw source text and materialized Claims.
