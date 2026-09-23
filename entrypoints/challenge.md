# ftd-challenge

Intent: run an optional, post-suite semantic challenge over an already-finalized run. Requires `run-state.json` status `VALIDATED`; a run that is not yet finalized is rejected with a clear message rather than silently finalized on its behalf.

Start with `scripts/challenge.py start --run <run> --challenge-id <id> [--seed file.md ...] [--focus "..."]`, read `challenges/<id>/work-order.json`, optionally request a bounded evidence excerpt with `scripts/challenge.py lookup`, then `submit` a payload and `finalize`. Seed Markdown files are `CHALLENGE_SEED` — inspiration, never authority — and the model is expected to go beyond them using the parent run's own actors, rules, states, findings and evidence.

The canonical suite is never rewritten: new cases use their own `CH-*` namespace under `challenges/<id>/`, and every command re-checks that the parent's canonical digest hasn't changed. `finalize` produces `challenge-cases.json`, `seed-dispositions.json` and the Manual/Physical/Field Test Plan (`challenge-plan.md`).

This command is an optional alias. An equivalent natural-language request — clearly about challenging an already-generated/finalized suite, not a new generation request — uses the same dispatcher.
