# ftd-check

Intent: read-only audit of an existing canonical run. Accept natural focus such as procedure, automation, coverage, outputs, or everything. Never silently redesign.

This command is an optional alias; ordinary language reaches the same intent through the host's `resolved_intent`.

- **Run:** `--run` is optional: without it the command uses the current validated run of the artifact root (`--output-dir`, default `./ftd-output`), recorded in `.ftd/current-run.json` when a canonical run is VALIDATED and verified again on use. An explicit `--run <run-id>` (or run directory) always wins.
