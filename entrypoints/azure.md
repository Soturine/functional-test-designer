# ftd-azure

```text
/ftd-azure --run "<run>" --output json [--chaos-id <id> ...] [--canonical-only]
```

Intent: convert a finalized run's validated FTD state into **local** Azure DevOps Test Plans input JSON, organized like the publication (functional groups in operational order, transversal rules, execution views), with requirements kept as traceability.

- **Input:** it consumes only the run's `canonical-suite.json` plus finalized `/ftd-chaos` runs. The default is all finalized chaos runs; `--chaos-id` selects specific ones and `--canonical-only` excludes them. It never rereads project sources or globs repository JSON. An unfinished chaos run that is named explicitly is rejected.
- **Command:** `scripts/workflow.py azure --run <run> --output json`, which is the same as `scripts/azure_export.py --run <run>`. It writes to `<artifact_root>/output/azure/`:
  - `azure-export-package.json`: `suites` from the publication organization, requirement groups titled `identifier — official title` (traceability), and one record per case with its full execution context (test data, postconditions, cleanup, `state_contract`, readiness blockers, layer, tool hint, variants, request contract, resources, environment, related cases);
  - `azure-preview.json`: create/update/unchanged/skipped/conflicts and the Suite placements, diffed against local integration state.
- **Export keys:** `canonical:TC-001` and `chaos:<chaos-id>:CH-001`. Earlier `challenge:<id>:CH-001` keys are migrated deterministically. A case that belongs to several groups is one work item with several Suite placements, never a clone. A run that `supersedes` an earlier one also exports that run's finalized chaos cases.
- **Ownership:** `azure_export.py` owns FTD aggregation. `integrations/azure_devops.py` remains the single owner of Azure mapping, Suite placement, diffing, idempotency and transport.
- **Local only:** the command never authenticates, never reads tokens and never calls Azure. Live publication would need a future, explicit user request.

`ftd-mcp` was replaced by this command and only prints a migration message.
