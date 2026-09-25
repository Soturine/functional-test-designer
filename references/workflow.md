# Commands, intents, clarification, outputs and integrations

Public commands: `/ftd-gen`, `/ftd-chaos`, `/ftd-azure`, `/ftd-clarify`, `/ftd-check`, `/ftd-render`.

```text
/ftd-gen   --input-file "<path>/instructions.md" --output json,md,html [--diagnostics] [--output-dir <dir>] [--locale <tag>]
/ftd-chaos --run "<run>" [--input-file "<path>/instructions.md"] [--output json,md,html] [--chaos-id <id>]
/ftd-azure --run "<run>" --output json [--chaos-id <id> ...] [--canonical-only]
```

`ftd-challenge` was renamed to `ftd-chaos`, and `ftd-mcp` was replaced by `ftd-azure`. The old names only print a migration message.

## Intent routing is semantic

Natural language stays first-class, but Python does not interpret it.

- The host model reads the request in context and decides the intent.
- The same words can mean different things in different run states. For example, "now do the real tests" means `ftd-gen` when there are new sources and `ftd-chaos` when a suite is already finalized.
- The host then hands off `resolved_intent`, and `scripts/workflow.py` only:
  - recognizes exact aliases (`/ftd-gen`, `$ftd-gen`, `ftd-gen`); an exact alias always wins;
  - validates the host's `resolved_intent` against the six intents;
  - validates arguments and dispatches.
- There is no phrase catalog. A raw call with neither an alias nor a resolved intent raises `IntentUnresolved`, never a guess.
- Output formats come from explicit `--output`/`output` tokens: `json`, `md`/`markdown` and `html`, in any case. They are never sniffed from free text.

## The instructions file

`/ftd-gen` and `/ftd-chaos` read one user-authored file: `instructions.md` or `instructions.txt`, taken as written. `instructions.html` is accepted only as a converted form of the same content.

- **Resolution** (`scripts/instructions.py`):
  1. An explicit file wins, and it must have one of those names; any other basename is a clear error.
  2. An explicit directory resolves to the single instructions file inside it.
  3. With no path, the runtime tries `<workspace>/docs/`, then the skill's `docs/`.

  There is no recursive search. Two different instructions files in one directory are ambiguous and rejected.
- **Meaning:** the file is guidance, source-selection intent and exploration seeds. It is never authority, never a DSL and has no fixed sections: headings are free-form, and the runtime recognizes none of them. The public template is `docs/instructions.md`.
- **Normalization is a handoff, not a user burden.**
  - `workflow.py gen --input-file ...` prints the file's text and the contract.
  - The host interprets the file semantically and writes the normalized request:
    - `sources` with roles and optional `source_order`;
    - `output`, `reading` preferences, `guidance`, `seeds` and `ambiguities`;
    - `scope_root`, plus `transcriptions` for unreadable sources.
  - `workflow.py gen ... --normalized <file>` validates the request and starts the run. The request must match the file's current digest, and the file can never select itself as a source.
  - The run persists `<run>/normalized-request.json`: the sources, the seeds anchored as `instructions.md#seed-NNN`, the guidance, and the effective settings with provenance.
- **Precedence**, per setting (`EXPLICIT`, `INSTRUCTIONS`, `DEFAULT`): explicit CLI or current user request > the instructions file > skill defaults. For example, `--output json` beats "HTML only" in the file, and "do not use subagents" (`--reading-strategy SEQUENTIAL`) beats a worker preference in the file. The file never widens a scope the user narrowed.
- **Seeds and guidance** reach every model work order as `user_guidance`. They provoke reasoning and never limit it. A seed that the authority or evidence does not support is never promoted to a normative Test Case, a Finding or an oracle.

## /ftd-gen

`/ftd-gen` orchestrates the canonical pipeline, and the user never runs its steps by hand:

1. resolve and normalize the instructions file;
2. lock the sources;
3. read them with lightweight readers, or reuse their catalogs;
4. reconcile;
5. `design`, `expansion` and `procedures`;
6. `finalize` in the requested formats, including diagnostics when asked;
7. `verify`.

**Optional follow-up.** The normalized request may carry `post_generation` (`CHAOS`, `AZURE_LOCAL_EXPORT`), read semantically from any wording or heading in the instructions file, or given as `--after chaos,azure|none` (which overrides the file). The sequence is canonical finalize → optional chaos → finalize chaos → refresh publication → optional local `/ftd-azure` export → stop. `finalize` returns `post_generation` with `done` and `next_actions`: without chaos the local export runs immediately; with chaos it runs when the chaos run finalizes. Remote publication is never a follow-up action: a request containing one is rejected, and `/ftd-azure-publish` runs only on an explicit request. No stage or gate is added.

A `VALIDATED` run is frozen: nothing later edits its files. To publish a revision, start a new run id with `--supersedes <earlier-run-id>`; the relation is recorded in the new run's `run.json` only. With unchanged sources every file catalog is reused, so a revision needs no reader, and accepted stage payloads can be resubmitted through the normal validators.

The direct form `dispatch("ftd-gen", workspace=..., sources=[{path, role}], ...)` still exists for programmatic callers. A pre-v2.3 request carrying `scenario_profiles`, `evidence_packs`, `risk_conditions` or similar pre-authored semantics is rejected.

### Multi-agent source reading

Many lightweight readers read faster; one main model decides.

- **Planning.** `start_run` plans the reading in `<run>/reading/task-plan.json`.
  - **User source selector:** what the user selected, a file or a directory. It is the reader unit.
  - **Physical source file:** every file resolved under a selector. Each is owned by exactly one selector; when selectors overlap, the most specific one owns the file, and no file is read twice.
  - **File ledger:** one entry per physical file, with digest, role and state. The file is also the cache/reuse unit.
  - The default strategy is `MULTI_AGENT_PER_SOURCE`, where a "source" is a user selector.
- **Readers.** The work order lists `reader_assignments`: one per selector that still has unaccounted files. The host spawns one reader per assignment, preferring Haiku on a Claude host.
  - At most `concurrency` readers run at once (default 8). Assignments carry a `wave` number, and later waves wait.
  - Readers use ordinary file and navigation tools; they never generate helper scripts, parsers or crawlers to automate cataloging.
  - Design, Expansion and Procedures are semantic reasoning stages: write each item from its own claim, evidence and oracle. Never replace that reasoning with a generated mapping or template script that fills field shapes — templated items (one text with only identifiers, codes, fixtures or numbers swapped) are rejected. Helper files never go into the run's `stages/` directory: only the pipeline writes official stage state, and submission and finalize refuse any other file there.
  - An oversized selector may be split into internal shards only when real context limits require it. Shards reconcile back into one selector catalog, and their use is reported in the telemetry.
  - The core role name is `LIGHTWEIGHT_SOURCE_READER`, and no model name appears in the contract.
  - The user can override the worker count, the model or the strategy, including `SEQUENTIAL`, which means no subagents.
  - If the requested model is unavailable, the host says what it actually used.
- **Reader output.** Each reader returns one selector result (`selector_id`, `reader`, `catalog`, `files`). `files` accounts for every file it was assigned: `CATALOGED` with that file's own catalog, `INSPECTED` (read, nothing to add) or `FAILED` with an error. Selector-level facts cite the owned `file` they come from, and excerpts must. The catalog sections are:
  - headings, identifiers, actors, entities, states, operations, integrations;
  - config facts, candidate rules, flows, test assets, excerpts with line ranges, references and ambiguities.

  Claims, oracles, tests, Findings, Questions, coverage and authority decisions are rejected.
- **Submission.** `pipeline.py reading-submit` validates results as all-or-nothing: the digest matches, the role is unchanged, the catalog is non-empty and excerpt lines exist. A worker failure is submitted as `FAILED` with an error.
- **Reconciliation.** `pipeline.py reading-reconcile` refuses while any physical file under any selector lacks a disposition. It writes one provenance-preserving catalog per selector under `reading/selector-catalogs/`, and a `telemetry` block that separates the requested reader model, the reported one and host verification (always `null`). Plans written before selector ownership are upgraded in place on resume, keeping every recorded result. It preserves conflicting identifier statements and cross-references with no majority vote, writes `reading/source-catalog.json` and `reading/reconciliation.json`, and binds the reconciliation into the `TEST_DESIGN` manifest record. Design cannot start before reconciliation.
- **States:** `PLANNED`, `CATALOGED` (only with a validated reader result), `REUSED`, `FAILED_WORKER`, `FAILED_TO_READ`, `UNSUPPORTED`, `EMPTY` (a zero-byte file, accounted for with no reader) and `MAIN_MODEL` (sequential).
- **Reuse.** Validated catalogs are cached under `<artifact-root>/.ftd/catalog-cache/`. The key is a collision-safe source key (a digest of the normalized path plus a readable suffix) together with the content digest, the role and the contract version.
  - A later run reuses them without rerunning any reader. A changed file, or a changed role, invalidates only that file, so its selector's reader reads just the changed files.
  - Extracted text is cached by digest, so an unchanged large PDF is not re-extracted.
  - Frozen runs are never touched.

## Helper commands

- `ftd-clarify` ranks open Questions by impact and returns at most five. Its impact order is oracle, actor/permission, starting state, trigger, input partition, execution boundary, side effect, procedure, test data, environment, observability and automation.
  - Ask one question at a time, and respect `stop`, `done`, `proceed` and `skip`.
  - Answers are `USER_CLARIFICATION` evidence. A conflict with approved authority stays visible unless the user explicitly designates an authoritative correction.
- `ftd-check` audits published cases read-only: generic preconditions, abstract actions, unobservable results, hidden variants, path compression, placeholders and readiness.
- `ftd-render` re-renders a validated run from canonical state with zero source reads, and refreshes the publication proof.
- These three accept either explicit data or the `run_dir` / `canonical_path` of a finished run.

## /ftd-chaos (post-suite pass)

`/ftd-chaos` is the real-world, adverse, field, physical and absurd-scenario pass over a **finalized** run (`run-state.json` status `VALIDATED`). It never rewrites that run. It is not limited to the CHAOS dimension, and its themes are never a closed list.

- **Public entry point:** `scripts/workflow.py chaos`.
- **Internals:** the former Challenge implementation is kept to avoid a storage migration: `scripts/challenge.py` and `<run>/challenges/<id>/`. These names are an implementation detail.

```bash
python scripts/workflow.py chaos --run <run> [--input-file docs/instructions.md [--normalized seeds.json]] [--output json,md,html]
# read challenges/<id>/work-order.json; optionally ground a step in real evidence:
python scripts/challenge.py lookup --run <run> --challenge-id <id> --source <selected path> --query "..." # or --lines A-B
python scripts/challenge.py submit --run <run> --challenge-id <id> --file chaos.json
python scripts/challenge.py finalize --run <run> --challenge-id <id>
python scripts/challenge.py verify --run <run> --challenge-id <id>
```

- **Ids and state.** When no id is given, ids are minted as `chaos-001`, `chaos-002` and so on. The state machine is `STARTED → SUBMITTED → FINALIZED` and one-way: `start` rejects an existing id, `submit` and `finalize` are one-shot, and a failed `submit` never advances the state. A mistake is fixed by starting a new id.
- **Seeds** come from any of three places, and all are inspiration, never authority:
  - the normalized instructions file, as items anchored `instructions.md#seed-NNN`;
  - when no file is given, the parent run's saved `normalized-request.json`;
  - Markdown seed files, split structurally into one item per bullet or paragraph (`notes.md#seed-001`).

  Every seed item needs a `seed_dispositions` entry: `MATERIALIZED`, `ALREADY_COVERED` with a real `covered_by`, `MERGED`, `QUESTIONED` or `NOT_APPLICABLE`. The model is expected to go beyond the seeds.
- **Context reuse.** The work order reuses the parent's saved domain model, canonical cases, requirement titles, authority excerpts, Findings, Questions and evidence index.
  - `challenge.py lookup` resolves a bounded, scope-checked excerpt from the run's persisted evidence snapshot, which is written once at `start_run` and bound to the source digest.
  - Only recorded lookups count toward `runtime_targeted_lookups`. `runtime_full_source_rereads` is always 0.
- **Case rules.**
  - `CH-*` ids are separate from `TC-*`.
  - `evidence_refs` get scope and line-range validation. A case without them must declare `MISSING_EXECUTION_SURFACE` or `UNKNOWN_SETUP_PATH`.
  - The ubiquitous procedure rules apply: no vague whole steps, no generic preconditions, observable results.
  - `execution_tags` recognize six core tags but accept any `UPPER_SNAKE_CASE` tag.
  - A non-automatable case is never dropped.
- **Canonical immutability.** The parent digest is captured at `start` and re-checked by every later command.
- **Outputs.** `finalize` writes the private state: `challenge-cases.json`, `seed-dispositions.json` and `challenge-plan.md`, the Manual/Physical/Field Test Plan, which groups canonical cases by reference and never clones them. It then publishes `<artifact-root>/output/chaos/<id>/` in the requested formats:
  - `chaos-cases.json` and `seed-dispositions.json`;
  - `chaos-plan.md`;
  - `chaos-plan.html`, offline and self-contained.

  A `canonical_gap_candidate` is advisory only.

  **Execution contracts:** a CH case may carry `cleanup`, `execution_variants` and `request_contract` under the same rules as canonical procedures (variants cite evidence and name a resource the case uses; a contract describes the request without tool syntax or unstated thresholds). A load or concurrency CH whose steps name a request must carry its `request_contract`. Each CH gets a derived `state_contract`; nothing irrelevant is required, and finalized chaos runs are never rewritten. The report, organization and `/ftd-azure` payload carry these fields.

  After finalizing, the suite's own publication (`report.html`, `organization.json`, `execution-plan.md`) is re-rendered from persisted state so the new CH cases appear without a manual `/ftd-render`. It is the parent run's, or that of a run that explicitly supersedes it — whichever currently owns `output/`. The canonical suite stays byte-identical, no source is read and no stage is regenerated; only the publication proof is refreshed.

## /ftd-azure (local Azure DevOps input)

`/ftd-azure` converts a finalized run's validated state into **local** JSON. It never authenticates, never reads tokens and never calls Azure.

- **Input:** `canonical-suite.json` plus finalized chaos runs — the run's own and, when the run explicitly `supersedes` an earlier one, that run's (they keep their parent). The default is all of them; `--chaos-id` selects specific ones and `--canonical-only` excludes them. It never reads project sources or globs repository JSON. An unfinished chaos run that is named explicitly is rejected.
- **Output:** `<artifact-root>/output/azure/`.
  - `azure-export-package.json` holds `suites`, one per group of the publication organization (see [output-contract.md](output-contract.md#organization-organizationjson)): functional groups in operational order (`REQUIREMENT_BASED`), transversal rules and each execution view (`STATIC`), with `test_case_refs` in placement order, plus an `Unassigned` suite only when some case has no group. Requirement groups (`identifier`, `title`, `suite_name` = `identifier — official title`, `external_id` only when a mapping is supplied, `test_case_refs`) stay as traceability. It also holds one record per case: export key, local id, source kind, title, priority, status, preconditions, test data, steps and expected results, postconditions, cleanup, `state_contract`, requirement refs, related TCs, execution tags, automation suitability/readiness/readiness blockers/layer/tool hint, execution variants, request contract, environment/resources and chaos run id.
  - Every field an executor needs survives into the mapped payload (`map_test_case`): `test_data`, `postconditions`, `cleanup`, `automation.{suitability, readiness, readiness_blockers, layer, tool_hint}`, `execution.{state_contract, required_resources, environment_requirements, variants, request_contract}`, `source_kind` and `trace_refs.related_test_cases`.
  - `azure-preview.json` (`operation: LOCAL_PREVIEW_ONLY`) holds create/update/unchanged/skipped/conflicts and the Suite placements, diffed against local integration state.
- **Keys:** `canonical:TC-001` and `chaos:<chaos-id>:CH-001`. `CH-017` stays `CH-017` locally, and only its export key marks it as a Test Case work item. Integration state keyed `challenge:<id>:CH-nnn` by earlier versions is migrated deterministically (`migrate_integration_state`).
- **Suites:** one work item per case, placed in every suite of its organization groups (a functional group and, for example, the load view), never cloned; suite membership keeps the organization's order.
- **Requirement trace grouping:**
  - A canonical TC goes under its `source_identifiers`.
  - A CH with `related_source_identifiers` is placed directly (`DIRECT`).
  - A CH with only `related_test_cases` inherits the placement of those TCs (`INHERITED_FROM_RELATED_TC`). This is organizational, never authority.
  - A CH with neither goes to `Unassigned`.
  - A case relevant to several requirements is one record with several placements, never cloned.
  - Any official identifier scheme works.
- **Ownership:**
  - `scripts/azure_export.py` owns FTD aggregation: run and chaos selection, export keys and requirement↔case relationships.
  - `scripts/integrations/azure_devops.py` remains the single owner of Azure payload mapping, Suite placement, diffing, idempotency, integration state and the transport contract. Its `apply_preview` stays approval-gated and is never called by `/ftd-azure`.

## /ftd-azure-publish (guarded remote publication)

`/ftd-azure` never connects. `/ftd-azure-publish` is the only remote-writing command and runs only on an explicit publication request; see [entrypoints/azure-publish.md](../entrypoints/azure-publish.md).

- **Prepare** (`--prepare`): runtime credentials (Azure CLI session, Entra interactive sign-in, or a named environment variable), read-only calls against the explicitly selected organization/project/plan (exact id or exact unambiguous name), then a local `publication-plan.json` bound to those ids, the run id, the package and canonical digests and the remote versions used. Zero writes; the plan is never applied implicitly.
- **Apply** (`--apply <plan>`): digests unchanged, same target ids (`TARGET_MISMATCH` otherwise), remote versions unchanged (`CONFLICTS` otherwise), preview shown, approval typed as `PUBLISH <project> / <plan>` or given with `--approved`. Without approval, zero writes.
- **Operations:** CREATE Test Case, UPDATE an FTD-managed one (local mapping export key → project id → work item id → last revision and content hash), CREATE child static suites under the destination, ADD placements in order. No DELETE of any kind, no membership removal, no Test Plan creation, no move between projects, no overwrite of an unmapped look-alike or a remotely changed item.
- **Ownership:** `integrations/azure_devops.py` owns target resolution, diffing, placements and the REST transport (GET/POST/PATCH only); `scripts/azure_publish.py` binds them to a finalized run. Tests use a fake transport only.

## Output selection

- **Formats:** `HTML`, `JSON`, `MARKDOWN`, `DIAGNOSTICS` and `OPERATIONAL`. The default is `HTML,JSON,MARKDOWN`, and the command-line tokens `json,md,html` map to the first three.
- **HTML** links only to published projections.
- **OPERATIONAL** renders the expansion catalog (`output/operational-scenarios.md`).
- **DIAGNOSTICS** writes `diagnostics/`: domain model, expansion candidates, checklists, journeys, test-asset challenge and run metrics.
- **Private run state** lives under `<artifact-root>/.ftd/runs/<run-id>/`.
