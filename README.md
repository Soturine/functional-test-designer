# Functional Test Designer V1.2

An Agent Skill that designs traceable functional manual tests from only the sources explicitly selected by the user. It supports requirements, selected implementation evidence, technical context, and existing QA assets while preserving their different authority roles.

## Install

```bash
python -m pip install -r requirements.txt
```

## Use

```text
Use the functional-test-designer skill.

Analyze only:
- docs/requirements.md
- src/order_service.py

Write the artifacts to output/.
```

A selected directory is recursive only within that directory. Files, imports, links, dependencies, and sibling directories are not implicitly selected.

## Validate and Render

Run the artifact pipeline in order:

```bash
python scripts/validate_output.py output
python scripts/render_markdown.py output
python scripts/render_report.py output
```

The validator checks JSON. The Markdown renderer writes one file per TC without changing JSON. The offline HTML report reads the Mermaid flow from each corresponding Markdown file.

Validate the synthetic example:

```bash
python scripts/validate_output.py examples/expected-output
python scripts/render_markdown.py examples/expected-output
python scripts/render_report.py examples/expected-output
python -m unittest discover -s tests -v
```

## Artifacts

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
|-- test-cases/
|   `-- TC-XXX.json
`-- test-cases-md/
    `-- TC-XXX.md
```

Optional execution diagnostics live separately under `diagnostics/` and contain timings, counts, and scope proof only.

## Repository Layout

```text
SKILL.md                       Scoped-source agent workflow
references/                    Contract, test design, and diagnostics guidance
schemas/                       JSON Schema Draft 2020-12 documents
scripts/resolve_scope.py       Metadata-only selected-path resolver
scripts/validate_output.py     JSON and cross-file validator
scripts/render_markdown.py     Deterministic per-TC Markdown renderer
scripts/render_report.py       Offline HTML renderer
scripts/diagnostics.py         Optional execution diagnostics
examples/                      Synthetic multi-source V1.2 example
tests/                         Scope, contract, renderer, and diagnostics tests
```

This skill does not crawl dependencies, index a repository, automate tests, create Shared Steps, or integrate with the Azure DevOps API.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details remain in `ATTRIBUTION.md`.
