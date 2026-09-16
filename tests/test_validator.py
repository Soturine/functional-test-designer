from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_output", ROOT / "scripts" / "validate_output.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load validator")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def read(self, relative: str) -> dict:
        return json.loads((self.output / relative).read_text(encoding="utf-8"))

    def write(self, relative: str, value: dict) -> None:
        (self.output / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_expected_output_passes(self) -> None:
        self.assertEqual([], VALIDATOR.validate(self.output))

    def test_duplicate_requirement_id_fails(self) -> None:
        index = self.read("test-cases.json")
        index["requirements"].append(copy.deepcopy(index["requirements"][0]))
        self.write("test-cases.json", index)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("duplicate requirement ID: REQ-001" in error for error in errors))

    def test_missing_case_file_fails(self) -> None:
        (self.output / "test-cases" / "TC-001.json").unlink()

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("missing file" in error for error in errors))

    def test_blocking_question_requires_blocked_case(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-007.json")
        index["test_cases"][6]["status"] = "NEEDS_REVIEW"
        case["status"] = "NEEDS_REVIEW"
        self.write("test-cases.json", index)
        self.write("test-cases/TC-007.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("Q-001 is blocking but TC-007 status is not BLOCKED" in error for error in errors))

    def test_nonconsecutive_steps_fail(self) -> None:
        case = self.read("test-cases/TC-001.json")
        case["steps"][1]["step"] = 3
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("step numbers must be ordered consecutively" in error for error in errors))

    def test_case_source_must_be_declared(self) -> None:
        case = self.read("test-cases/TC-001.json")
        case["source_refs"][0]["source"] = "unknown.md"
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("TC-001 references source absent from index sources" in error for error in errors))

    def test_case_requirement_must_be_covered_by_scenario(self) -> None:
        index = self.read("test-cases.json")
        case = self.read("test-cases/TC-001.json")
        index["test_cases"][0]["requirement_refs"] = ["REQ-002"]
        case["requirement_refs"] = ["REQ-002"]
        self.write("test-cases.json", index)
        self.write("test-cases/TC-001.json", case)

        errors = VALIDATOR.validate(self.output)

        self.assertTrue(any("REQ-002 is not covered by its referenced scenarios" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
