# Migrating from v2.2.1 to v2.2.2

Public Test Case schema version remains `2.2`, and schema `1.2` remains supported.
New case properties are optional for stored compatibility, while the official
v2.2.2 generation runtime derives and validates automation blockers, priority
reasons, Claim exercise mappings, E2E stage mappings, and narrowly justified
atomicity exceptions.

Official runs now include `.ftd/runs/<run-id>/run-manifest.json`. Consumers that
claim pipeline provenance should validate it alongside public output:

```bash
python scripts/validate_output.py output --manifest .ftd/runs/<run-id>/run-manifest.json
```

The diagnostics selection additionally emits `test-asset-challenge.json`,
`physical-source-ledger.json`, `source-identifier-ledger.json`, and
`claim-exercise-map.json`. These are diagnostic/internal artifacts, not new
mandatory public Test Case files.
