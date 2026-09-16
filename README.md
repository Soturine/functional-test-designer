# Functional Test Designer V1.1

An independent Agent Skill that converts requirement documents into Coverage Points, executable manual Test Cases, validated JSON, and a friendly offline HTML report. This version operates only in `GREENFIELD_REQUIREMENTS_ONLY` mode.

## Install

```bash
python -m pip install -r requirements.txt
```

## Validate and Render

```bash
python scripts/validate_output.py output
python scripts/render_report.py output
```

The validator returns exit code `0` on success. The renderer validates first and writes `output/report.html` without changing JSON.

Validate and render the synthetic example with:

```bash
python scripts/validate_output.py examples/expected-output
python scripts/render_report.py examples/expected-output
```

## Manual Skill Run

```text
Use the functional-test-designer skill.

Mode:
GREENFIELD_REQUIREMENTS_ONLY

Diagnostic:
true

Input:
<requirements document selected by the user>

Output:
output/
```

Expected artifacts:

```text
output/
|-- test-cases.json
|-- questions.json
|-- report.html
`-- test-cases/
    `-- TC-XXX.json

diagnostics/
`-- run-metrics.json
```

Diagnostics are optional and separate from the Test Case contract. See `references/diagnostics.md` for the real-time stage commands.

## Repository Layout

```text
SKILL.md                     Requirements-only agent workflow
references/                  Output, conditional test design, and diagnostics guidance
schemas/                     JSON Schema Draft 2020-12 documents
scripts/validate_output.py   Schema and cross-file validator
scripts/render_report.py     Offline HTML renderer
scripts/diagnostics.py       Optional wall-clock stage recorder
examples/                    Synthetic requirement and V1.1 output
tests/                       Validator, renderer, and diagnostics tests
```

## Boundaries

V1.1 does not use backlog, source code, implementation behavior, existing tests, or project history as generation inputs. It does not automate tests or integrate with the Azure DevOps API. The TC title, priority, preconditions, and per-step Action/Expected Result remain straightforward to map in a future adapter.

Future work may add a separate audit mode for existing projects. That mode is not implemented or anticipated through new abstractions here.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details are in `ATTRIBUTION.md`.

