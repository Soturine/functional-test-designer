from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("resolve_artifacts", ROOT / "scripts" / "resolve_artifacts.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load artifact resolver")
ARTIFACTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ARTIFACTS)


class ArtifactPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.skill = self.base / "functional-test-designer"
        self.source = self.base / "project-under-test"
        self.workspace = self.base / "test-run"
        self.skill.mkdir()
        self.source.mkdir()
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_explicit_root_is_used_exactly_without_skill_named_child(self) -> None:
        result = ARTIFACTS.resolve_artifact_paths(
            skill_root=self.skill,
            source_root=self.source,
            explicit_artifact_root=self.workspace,
        )

        self.assertEqual(str(self.workspace.resolve()), result["artifact_root"])
        self.assertEqual(str((self.workspace / "output").resolve()), result["output_path"])
        self.assertEqual(str((self.workspace / "diagnostics").resolve()), result["diagnostics_path"])
        self.assertEqual("explicit_user_path", result["artifact_root_source"])
        self.assertNotIn("functional-test-designer", Path(result["output_path"]).parts[-2:])

    def test_workspace_is_safe_fallback_even_when_cwd_is_skill_root(self) -> None:
        result = ARTIFACTS.resolve_artifact_paths(
            skill_root=self.skill,
            source_root=self.source,
            workspace_root=self.workspace,
        )

        self.assertEqual("workspace", result["artifact_root_source"])
        self.assertEqual(str((self.workspace / "output").resolve()), result["output_path"])

    def test_skill_root_is_never_a_fallback(self) -> None:
        with self.assertRaisesRegex(ARTIFACTS.ArtifactResolutionError, "skill root"):
            ARTIFACTS.resolve_artifact_paths(
                skill_root=self.skill,
                source_root=self.source,
                workspace_root=self.skill,
            )

    def test_source_root_requires_explicit_override(self) -> None:
        with self.assertRaisesRegex(ARTIFACTS.ArtifactResolutionError, "source root"):
            ARTIFACTS.resolve_artifact_paths(
                skill_root=self.skill,
                source_root=self.source,
                workspace_root=self.source,
            )

        result = ARTIFACTS.resolve_artifact_paths(
            skill_root=self.skill,
            source_root=self.source,
            explicit_artifact_root=self.source,
            allow_source_root=True,
        )
        self.assertEqual(str(self.source.resolve()), result["artifact_root"])

    def test_ambiguous_destination_requires_user_input(self) -> None:
        with self.assertRaisesRegex(ARTIFACTS.ArtifactResolutionError, "ambiguous"):
            ARTIFACTS.resolve_artifact_paths(skill_root=self.skill, source_root=self.source)

    def test_path_obtained_after_prompt_is_recorded_as_prompted(self) -> None:
        result = ARTIFACTS.resolve_artifact_paths(
            skill_root=self.skill,
            source_root=self.source,
            explicit_artifact_root=self.workspace,
            explicit_root_source="prompted",
        )

        self.assertEqual("prompted", result["artifact_root_source"])


if __name__ == "__main__":
    unittest.main()
