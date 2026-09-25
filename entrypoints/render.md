# ftd-render

Intent: re-render a validated run from canonical state (`scripts/pipeline.py render`) in the requested formats without source reads or Test Design reruns.

This command is an optional alias; ordinary language reaches the same intent through the host's `resolved_intent`.

- **Run:** `--run` is optional: without it the command uses the current validated run of the artifact root (`--output-dir`, default `./ftd-output`), recorded in `.ftd/current-run.json` when a canonical run is VALIDATED and verified again on use. An explicit `--run <run-id>` (or run directory) always wins.
