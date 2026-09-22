# ftd-gen

Intent: design a suite from explicitly selected sources. Start the staged pipeline (`scripts/pipeline.py start`, or `scripts/workflow.py` dispatch), then follow each `work-order.json`: submit `design`, `expansion` and `procedures`, and `finalize` with the requested formats. The shared core validates every stage; the model does the QA reasoning described in SKILL.md.

This command is an optional alias. An equivalent natural-language request uses the same dispatcher and pipeline.
