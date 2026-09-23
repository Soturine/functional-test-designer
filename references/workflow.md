# Intents, clarification, outputs and integrations

Natural language is the primary interface. The aliases `ftd-gen`, `ftd-clarify`, `ftd-check`, `ftd-render`, `ftd-mcp` and `ftd-challenge` normalize through `scripts/workflow.py`; host wrappers contain no Test Design logic.

- `ftd-gen` starts the pipeline from selected sources (`pipeline.start_run`). The selection is a list of files and/or directories, each with a role (`sources: [{path, role}]`, or the pre-v2.3 `selectors` plus `roles`). Optional: `formats` (or stated in the request: "save HTML/JSON/Markdown"), `diagnostics` ("enable diagnostics"), `source_order` (ordered groups when the user says first/then/last), `clarifications` (prior `USER_CLARIFICATION` answers), `locale`. These become run properties: work orders carry order and clarifications to the model, and finalize applies the requested formats. A pre-v2.3 request carrying `scenario_profiles`, `evidence_packs`, `risk_conditions` or similar pre-authored semantics is rejected.
- `ftd-clarify` ranks open Questions by impact (oracle, actor/permission, starting state, trigger, input partition, execution boundary, side effect, procedure, test data, environment, observability, automation) and returns at most five. Ask one at a time; respect `stop`, `done`, `proceed`, `skip`. Answers are `USER_CLARIFICATION` evidence; a conflict with approved authority stays visible unless the user explicitly designates an authoritative correction.
- `ftd-check` audits published cases read-only (generic preconditions, abstract actions, unobservable results, hidden variants, path compression, placeholders, readiness).
- `ftd-clarify`, `ftd-check`, `ftd-render` and `ftd-mcp` accept either explicit data or `run_dir` / `canonical_path` of a finished run.
- `ftd-render` re-renders a validated run from canonical state with zero source reads and refreshes the publication proof.
- `ftd-mcp` builds an Azure DevOps Test Plans preview (`scripts/integrations/azure_devops.py`): create/update/unchanged/skipped/conflict, NEEDS_REVIEW skipped unless included, no deletes, no write without explicit approval, deterministic fallback exports when transport is unavailable. MCP is transport, never canonical truth.

## Post-suite challenge (optional)

`ftd-challenge` runs only against a finalized run (`run-state.json` status `VALIDATED`) and never rewrites it. It lives in `scripts/challenge.py`, its own thin shell alongside `pipeline.py`, and follows the same start → submit → finalize shape as the main stages:

```bash
python scripts/challenge.py start --run <run> --challenge-id <id> [--seed notes.md ...] [--focus "operator error and physical devices"]
# read challenges/<id>/work-order.json, author a challenge payload, then:
python scripts/challenge.py submit --run <run> --challenge-id <id> --file challenge.json
python scripts/challenge.py finalize --run <run> --challenge-id <id> [--azure-project P --azure-plan L --azure-suite S]
python scripts/challenge.py verify --run <run> --challenge-id <id>
```

- Seed Markdown files (zero, one or several) are `CHALLENGE_SEED`: informal ideas, not authority. Every seed file needs at least one `seed_dispositions` entry (`MATERIALIZED`, `ALREADY_COVERED`, `MERGED`, `QUESTIONED`, `NOT_APPLICABLE`); a seed never becomes an Acceptance oracle on its own. The model is expected to go beyond the seeds using the parent run's own actors, rules, states, findings, questions and evidence.
- Challenge cases live in their own `CH-*` namespace, never `TC-*`, and are validated the same way procedures are: grounded in `evidence_refs` or an honest `MISSING_EXECUTION_SURFACE`/`UNKNOWN_SETUP_PATH`, no generic preconditions, no abstract actions, no auth-only steps unless the case is about authentication. `execution_tags` (`AUTOMATABLE`, `MANUAL`, `PHYSICAL_DEVICE`, `EXTERNAL_ENVIRONMENT`, `EXPLORATORY`, `CHAOS_RECOVERY`) describe how a case can realistically run; a non-automatable case is never dropped for that reason.
- Canonical immutability is the one contract that matters: the parent's canonical digest is captured at `start` and re-checked at every later call. A challenge run that finds the parent changed refuses to continue rather than silently adapting to it. A failed `submit` leaves both the parent and the challenge run exactly as they were.
- `finalize` writes `challenges/<id>/challenge-cases.json`, `seed-dispositions.json` and `challenge-plan.md` (the Manual/Physical/Field Test Plan, grouping the new `CH-*` cases with the parent's own manual/physical/blocked/exploratory Test Cases by reference, never by cloning them). A `canonical_gap_candidate` on a case is advisory only: reviewing and, if accepted, generating a new canonical run is the only way to change the frozen suite.
- An `--azure-*` triple on `finalize` reuses `integrations/azure_devops.build_preview` for a local, read-only `azure-devops-preview.json` scoped to the challenge's own cases. Remote publication is the same explicit, approval-gated path the canonical suite already uses; generating a Challenge Pack never talks to Azure DevOps by itself.
- The same frozen parent supports any number of independent challenge runs (`--challenge-id`); each is disposable and none of them touch each other.

## Output selection

Formats: `HTML`, `JSON`, `MARKDOWN`, `DIAGNOSTICS`, `OPERATIONAL` (default `HTML,JSON,MARKDOWN`). HTML links only to published projections. `OPERATIONAL` renders the expansion catalog (`output/operational-scenarios.md`); `DIAGNOSTICS` writes `diagnostics/` (domain model, expansion candidates, checklists, journeys, test-asset challenge, run metrics). Private run state lives under `<artifact-root>/.ftd/runs/<run-id>/`.
