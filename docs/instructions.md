# Instructions for the Functional Test Designer

> The sections are examples. Add/remove/rename sections freely. The model interprets them semantically. They are guidance/seeds, not authority or a fixed schema.

Copy this file into your project as `docs/instructions.md` (or `docs/instructions.txt`) and run:

```text
/ftd-gen --input-file ./docs/instructions.md --output json,md,html
```

Explicit command options (`--output`, `--locale`, `--diagnostics`, `--output-dir`) and what you say in the conversation always win over this file.

## Sources

Read these, in this order:

1. `path/to/requirements.pdf`: the official requirements (functional authority).
2. `path/to/docs/`: product and user documentation.
3. `path/to/src/`: implementation code (evidence, not authority).
4. `path/to/config/`: configuration.
5. `path/to/tests/`: existing tests (a challenge set, never authority).

Do not read anything else.

## Flow ideas

A first idea of the main business flow. Reconstruct the real flow from the requirements and add or reorder steps where they say so.

- first business action
- next action
- final confirmation

## Adverse / real-world ideas

- an interruption in the middle of an operation
- the wrong actor or the wrong resource
- the same action done twice

## Physical / manual focus

- interactions with a device or a person that cannot be automated

## Performance focus

- many users doing the same thing at once (never invent a threshold; ask for one)

## Other guidance

Add anything else that matters to this project here: business concerns, actors, environments, integrations, known risks, unusual workflows, review priorities or other context.

## Output

- Language: the language of the requirements.
- Formats: JSON, Markdown and HTML.
