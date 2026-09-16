# Functional Test Designer

An independent Agent Skill that turns requirement documents into lean, traceable manual test cases and validated JSON. It preserves unknown behavior as explicit questions instead of inventing expected results.

## Use

Invoke the skill with the source and desired output location, for example:

```text
Use this skill to analyze docs/requirements.pdf and generate manual test cases in output/.
```

The agent follows `SKILL.md`, writes the contract defined in `references/output-contract.md`, and validates the result.

## Install the Validator Dependency

```bash
python -m pip install -r requirements.txt
```

## Validate Output

```bash
python scripts/validate_output.py output
python scripts/validate_output.py examples/expected-output
```

Success returns exit code `0`; schema or consistency failures return a non-zero exit code with itemized messages.

## Repository Layout

```text
SKILL.md                     Agent workflow
references/                  Test-design and output-contract guidance
schemas/                     JSON Schema Draft 2020-12 documents
scripts/validate_output.py   Schema and cross-file validator
examples/                    Synthetic requirement and passing output
tests/test_validator.py      Validator regression tests
```

## Current Boundaries

This V1 does not parse documents itself, automate tests, verify an implementation, publish work items, or integrate with Azure DevOps. A future adapter can consume the stable local `TC-XXX` JSON contract after human review.

## License and Attribution

The MIT license and required copyright notice are preserved in `LICENSE`. Adaptation details are in `ATTRIBUTION.md`.

