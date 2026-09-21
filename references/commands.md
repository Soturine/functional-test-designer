# Workflow intents

Natural language is the primary interface. The optional aliases `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, and `ftd-mcp` normalize through `scripts/workflow_entrypoints.py`; wrappers must not contain Test Design logic.

`ftd-gen` accepts selected scope, optional source order, artifact root, requested public formats, diagnostics preference, and prior clarifications. It resolves scope, creates canonical state, freezes identity, enriches procedure, classifies readiness, validates, and renders only requested outputs.

`ftd-clarify` ranks high-impact ambiguity. `ftd-check` is read-only and can focus on procedure, automation, cohesion, coverage, outputs, or everything. `ftd-render` validates and projects existing canonical state without source reads. `ftd-mcp` creates a preview and cannot write without explicit approval. `ftd-run` is reserved for a future runner contract.

Host adapters are ergonomic aliases only. Natural and command forms use the same authority rules, gates, canonical state, and dispatcher.
