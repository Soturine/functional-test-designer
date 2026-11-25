"""Native-first reading: originals are read with the host's tools; extracted text verifies or falls back."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import reading  # noqa: E402
import sources  # noqa: E402


class NativeFirstTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / "docs").mkdir()
        (self.workspace / "docs" / "spec.md").write_text("REQ-1 The user signs in.\n", encoding="utf-8")
        (self.workspace / "docs" / "flow.png").write_bytes(b"\x89PNG not opened")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_records_carry_native_reading_guidance(self) -> None:
        records, _ = sources.build_source_records(
            self.workspace, {"docs/spec.md": "FUNCTIONAL_AUTHORITY", "docs/flow.png": "TECHNICAL_CONTEXT"}
        )
        by_path = {r["path"]: r for r in records}
        self.assertEqual("text", by_path["docs/spec.md"]["format"])
        self.assertEqual("image", by_path["docs/flow.png"]["format"])
        self.assertIn("native vision", by_path["docs/flow.png"]["native_reading"])
        self.assertEqual("none", by_path["docs/flow.png"]["extracted_layer"])
        self.assertIn("text layer", sources.EXTRACTED_LAYER["pdf"])

    def _task(self, fmt: str) -> dict:
        return {"source_key": "k", "path": "docs/spec.pdf", "role": "FUNCTIONAL_AUTHORITY",
                "content_digest": "d", "format": fmt}

    def _result(self, **reading_decl: object) -> dict:
        result = {"source_key": "k", "path": "docs/spec.pdf", "content_digest": "d", "status": "INSPECTED",
                  "reader": {"model": "m"}}
        if reading_decl:
            result["reading"] = reading_decl
        return result

    def test_pdf_text_layer_only_reading_must_declare_limitations(self) -> None:
        errors = reading._validate_result(self._result(method="extracted_text"), self._task("pdf"), {})
        self.assertTrue(any("text layer only" in e for e in errors), errors)
        ok = self._result(method="extracted_text", limitations=["host has no PDF reader"])
        self.assertEqual([], reading._validate_result(ok, self._task("pdf"), {}))
        self.assertEqual([], reading._validate_result(self._result(method="native"), self._task("pdf"), {}))

    def test_reading_declaration_is_optional_but_validated(self) -> None:
        self.assertEqual([], reading._validate_result(self._result(), self._task("pdf"), {}))
        errors = reading._validate_result(self._result(method="guess"), self._task("text"), {})
        self.assertTrue(any("reading.method" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
