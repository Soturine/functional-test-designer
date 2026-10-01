**English** · [Português (Brasil)](README.pt-BR.md)

# Functional Test Designer

<p align="center">
  <img src="docs/hiw.png" alt="Functional Test Designer — conceptual workflow" width="100%">
</p>


Agent Skill that designs **traceable, executable functional Test Cases** using only the sources you select — requirements, documentation, source code, and existing tests — across any domain.

- **Input:** an `instructions.md` file describing what to read and what deserves extra attention.
- **Output:** a Test Case suite in JSON (source of truth), Markdown, and an offline HTML report with Questions, Findings, coverage, and traceability.
- **Optional:** a post-suite pass for realistic and adversarial scenarios (`/ftd-chaos`), a local Azure DevOps package (`/ftd-azure`), and, only when explicitly requested, publication to Azure DevOps (`/ftd-azure-publish`).

The model performs the QA reasoning; the runtime protects scope, traceability, validation, and publication. Nothing is silently invented: when the selected sources do not define something safely, the FTD records a Question or an explicit pending item instead.

> Published version: 2.5.0.

## Quick start

1. Copy [`docs/instructions.md`](docs/instructions.md) into your project and edit the sources.
2. Run:

~~~text
/ftd-gen --input-file ./docs/instructions.md --output json,md,html --diagnostics --output-dir ./ftd-output
~~~

3. Open `./ftd-output/output/report.html`.

`--output-dir ./ftd-output` means “store all FTD artifacts under `./ftd-output`” (the default is `<workspace>/ftd-output`). Without `--run-id`, the FTD creates an id such as `ftd-20260925-143000`; run state is stored under `./ftd-output/.ftd/runs/<run-id>/`.

You normally do not need to copy that id. After a successful generation, the FTD remembers the **current validated run** (`./ftd-output/.ftd/current-run.json`), and later commands use it when `--run` is omitted. Only a canonical `VALIDATED` run can become current — never a failed, incomplete, or chaos run — and it is verified again whenever reused. To target an older or specific run, pass `--run <run-id>`.

## The `instructions.md` file

A human-readable configuration file, not a DSL. Headings and wording are free-form; the model interprets the text semantically.

~~~markdown
## Sources
1. `docs/requirements.pdf` — functional authority
2. `docs/user/` — product context
3. `src/` — implementation evidence
4. `tests/` — existing tests

Do not read anything else.

## Things I want you to explore
- wrong actor or resource
- interruption and recovery
~~~

- It is guidance, never authority: an idea that the selected sources do not support does not become a normative Test Case, and guidance never limits the analysis.
- Every guidance item receives an explicit disposition (materialized, already covered, used for ordering, Question, or not applicable with a reason) — it never silently disappears.
- What you say in the conversation or pass on the command line overrides this file.

Post-run actions can also be written in the file using natural language:

~~~markdown
## After the run
- run chaos
- convert to Azure
~~~

The FTD interprets the intent and follows: suite → chaos → refreshed report → **local** Azure package → stop. “Convert/generate/prepare Azure” always means the local package; `/ftd-azure-publish` never runs automatically. On the command line, `--after chaos,azure` or `--after none` overrides the file.

Full commented template: [`docs/instructions.md`](docs/instructions.md).

## Commands

| Command | What it does | Writes outside the machine? |
| --- | --- | --- |
| `/ftd-gen` | Reads the selected sources and generates the canonical suite | No |
| `/ftd-chaos` | Optional post-suite cases for realistic, adversarial, physical, and field scenarios (`CH-*`) | No |
| `/ftd-render` | Re-renders from saved state without rereading sources | No |
| `/ftd-check` | Read-only suite audit | No |
| `/ftd-clarify` | Lists the most important Questions | No |
| `/ftd-azure` | Generates the **local** Azure DevOps package (JSON) | **No — it never connects** |
| `/ftd-azure-publish --prepare` | Reads the Azure DevOps target and creates a local publication plan | No remote writes (read-only remote access) |
| `/ftd-azure-publish --apply` | Publishes the reviewed plan | **Yes — only after explicit approval** |
| `/ftd --adr <folder>` (`/ftd-adr`) | Maintains the validated suite from new ADRs and decisions | No |

Natural-language requests also work (“run chaos”, “generate the Azure package”). “Generate/convert/prepare Azure” always means the local package; publication requires an explicit request.

## Full flow

~~~text
/ftd-gen   --input-file ./docs/instructions.md --output json,md,html --output-dir ./ftd-output
/ftd-chaos --input-file ./docs/instructions.md --output json,md,html
/ftd-azure
~~~

For a specific run: `/ftd-azure --run <run-id>` (the same applies to `/ftd-chaos`, `/ftd-check`, `/ftd-render`, and `/ftd-azure-publish --prepare`). If the artifact root is elsewhere, use `--output-dir`.

- `/ftd-chaos` never changes the canonical suite; once finalized, the report, organization, and execution plan are refreshed to include the `CH-*` cases.
- `/ftd-azure` writes `output/azure/azure-export-package.json` and `azure-preview.json`: one work item per case, multiple Suite placements when necessary, never cloned Test Cases.

### Publishing to Azure DevOps (optional and explicit)

~~~text
/ftd-azure-publish --prepare \
    --organization https://dev.azure.com/<your-org> --project <project> --plan <test-plan> --auth azure-cli
~~~

Review the preview first: organization, project, Test Plan, CREATE/UPDATE/CONFLICT counts, and `DELETE operations 0`. Only then:

~~~text
/ftd-azure-publish --apply ./ftd-output/output/azure/publication-plan.json --auth azure-cli
~~~

- `--prepare` first shows which run and canonical digest will be used, then reads the target and creates a `publication-plan.json` bound to that exact state.
- `--apply` rechecks the target and remote revisions, then writes only after you type `PUBLISH <project> / <plan>` (or pass `--approved` in non-interactive mode).
- Every published Test Case carries FTD execution metadata for downstream executors: status, readiness, suitability, automation layer/tool hint, blockers, and Question ids — through a human-readable Description section, `FTD_STATUS:`/`FTD_READINESS:`/`FTD_SUITABILITY:`/`FTD_LAYER:`/`FTD_TOOL:` tags, and a versioned `FTD_METADATA_V1` JSON block. Structured `request_contract` data and related Test Cases are preserved. Full Question details remain in the HTML report, allowing Azure to act as the operational execution source without the original source corpus.
- The destination is never guessed, nothing is deleted, Test Cases not managed by FTD are not overwritten, and credentials are never stored. Details: [`entrypoints/azure-publish.md`](entrypoints/azure-publish.md).

### Manual Azure DevOps import

Prefer importing by hand in Azure Test Plans (Import test cases from CSV/XLSX)? `/ftd-azure` can also write the import files locally — it still never connects to Azure:

~~~text
/ftd-azure --manual-import --fresh-target --area-path "<project>\<area>"
/ftd-azure --manual-import --existing-azure-export ./azure-current.csv --area-path "<project>\<area>"
~~~

**Blank ID = new Test Case. Existing ID = update of that Test Case.** The files are split by intent so an update can never create duplicates by accident.

- **Fresh target** (`--fresh-target`, only for a new, empty destination): CSV files with blank IDs under `output/azure/manual-import/manual-import-create/`, one per primary Suite. Each Test Case is created exactly once.
- **Existing target:** in Azure Test Plans, add **Tags** (and Description) through Column options, export the current Test Cases to CSV/XLSX and give that file back with `--existing-azure-export`. FTD matches each case by its `ftd-key:` tag (or the `FTD_METADATA_V1` block), never by title, and writes `manual-import-update.csv` with the existing IDs. A case with several matches is a CONFLICT; a case with no stable match is UNMATCHED and is **not** turned into a blank-ID row unless you pass `--allow-create`.
- `manual-import-plan.json` and `manual-import-summary.md` list CREATE / UPDATE / UNCHANGED / CONFLICT / UNMATCHED before you import anything. `--assigned-to` is optional (never invented); `--state` defaults to `Design`.
- **Review is visible:** titles read `TC-014 — …`, `[REVIEW] TC-014 — …`, `[BLOCKED] …` or `[EXPLORATORY] CH-003 — …`; the canonical title itself never changes. Opening a case shows the FTD execution status (status, readiness blockers, Question ids), and tags such as `FTD_STATUS:NEEDS_REVIEW` keep it filterable.
- **Suite order:** `suite-order.md` lists the Suites in display order — requirements in natural order (`REQ-2` before `REQ-10`), then use cases, transversal rules and execution views — and the reverse creation order for Test Plans that insert new Suites on top. Suite names stay clean.
- **No clones:** a case that belongs to several Suites is imported once, in its primary Suite; `secondary-suite-placements.csv` lists the other Suites to add the same Test Case to with **Add existing test cases**.

`/ftd-azure-publish` is unchanged; manual import is an additional, safe workflow.

## Maintaining the suite with ADRs

Generate the suite once; when ADRs, approved decisions, meeting notes or other change material arrive later, point the FTD at them:

~~~text
/ftd-gen --input-file ./docs/instructions.md --output json,md,html     # once, at the start
/ftd --adr ./docs/adr/                                                 # whenever new decisions arrive
~~~

FTD uses the project's current validated run (and its latest finalized ADR round) unless you pass `--run`. It:

- reads only new or changed ADR files and reuses everything already analyzed — the suite is not regenerated and the original sources are not reread;
- treats the folder as a change corpus: formal ADRs, notes, drafts and observations are understood by meaning, statement by statement, with their own authority — only an approved decision changes expected behavior, while drafts and notes become Questions, Findings or review items;
- shows which Test Cases are affected (directly or indirectly), proposes updates to existing Test Cases (same id) and new Test Cases where behavior is not covered yet, each with a complete executable procedure;
- records new Questions and Findings and marks old Questions an ADR answers, without erasing history;
- writes an offline report (`output/adr/<adr-id>/adr-report.html`) with decisions, before/after and procedure changes, and a local Azure delta with only the changed Test Cases;
- never publishes by itself: `/ftd-azure-publish --prepare --adr <adr-id>` and an approved `--apply` update the same Azure Test Cases, and an executed Test Case whose behavior changed needs your explicit decision first.

Details: [`entrypoints/adr.md`](entrypoints/adr.md).

## How it works

~~~text
start       (runtime)  scope → source roles → official identifiers → language → existing tests
reading     (readers)  factual catalogs per source (reused when the source is unchanged)
design      (model)    requirements → atomic claims → Acceptance TCs → frozen normative baseline
expansion   (model)    17 dimensions, operator mistakes, failures, existing tests, E2E journeys (add-only)
procedures  (model)    executable steps, semantic fixtures, pending items, automation metadata
finalize    (runtime)  8 gates → canonical state → HTML / JSON / Markdown → publication proof
~~~

Every model stage is validated by the runtime; an invalid stage is rejected with all detected problems at once. Design, Expansion, and Procedures are semantic reasoning stages — scripts that generate templated payloads are rejected.

- **Scope:** only selected sources; a directory is recursive only within itself.
- **Roles:** `FUNCTIONAL_AUTHORITY` (what must happen), `TECHNICAL_CONTEXT` (how users reach it), `IMPLEMENTATION_EVIDENCE` (what actually exists), and `TEST_ASSET` (existing tests challenge the new suite but are never authority).
- **Language:** the language of the functional authority unless explicitly overridden.

## Outputs

~~~text
./ftd-output/
|-- output/
|   |-- report.html            offline report: requirements, families, E2E, load, physical, chaos, all
|   |-- test-cases.json        index: requirements, coverage, gaps, gates
|   |-- test-cases/TC-XXX.json source of truth for each Test Case
|   |-- test-cases-md/         Markdown version of each Test Case
|   |-- organization.json      groups and execution order (references, no copies)
|   |-- execution-plan.md      each group with its cases in execution order
|   |-- questions.json
|   |-- chaos/<id>/            with /ftd-chaos
|   `-- azure/                 with /ftd-azure (and the /ftd-azure-publish plan)
|-- diagnostics/               with --diagnostics
`-- .ftd/runs/<run-id>/        private run state
~~~

## Security

- FTD reads only the sources you select and never executes their code.
- `/ftd-azure` never connects to anything. Only `/ftd-azure-publish --apply` writes to Azure DevOps, after an explicit target, a reviewed plan, and your approval. There is no delete operation.
- Azure credentials are used only at runtime (Azure CLI session, interactive Microsoft Entra login, or an environment variable you explicitly name) and are never persisted.

## Advanced

- Contracts and references: [`SKILL.md`](SKILL.md), [`references/workflow.md`](references/workflow.md), [`references/stage-contracts.md`](references/stage-contracts.md), [`references/output-contract.md`](references/output-contract.md), [`references/validation.md`](references/validation.md).
- Internal steps (`/ftd-gen` already orchestrates them; use these only for debugging):

~~~bash
python scripts/pipeline.py start --workspace <root> --source "docs/requirements.pdf=FUNCTIONAL_AUTHORITY" \
    --source "src=IMPLEMENTATION_EVIDENCE" --artifact-root <destination> --run-id <id>
python scripts/pipeline.py submit --run <run> --stage design --file design.json      # then expansion, procedures
python scripts/pipeline.py finalize --run <run>
python scripts/pipeline.py verify --run <run>
~~~

- Validate and test:

~~~bash
python -m pip install -r requirements.txt
python scripts/validation.py <destination>/output --manifest <destination>/.ftd/runs/<run-id>/run-manifest.json
python scripts/benchmark.py packs           # six synthetic multi-domain packs
python -m unittest discover -s tests
~~~

## Limits

FTD does not execute tests, create Shared Steps, globally index the repository, or delete/move anything in Azure DevOps during publication.

See also [`CHANGELOG.md`](CHANGELOG.md), the [migration guides](docs/migrations/README.md), and the [history](docs/history/v2.3-simplification-report.md).

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
