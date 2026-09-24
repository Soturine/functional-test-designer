# Changelog

## Unreleased (targeting 2.4.0)

Optional post-suite challenge, additive to the frozen v2.3.0 pipeline. Not yet released or tagged; `VERSION` stays at 2.3.0.

- Added `ftd-challenge` and `scripts/challenge.py`: a start → submit → finalize workflow that runs only after `finalize` (`run-state.json` status `VALIDATED`) and never modifies the parent canonical suite, `run-manifest.json` or `TC-*` identities. The parent's canonical digest is captured at `start` and re-checked at `submit`, `finalize` and `verify`.
- New cases use a separate `CH-*` namespace under `<run>/challenges/<challenge-id>/`. Any number of independent challenge runs can target the same frozen parent.
- Zero, one or several Markdown seed files are accepted as `CHALLENGE_SEED` (inspiration, not authority); every seed file needs an honest `seed_dispositions` entry, and the model is expected to derive cases beyond what the seeds mention.
- Challenge cases are grounded like procedures (`evidence_refs` or an honest `MISSING_EXECUTION_SURFACE`/`UNKNOWN_SETUP_PATH`, real preconditions, observable results) and classified with `execution_tags` (`AUTOMATABLE`, `MANUAL`, `PHYSICAL_DEVICE`, `EXTERNAL_ENVIRONMENT`, `EXPLORATORY`, `CHAOS_RECOVERY`); a non-automatable case is never dropped for that reason.
- `finalize` produces `challenge-cases.json`, `seed-dispositions.json`, the Manual/Physical/Field Test Plan (`challenge-plan.md`, which references parent Test Cases rather than cloning them) and, given `--azure-project/--azure-plan/--azure-suite`, a local, read-only `azure-devops-preview.json` reusing the existing adapter.
- A challenge case may carry an advisory `canonical_gap_candidate`; it never patches the parent suite. Reviewing it and, if accepted, running a new canonical generation is the only way to change canonical output.
- No new gates: canonical immutability, reference integrity and explicit-only remote publication are checked directly, the same way the existing integrity contracts are.

Corrective/additive round on top of the above, still targeting 2.4.0:

- Challenge work orders now reuse the parent run's saved `domain_model`, requirement titles and authority excerpts instead of a shallow summary. Every eligible selected source is snapshotted once at `start_run` (`<run>/evidence/source-catalog.json` + `evidence/text/*.txt`), bound to its digest; `scripts/challenge.py lookup` resolves a real, bounded, scope-checked excerpt from that snapshot, and only a recorded lookup — never the mere presence of an `evidence_ref` — counts toward `runtime_targeted_lookups`. `runtime_full_source_rereads` is always 0 by construction; `model_source_rereads` is reported as `NOT_OBSERVABLE`.
- `evidence_refs` on a challenge case now get real scope/provenance validation (known selected source, non-empty locator, a line range that fits the source).
- Seed dispositioning is item-level: each seed file is split deterministically into addressable items (`file.md#seed-001`, one per bullet/paragraph); every item needs its own `seed_dispositions` entry (`ALREADY_COVERED` now requires a real `covered_by`), and a payload's temporary case keys are normalized to their assigned `CH-*`/canonical `TC-*` ids before being recorded.
- Challenge runs are strictly append-only: `STARTED → SUBMITTED → FINALIZED`; a second `submit` or a second `finalize` on the same `challenge_id` is rejected outright.
- Fixed natural-language routing: a clear generation request ("generate test cases for this physical device") now always reaches `ftd-gen`, even when it names vocabulary ("physical device", "real-world") that also appears in Challenge phrasing; `ftd-challenge` now requires unambiguous post-suite phrasing.
- `execution_tags` keeps six recognized core tags for rendering/grouping but is no longer a closed set; any well-formed `UPPER_SNAKE_CASE` tag is accepted. Case nature (e.g. `EXPLORATORY`) and readiness are derived and kept distinct, the same way canonical Test Cases already separate `automation_suitability` from `automation_readiness`.
- The Manual/Physical/Field Test Plan is richer per item (resources, environment, preconditions, steps, evidence to collect, blocking unknowns) and now also includes canonical Test Cases whose `automation_layer` is `HARDWARE`/`MIXED` regardless of `automation_suitability`.
- Added default multi-agent source reading/cataloging for the first canonical generation of a new or invalidated corpus: `sources.plan_reading_tasks` plans one lightweight reading/cataloging task per eligible selected source (`<run>/reading-task-plan.json`), with bounded concurrency, honoring an explicit `--reading-strategy`/`--reading-model`/`--reading-concurrency` override (including a `SEQUENTIAL` opt-out). The runtime only plans the work and records honest per-source dispositions; a host agent (preferring Haiku workers on Claude) executes it and always remains the sole owner of semantic synthesis. An unchanged source (by digest) already catalogued under the same artifact root is marked reusable.
- Added `ftd-azure` and `scripts/azure_export.py`: a canonical-plus-Challenge, requirement-by-requirement Azure DevOps packaging workflow, consuming only a run's own validated JSON state. `azure_export.py` owns FTD-side aggregation only (run/Challenge selection, scoped export keys, requirement↔case relationships); every Azure-specific concern (payload mapping, Suite placement, create/update/unchanged/conflict diffing, external ids, content hashes, integration state, transport/publish) stays owned by `integrations/azure_devops.py`, extended with a generic `build_group_suite_mapping`. A Challenge case keeps its local `CH-*` identity forever; only its scoped export key (`challenge:<challenge_id>:CH-nnn`) identifies it to Azure, preventing collisions across Challenge runs. `ftd-mcp` is unchanged and stays backward compatible.

Final rework round, still targeting 2.4.0 (unified commands):

- **Public commands** are now `/ftd-gen`, `/ftd-chaos`, `/ftd-azure`, `/ftd-clarify`, `/ftd-check` and `/ftd-render`.
  - `ftd-challenge` was renamed to `ftd-chaos`, and `ftd-mcp` was replaced by `ftd-azure`. Both old names only raise a migration message.
  - Their entrypoints and `.claude`/`.cursor` adapters were removed.
- **Semantic routing.** The host model resolves intent from the request and the run state and hands off `resolved_intent`. `scripts/workflow.py` only recognizes exact aliases, validates and dispatches.
  - The phrase tables, the generation-verb regex and free-text format sniffing are gone.
  - Formats come only from explicit `--output` tokens: `json`, `md`/`markdown` and `html`, case-insensitive.
- **Instructions file.** `/ftd-gen --input-file <path>/instructions.md --output json,md,html` is the primary interface.
  - The runtime file is `instructions.md` or `instructions.txt`, read as written. `instructions.html` is accepted only as a converted form of the same content.
  - Resolution: explicit file > explicit directory > `<workspace>/docs/` > the skill's `docs/`. There is no recursive search, and two instructions files in one directory are ambiguous.
  - The file is guidance, source intent and seeds, never authority. Its headings are free-form, and none is hardcoded.
  - The host normalizes it semantically. `scripts/instructions.py` validates that handoff, applies precedence per setting (explicit > file > defaults, with provenance) and persists `<run>/normalized-request.json`.
  - Seeds and guidance reach every model work order as `user_guidance`.
  - A generic template ships as `docs/instructions.md`.
- **Multi-agent ingestion is now real.** `scripts/reading.py` replaces `reading-task-plan.json` and `sources.plan_reading_tasks`.
  - `start` plans one `LIGHTWEIGHT_SOURCE_READER` task per eligible source (`<run>/reading/task-plan.json`).
  - The host runs the readers and submits validated factual catalogs (`pipeline.py reading-submit`). Main-model decisions are rejected, and so are digest or role drift and phantom excerpt lines. Submission is all-or-nothing.
  - `reading-reconcile` refuses while a source lacks a result. It preserves conflicts without voting, writes `reading/source-catalog.json` and `reconciliation.json`, and binds the reconciliation into the `TEST_DESIGN` manifest record. Design is refused before it.
  - The states are honest: `CATALOGED` requires a reader result.
  - Validated catalogs are reused across runs by collision-safe source key + digest + role + contract version, with no reader rerun. Only changed sources are invalidated.
  - Extracted text is cached by digest, and evidence and authority snapshots use the same source key.
  - `SEQUENTIAL` is the no-subagent opt-out.
- **Ubiquitous procedures.** One procedure serves a novice tester and an automation agent: who, where, what, target, data and expected, when the evidence supports them.
  - Vague whole steps are rejected: "access the system", "perform the operation", "validate it", "check if it worked", "continue the flow", "do everything required". So are "it works"-style expected results.
  - Nothing is invented.
  - The automation translation mapping is documented in `references/method.md`.
- **`/ftd-chaos`** keeps every former Challenge invariant: parent digest, `CH-*`, item-level seeds, real lookups, the one-way state machine and the Manual/Physical/Field plan. It adds:
  - seeds from the instructions file (`instructions.md#seed-NNN`), or from the parent run's saved request;
  - default ids `chaos-NNN`;
  - requested-format outputs under `output/chaos/<id>/`, including a self-contained HTML plan.
- **`/ftd-azure`** is local only.
  - It writes `output/azure/azure-export-package.json` and `azure-preview.json`, with requirement groups titled `identifier — official title` and an `Unassigned` group.
  - Keys are `canonical:TC-001` and `chaos:<id>:CH-001`, with deterministic migration of `challenge:` keys in integration state.
  - It selects chaos runs with `--chaos-id` or `--canonical-only`.
  - No Azure call is ever made. `azure_devops.py` remains the single Azure owner.

Source-selector reader round, still targeting 2.4.0:

- **Reader unit.** The reader unit is now the source selector the user declared. A selected directory is one reader responsibility, not one reader per physical file, and the runtime still keeps a per-file ledger (digest, role, state) for every file beneath it.
  - Overlapping selectors never double-own a file: the most specific selector wins.
- **Waves.** The work order lists `reader_assignments` with a `wave` number bounded by the concurrency limit (default 8, a host execution default).
- **Selector results.** A selector result accounts for every assigned file (`CATALOGED`, `INSPECTED` or `FAILED`). Facts must cite files the selector owns, and a result that references a file outside its selector is rejected.
- **Sharding.** Internal shards are optional, only for real capacity limits, and reconcile back into one selector catalog.
- **Reconciliation.** It refuses while any physical file is unaccounted. It writes one provenance-preserving catalog per selector and a telemetry block that separates the requested, reported and host-verified reader model.
- **Reuse.** File catalogs remain the cache unit, so only changed files under a selector are read again. A plan written before selector ownership is upgraded in place on resume, without re-reading.
- **Semantic barrier.** Documented: an authority-only skeleton may be prepared while readers run, while Design is decided and submitted only after reconciliation. Readers use ordinary file tools and never generate helper scripts to automate cataloging.
- **Bug fixes.** A zero-byte selected file gets the `EMPTY` state instead of an unreachable reader task, and submitted JSON written with a UTF-8 BOM is accepted.

Corrective round after the benchmark audit, still targeting 2.4.0:

- **Report family review.** "View Test Cases" on a family card opens on every unique Test Case the card counts ("All (N)"), not on its first identifier. Identifier pages remain as refinements through previous/next and a page selector, and a Test Case linked to several identifiers appears once in the family view.
- **Existing tests inside implementation trees.** Conventional test files (by ecosystem naming, in several languages) inside an `IMPLEMENTATION_EVIDENCE` selection are discovered as test assets and challenge the suite. The file keeps its role (`source_role`), never becomes authority, and an unparseable implementation-side test file is a warning.
- **Safe resume.** A run resumes only when its `selection_fingerprint` (corpus, per-file roles, selector structure, semantic request, locale) is unchanged. The same file under another role, or a changed selector structure, is re-planned with explicit reasons while compatible file catalogs are reused. A `VALIDATED` or `SUPERSEDED` run is refused instead of deleted.
- **Current reading preferences on resume.** Strategy, worker model and concurrency from the current request win over the stored plan and are recorded with their provenance. A contract 1 plan migrates to the current contract version, keeping the initial version in its history.
- **Cleaner reconciliation.** Exact restatements of a fact appear once per selector catalog. Identifier conflicts need an official identifier stated in disagreeing ways by two defining sources; implementation and test mentions become `identifier_references`.
- **Finding → Question.** A Finding with coverage disposition `QUESTION` must link the real Question(s) that ask what must be resolved; the canonical Finding carries optional `question_refs`.
- **Executable procedures.** Chained vague steps are rejected, as are expected results that only echo the action or offer alternative outcomes, and fixtures used without a test-data description (source codes excepted). A step that changes the environment or suppresses a signal needs supporting evidence or an honest `UNKNOWN_SETUP_PATH`/`MISSING_EXECUTION_SURFACE`, and a load, latency or capacity threshold may be asserted only when the designed Test Case states it. The guidance asks for self-contained procedures and a characterization shape for capacity questions without an SLA.
- **CI.** The test suite runs on Linux and Windows.

## 2.3.0

Simplification, quality recovery and model-first design.

- Consolidated 41 script modules into 11 (`common`, `sources`, `design`, `expansion`, `procedures`, `validation`, `pipeline`, `render`, `workflow`, `benchmark`, `integrations/azure_devops`) and 28 gates into 8 (`SCOPE_VALID`, `SOURCE_COVERAGE_VALID`, `NORMATIVE_BASELINE_VALID`, `ADDITIVE_EXPANSION_VALID`, `PROCEDURE_QUALITY_VALID`, `EVIDENCE_AND_REFERENCE_VALID`, `PIPELINE_INTEGRITY_VALID`, `PUBLICATION_VALID`). References went from 22 files to 6.
- Selected sources are the entry point. The model submits three stages (`design`, `expansion`, `procedures`) as JSON inside the official manifest; the runtime owns scope, identifiers, ids, validation, canonical state and publication. Pre-authored semantic request fields are rejected.
- The semantic core stays LLM-driven and domain-agnostic: universal reasoning dimensions, a project-derived `domain_model`, 14 operator-error patterns and 15 failure surfaces interpreted in the project's own terms. No project vocabulary lives in production code; six multi-domain packs (A–F) prove generality.
- Added `output_locale` with its source, official identifier titles (never `REQ-A — header` as a test title), explicit identifier dispositions and a runtime-derived identifier ledger.
- Made the 17-dimension second pass mandatory, with operator-error and chaos/recovery checklists, existing tests as a semantic challenge set, characterization, and E2E journeys composed of real atomic stages for every use case.
- Split `automation_suitability` from `automation_readiness`. READY no longer requires literal data: only material unknowns affect execution status.
- Added a priority rubric, simple Scenario Families, advisory merge candidates, honest six-dimension `gap_metrics` ("0 gaps" only when all are zero) and benchmark-only baselines that report `NOT_APPLIED` when not loaded.
- Preserved the public workflow: natural language first, `ftd-gen/clarify/check/render/mcp`, multiple files and directories, source order, output formats, diagnostics, prior clarifications and exact destination.
- Cross-requirement traceability: `related_identifiers` keeps every authoritative relationship in `requirement_refs`/`source_identifiers`, shown as chips on the collapsed HTML card.
- Semantic guards (no new gate family): a `structure_reviews` reason is required when a multi-item authority unit becomes one claim; copied intents are rejected; happy-path tests cannot cover adversarial scenarios; converging test assets must share a failure domain or oracle; one Question across several failure surfaces needs a `shared_policy`.
- Procedures are grounded and cheap: they run on frozen identities, cite `evidence_refs` or declare the path gap, reject generic authentication boilerplate, work in family batches from an indexed evidence context with zero source rereads, and report `procedure_generation_seconds`, `targeted_source_lookups`, `procedures_requiring_additional_evidence` and related diagnostics.
- Public schema stays 2.2 (additive optional fields); schema 1.2 suites still validate and render; legacy gate names are still accepted by the validator.

## 2.2.2

- Added an ordered, hash-chained runtime manifest for every official generation stage, canonical state, and published artifact.
- Made gate results runtime-owned and rejected request-supplied quality verdicts.
- Added atomic CP-to-Acceptance, Claim-to-Step/assertion, source-identifier, use-case-flow, Scenario Family, E2E-stage, automation, priority, and historical-baseline gates.
- Added official physical-source, identifier, claim-exercise, and Test Asset challenge diagnostics.
- Added publication tamper detection and an official validator mode using `--manifest`.
- Preserved public schema 2.2, schema 1.2 compatibility, additive expansion, canonical atomic TCs, and advisory-only merge candidates.

## 2.2.1

- Added a mandatory frozen normative baseline and a preservation gate before additive expansion.
- Added below-file normative-unit and use-case-flow accounting.
- Required explicit dispositions and materialization for supported risk, misuse, Test Asset, and characterization opportunities.
- Added physical evidence-reference, semantic E2E-composition, and Test Data reachability gates.
- Added procedure-template, priority-distribution, full-run provenance, and additive-layer diagnostics.
- Added advisory merge-candidate IDs/details, renderer counters, UTF-8 title fallback, and terminal run-state hygiene.
- Preserved public schema 2.2, schema 1.2 compatibility, atomic Acceptance identities, normative oracles, and zero destructive merges.

## 2.2.0

- Added an authority-aware source-universe gate before atomic extraction.
- Made the canonical design atomic-first: Scenario Families organize multiple independent Test Cases without deleting them.
- Replaced destructive shared-execution merging with non-destructive merge-candidate metadata.
- Added Acceptance, Characterization, Derived, Exploratory, Regression, and E2E test bases.
- Added explicit execution status, primary test taxonomy, automation hints, reciprocal Question/Finding links, and E2E composition.
- Added independent quality gates, expanded diagnostics, benchmark reconciliation, and stronger cross-reference validation.
- Updated Markdown and offline HTML to expose test basis, blocked states, merge candidates, E2E composition, automation candidates, and separate test-basis counters.
- Preserved schema 1.2 validation and rendering as a compatibility path.
