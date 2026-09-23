# ftd-chaos

```text
/ftd-chaos --run "<run>" [--input-file "<path>/instructions.md"] [--output json,md,html] [--chaos-id <id>]
```

Intent: the post-suite real-world, adverse, field, physical and absurd-scenario pass over an already-**finalized** canonical run. It is not limited to the CHAOS expansion dimension. It can cover operator mistakes, device and manual work, recovery, external dependencies, load ideas and unexpected sequences — whatever this project's own evidence supports, never a closed list.

- **Command:** `scripts/workflow.py chaos --run <run> [--input-file ...] [--output ...]`.
  - With `--input-file` it is two-phase, like `/ftd-gen`: normalize the file semantically, then rerun with `--normalized <file>`.
  - Without it, the parent run's saved `normalized-request.json` seeds are reused.
- **Seeds:** each seed becomes an item anchored as `instructions.md#seed-NNN` (the file's own name). Seeds are inspiration, not authority. Disposition every item honestly, then go beyond the seeds.
- **Internals:** kept from the former Challenge implementation.
  - `scripts/challenge.py` state under `<run>/challenges/<id>/`: `lookup` for bounded evidence reads, then `submit` and `finalize`.
  - The parent canonical digest is re-checked on every command.
  - `CH-*` ids are separate from `TC-*`.
  - State machine STARTED → SUBMITTED → FINALIZED.
  - The saved domain model and evidence snapshots are reused; the corpus is never reread.
- **Outputs:** `finalize` publishes `<artifact_root>/output/chaos/<id>/` in the requested formats.
  - JSON: `chaos-cases.json` and `seed-dispositions.json`.
  - Markdown: `chaos-plan.md`, the Manual/Physical/Field plan.
  - HTML: `chaos-plan.html`.

`ftd-challenge` was renamed to this command and only prints a migration message. Natural language reaches the same dispatcher via the host's `resolved_intent="ftd-chaos"`.
