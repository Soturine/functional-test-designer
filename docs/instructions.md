# Functional Test Designer instructions

<!--
How to use this file
- Copy it into your project (for example docs/instructions.md) and edit it.
- Headings and wording are free-form: rename, delete or add sections. The model reads the text by meaning.
- This file is guidance, not authority. Ideas here provoke analysis; they never force a Test Case
  and never limit what the analysis explores. Every idea gets an explicit answer in the output.
- Only the sources listed here are read. A directory is read recursively, but only inside itself.
- What you type on the command line or say in the conversation overrides this file.

Run:
  /ftd-gen --input-file ./docs/instructions.md --output json,md,html --diagnostics --output-dir ./ftd-output
After a successful run, the FTD remembers it as the current validated run: later commands such as
/ftd-chaos or /ftd-azure need no run id (pass --run <run-id> only for an older or specific run).
-->

## Sources

1. `docs/requirements.pdf` — functional authority
2. `docs/user/` — technical/product context
3. `src/` — implementation evidence
4. `tests/` — existing tests

Do not read anything else.

<!--
Roles, one sentence each:
- functional authority (FUNCTIONAL_AUTHORITY): what the system must do; the only source of expected results.
- technical/product context (TECHNICAL_CONTEXT): how users reach features (screens, manuals, routes).
- implementation evidence (IMPLEMENTATION_EVIDENCE): what actually exists in code and configuration.
- existing tests (TEST_ASSET): a challenge set for the new suite, never authority.
-->

## Main flow

- create the order
- approve the order
- ship and finish the order

## Things I want you to explore

- the wrong actor or the wrong resource
- an interruption in the middle of an operation, and recovery
- the same action done twice
- many users doing the same thing at once (never invent a threshold; ask for one)

## Physical/manual focus

- steps done with a device or by a person that cannot be automated

## Other guidance

- anything else that matters: actors, environments, integrations, known risks, review priorities

## After the run (optional)

- run chaos
- convert to Azure

<!--
Optional follow-up, in any words or language ("depois da run: fazer chaos, converter azure",
"no final quero chaos + Azure local"). Order: suite → chaos → report refreshed → local Azure package → stop.
Azure wording always means the LOCAL package; publishing to Azure DevOps is never automatic.
-->

## Output

- Language: the language of the requirements
- Formats: JSON, Markdown, HTML
- Diagnostics: yes
