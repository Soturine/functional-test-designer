# ftd-gen

```text
/ftd-gen --input-file "<path>/instructions.md" --output json,md,html [--diagnostics] [--output-dir <dir>] [--locale <tag>]
```

Intent: design the canonical suite for the sources that the instructions file (or the user) selects. The input is `instructions.md` or `instructions.txt`, read as written; `instructions.html` is accepted only as a converted form of the same content. `--output` tokens are case-insensitive: `json`, `md`/`markdown`, `html`; default `json,md,html`.

Input resolution (`scripts/instructions.py`): an explicit file must be named `instructions.md` or `instructions.txt` (or `instructions.html`); an explicit directory means the single instructions file inside it; with no path, `<workspace>/docs/`, then the skill's `docs/`. Two different instructions files in one directory are ambiguous and rejected. The user's path always wins; there is no recursive search.

Orchestration — the user never runs these steps by hand:

1. `scripts/workflow.py gen --input-file ... --output ...` prints the normalization order: the file's text and the handoff contract.
2. Interpret the file **semantically**: headings are free-form, and section names are never keywords. Normalize it into sources with roles and optional order, output, reading preferences, guidance and seeds. Explicit CLI and user instructions win over the file, and the file wins over defaults. Seeds and guidance provoke reasoning; they never limit it and are never authority. If source roles are materially ambiguous, ask one concise question.
3. `scripts/workflow.py gen ... --normalized <file>` validates the request, persists `<run>/normalized-request.json` and starts the run.
4. Follow each `work-order.json`:
   - **reading:** one lightweight reader per planned source (Haiku on a Claude host by default, bounded concurrency, or the user's override), then `pipeline.py reading-submit` and `reading-reconcile`;
   - **model stages:** `design`, `expansion` and `procedures`;
   - **finish:** `pipeline.py finalize` and `verify`.

Natural language reaches the same dispatcher: the host resolves the intent (`resolved_intent="ftd-gen"`); Python never matches phrases.
