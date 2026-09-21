# MCP and Test Management integration

The canonical suite feeds a target adapter, then preview/validation, then an optional transport. Target payloads never become canonical truth.

The Azure DevOps adapter maps portable title, priority, preconditions, Action/Expected steps, tags, trace refs, and status metadata. Preview classifies create, update, unchanged, skipped, and conflict candidates with target project/plan/suite. `NEEDS_REVIEW` is skipped unless explicitly included; `BLOCKED` is skipped.

Persist non-secret local/external IDs, content hashes, synchronized versions, and target refs under private integration state. A second unchanged sync is a no-op. External changes create conflicts rather than silent overwrite. Never delete because a local case disappeared. No write occurs without explicit approval.

When transport is unavailable, say so and produce deterministic preview exports under `exports/azure-devops/`; never claim publication succeeded. Keep tokens outside repository files.
