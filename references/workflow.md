# Intents, clarification, outputs and integrations

Natural language is the primary interface. The aliases `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render` and `ftd-mcp` normalize through `scripts/workflow.py`; host wrappers contain no Test Design logic.

- `ftd-gen` starts the pipeline from selected sources (`pipeline.start_run`). The selection is a list of files and/or directories, each with a role (`sources: [{path, role}]`, or the pre-v2.3 `selectors` plus `roles`). Optional: `formats` (or stated in the request: "save HTML/JSON/Markdown"), `diagnostics` ("enable diagnostics"), `source_order` (ordered groups when the user says first/then/last), `clarifications` (prior `USER_CLARIFICATION` answers), `locale`. These become run properties: work orders carry order and clarifications to the model, and finalize applies the requested formats. A pre-v2.3 request carrying `scenario_profiles`, `evidence_packs`, `risk_conditions` or similar pre-authored semantics is rejected.
- `ftd-clarify` ranks open Questions by impact (oracle, actor/permission, starting state, trigger, input partition, execution boundary, side effect, procedure, test data, environment, observability, automation) and returns at most five. Ask one at a time; respect `stop`, `done`, `proceed`, `skip`. Answers are `USER_CLARIFICATION` evidence; a conflict with approved authority stays visible unless the user explicitly designates an authoritative correction.
- `ftd-check` audits published cases read-only (generic preconditions, abstract actions, unobservable results, hidden variants, path compression, placeholders, readiness).
- `ftd-clarify`, `ftd-check`, `ftd-render` and `ftd-mcp` accept either explicit data or `run_dir` / `canonical_path` of a finished run.
- `ftd-render` re-renders a validated run from canonical state with zero source reads and refreshes the publication proof.
- `ftd-mcp` builds an Azure DevOps Test Plans preview (`scripts/integrations/azure_devops.py`): create/update/unchanged/skipped/conflict, NEEDS_REVIEW skipped unless included, no deletes, no write without explicit approval, deterministic fallback exports when transport is unavailable. MCP is transport, never canonical truth.

## Output selection

Formats: `HTML`, `JSON`, `MARKDOWN`, `DIAGNOSTICS`, `OPERATIONAL` (default `HTML,JSON,MARKDOWN`). HTML links only to published projections. `OPERATIONAL` renders the expansion catalog (`output/operational-scenarios.md`); `DIAGNOSTICS` writes `diagnostics/` (domain model, expansion candidates, checklists, journeys, test-asset challenge, run metrics). Private run state lives under `<artifact-root>/.ftd/runs/<run-id>/`.
