# Workflow intents

Natural language is the primary interface. The optional aliases `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, and `ftd-mcp` normalize through `scripts/workflow_entrypoints.py`; wrappers must not contain Test Design logic.

`ftd-gen` accepts selected scope, optional source order, artifact root, requested public formats, diagnostics preference, and prior clarifications. It delegates to the enforced shared generation orchestrator, which gates scope, evidence accounting, source-first atomicity, selected-evidence opportunities, candidate-first cohesion, frozen identity, procedure, readiness, validation, canonical state, and requested renderers. There is no free-form generation fallback.

`ftd-clarify` ranks high-impact ambiguity. `ftd-check` is read-only and can focus on procedure, automation, cohesion, coverage, outputs, or everything. `ftd-render` validates and projects existing canonical state without source reads. `ftd-mcp` creates a preview and cannot write without explicit approval. `ftd-run` is reserved for a future runner contract.

Host adapters are ergonomic aliases only. Natural and command forms use the same authority rules, gates, canonical state, and dispatcher.
