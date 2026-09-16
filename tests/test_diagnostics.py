from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIAGNOSTICS = load_script("diagnostics")
VALIDATOR = load_script("validate_output")


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output = self.root / "output"
        self.metrics = self.root / "diagnostics" / "run-metrics.json"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_diagnostics_records_real_macro_timing_without_affecting_validator(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)
        DIAGNOSTICS.begin_stage(self.metrics, "source_read")
        DIAGNOSTICS.end_stage(
            self.metrics,
            "source_read",
            ["Read one synthetic requirements document."],
            {"source_files": 1},
        )
        for name in DIAGNOSTICS.STAGE_NAMES[1:]:
            DIAGNOSTICS.skip_stage(self.metrics, name, ["Not exercised by this helper unit test."])
        document = DIAGNOSTICS.finish_run(
            self.metrics,
            self.output,
            ["Measure a complete synthetic agent run before changing the workflow."],
        )

        source_stage = document["stages"][0]
        self.assertTrue(source_stage["timing_available"])
        self.assertIsInstance(source_stage["elapsed_seconds"], float)
        self.assertGreaterEqual(source_stage["elapsed_seconds"], 0)
        self.assertEqual("GREENFIELD_REQUIREMENTS_ONLY", document["run"]["mode"])
        self.assertFalse(document["run"]["source_code_used"])
        self.assertFalse(document["run"]["existing_test_assets_used"])
        self.assertEqual(10, document["totals"]["test_cases"])
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_finish_requires_every_stage_to_be_addressed(self) -> None:
        DIAGNOSTICS.start_run(self.metrics)

        with self.assertRaisesRegex(ValueError, "Finish or skip every diagnostic stage"):
            DIAGNOSTICS.finish_run(self.metrics)


if __name__ == "__main__":
    unittest.main()
