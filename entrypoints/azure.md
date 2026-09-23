# ftd-azure

Intent: project a finalized run's canonical Test Cases, plus zero/selected/all of its finalized Challenge runs, into a normalized Azure DevOps Test Plans package organized requirement by requirement. Consumes only a run's own validated JSON state (`canonical-suite.json` and finalized `challenge-cases.json`); it never rereads project sources or globs arbitrary repository JSON, and an unfinished Challenge run is not included unless explicitly (and then rejected, not silently skipped).

`scripts/azure_export.py prepare --run <run> [--challenge-id <id> ...]` writes `azure-export-package.json`; `preview --project P --plan L --suite S` writes a local, read-only `azure-preview.json` (create/update/unchanged/skipped/conflicts, including Challenge cases); `publish --approved` is the only path that can write remotely, and reuses `integrations/azure_devops.py` — the single owner of Azure mapping, Suite placement, diffing, idempotency and transport — rather than a second Azure client.

A Challenge case keeps its local `CH-017` identity forever; only its Azure export key (`challenge:<challenge_id>:CH-017`) identifies it as a Test Case work item, so two Challenge runs that each mint `CH-001` never collide remotely. A Test Case relevant to several requirements gets several Suite placements, never a cloned work item.

This command is an optional alias; `ftd-mcp` (canonical-only, single-suite preview) remains valid and unchanged. Natural language reaches the same dispatcher.
