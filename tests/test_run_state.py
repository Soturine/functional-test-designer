from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import diagnostics  # noqa: E402
from run_state import (  # noqa: E402
    RunStateStore,
    diagnostics_compatibility_self_check,
    source_manifest,
)


class RunStateTests(unittest.TestCase):
    def test_checkpoint_resume_requires_identical_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source = root / "requirements.md"
            source.write_text("approved behavior", encoding="utf-8")
            manifest = source_manifest([source], root)
            store = RunStateStore(root / "artifacts", "run-001")
            store.save("EVIDENCE_BARRIER_COMPLETE", {"evidence_refs": ["R1"]}, manifest)

            loaded = store.load(manifest)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.reusable)
            self.assertEqual({"evidence_refs": ["R1"]}, loaded.payload)

            source.write_text("changed behavior", encoding="utf-8")
            invalid = store.load(source_manifest([source], root))
            self.assertFalse(invalid.reusable)
            self.assertEqual("SOURCE_HASH_CHANGED", invalid.invalidation_reason)

    def test_internal_state_rejects_credentials_and_raw_sources(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            store = RunStateStore(Path(value), "run-001")
            for payload in ({"token": "secret"}, {"raw_source": "private text"}):
                with self.assertRaisesRegex(ValueError, "cannot persist sensitive"):
                    store.save("SCOPE_RESOLVED", payload, {})

    def test_diagnostics_contract_is_checked_before_expensive_work(self) -> None:
        observed = diagnostics_compatibility_self_check(
            diagnostics.STAGE_NAMES, diagnostics.AGGREGATION_STRATEGIES
        )
        self.assertTrue(observed["diagnostics_compatibility_checked"])
        json.dumps(observed)

        with self.assertRaisesRegex(ValueError, "unique"):
            diagnostics_compatibility_self_check(("scope", "scope"), {})


if __name__ == "__main__":
    unittest.main()
