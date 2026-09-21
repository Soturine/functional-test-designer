# Canonical state and output selection

Persist private run state under `.ftd/runs/<run-id>/` when enabled. The canonical suite contains the validated semantic state used by every renderer; it is not a new public schema.

Supported public selections are HTML, JSON, Markdown, and diagnostics. Default behavior may retain the established full output, but an explicit selection emits only those formats. HTML must not link to JSON or Markdown that was not published. Rendering validates canonical state, performs zero project-source reads, and never reruns Test Design.

Record requested and rendered formats, canonical-state persistence, and source reads during render. Same canonical state and renderer options must produce the same semantic projection.
