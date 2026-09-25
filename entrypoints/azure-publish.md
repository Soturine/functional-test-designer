# ftd-azure-publish

```text
/ftd-azure-publish [--run <run-id>] --prepare --organization <url> --project <id|name> --plan <id|name> [--root-suite <id|name>] --auth <azure-cli|interactive|env:VARIABLE>
/ftd-azure-publish --apply "<output>/azure/publication-plan.json" --auth <...> [--approved]
```

- **Run:** `--run` is optional: without it the command uses the current validated run of the artifact root (`--output-dir`, default `./ftd-output`), recorded in `.ftd/current-run.json` when a canonical run is VALIDATED and verified again on use. An explicit `--run <run-id>` (or run directory) always wins.

Intent: publish a finalized run's local `/ftd-azure` package to Azure DevOps Test Plans. This is the **only** FTD command that can write to Azure DevOps, and it is never invoked implicitly — not by `/ftd-azure`, not by "convert/generate/prepare Azure" wording, not because credentials exist.

- **Prepare (read-only):** first prints the resolved run id and canonical digest, then authenticates, reads the explicitly named organization, project and Test Plan (and optional root suite), and writes `publication-plan.json` next to the package. It performs zero remote writes. A target is an exact id, or an exact name exactly one item has; nothing is guessed (no first item, no last-used target, no near name) and an ambiguous name stops with the candidate ids.
- **Plan contents:** source run id and package/canonical digests, organization/project/plan (and root suite) ids and names, timestamp, remote versions used, the summary and every operation: CREATE / UPDATE / UNCHANGED / CONFLICT / SKIPPED Test Cases, CREATE / REUSE suites, suite placements.
- **Apply:** reopens the plan, verifies the package and canonical digests are unchanged, revalidates that the connected organization/project/plan are the same ids (`TARGET_MISMATCH` otherwise), rechecks remote versions, prints the preview, and writes only after approval: the typed phrase `PUBLISH <project> / <plan>`, or `--approved` when no interaction is possible. No approval means zero writes.
- **Non-destructive v1:** creates Test Cases, updates only FTD-managed ones (proven by the local mapping export key → project id → work item id → last synchronized revision and content hash), creates child static suites under the destination and adds placements in order. Never deletes, never removes memberships, never creates Test Plans, never moves content between projects, never overwrites an unmapped look-alike (`POSSIBLE_UNMANAGED_MATCH`) or a Test Case changed remotely since the last sync (`CONFLICT`, no last-write-wins).
- **One work item per case:** a case in several suites is one Test Case with several placements, never a clone.
- **Credentials:** runtime only — Azure CLI session, Microsoft Entra interactive sign-in (optional `azure-identity`) or a short-lived value in an environment variable the user names. They are never written to the plan, mapping, logs, diagnostics, package or report.
- **Ownership:** `integrations/azure_devops.py` owns the Azure specifics (target resolution, diffing, placements, transport); `scripts/azure_publish.py` ties them to a finalized run.
