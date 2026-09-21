from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_synthetic_e2e import run  # noqa: E402
from semantic_regression import (  # noqa: E402
    assert_projection_parity,
    fingerprint,
)


BASELINE_CORE_FINGERPRINT = "952bf5e0f908087d1644af9ded6f62ab4cecd8cacf21d924848463a893b4a953"
V20_PROCEDURE_FINGERPRINT = "692bb66f841249c51fc030fee1faf35636a23aa109fbfadbc420d8ef43edf7d8"
V21_PROCEDURE_FINGERPRINT = "7a2f1bac61f1e361f1eea39ac8fece7df8e434d92bd3cd6c43bfe152f7c29f0e"


class SemanticRegressionTests(unittest.TestCase):
    def test_runtime_noise_does_not_change_fingerprint(self) -> None:
        left = {"id": "TC-001", "generated_at": "2026-01-01", "run_id": "one"}
        right = {"id": "TC-001", "generated_at": "2027-01-01", "run_id": "two"}
        self.assertEqual(fingerprint(left), fingerprint(right))

    def test_public_synthetic_baseline_has_no_unexplained_drift(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            observed = run(Path(value))["semantic_regression"]

        self.assertEqual(BASELINE_CORE_FINGERPRINT, observed["core_fingerprint"])
        self.assertEqual(V21_PROCEDURE_FINGERPRINT, observed["procedure_fingerprint"])
        self.assertNotEqual(V20_PROCEDURE_FINGERPRINT, observed["procedure_fingerprint"])

    def test_projection_parity_rejects_semantic_mutation(self) -> None:
        canonical = [{"id": "TC-001", "objective": "Confirm order"}]
        assert_projection_parity(canonical, list(canonical))
        with self.assertRaisesRegex(ValueError, "differs from canonical"):
            assert_projection_parity(canonical, [{"id": "TC-001", "objective": "Cancel order"}])


if __name__ == "__main__":
    unittest.main()
