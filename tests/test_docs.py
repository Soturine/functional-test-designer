"""Documentation contracts: the quick start uses public commands only, and every document
agrees that /ftd-azure is local while only /ftd-azure-publish can write remotely."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow  # noqa: E402


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class ReadmeTests(unittest.TestCase):
    def test_every_public_command_is_explained(self) -> None:
        readme = read("README.md")
        for intent in workflow.INTENTS:
            self.assertIn(f"/{intent}", readme)

    def test_the_quick_start_uses_only_public_commands(self) -> None:
        readme = read("README.md")
        before_advanced = readme.split("## Avançado", 1)[0]
        self.assertNotIn("python scripts/", before_advanced)
        commands = re.findall(r"^(/[a-z-]+)", before_advanced, re.MULTILINE)
        self.assertTrue(commands)
        self.assertEqual(set(), {c.lstrip("/") for c in commands} - set(workflow.INTENTS))

    def test_output_dir_and_run_id_are_explained(self) -> None:
        readme = read("README.md")
        self.assertIn("--output-dir ./ftd-output", readme)
        self.assertIn(".ftd/runs/<run-id>/", readme)


class AzureSafetyAgreementTests(unittest.TestCase):
    DOCS = ("README.md", "SKILL.md", "entrypoints/azure.md", "entrypoints/azure-publish.md", "references/workflow.md")

    def test_every_document_keeps_ftd_azure_local(self) -> None:
        self.assertIn("Não — nunca se conecta", read("README.md"))
        self.assertIn("never contacts Azure DevOps", read("SKILL.md"))
        self.assertIn("never calls Azure", read("entrypoints/azure.md"))
        self.assertIn("`/ftd-azure` never connects", read("references/workflow.md"))

    def test_publication_is_explicit_and_approval_gated_everywhere(self) -> None:
        for name in ("README.md", "SKILL.md", "entrypoints/azure-publish.md", "references/workflow.md"):
            text = read(name)
            with self.subTest(document=name):
                self.assertIn("/ftd-azure-publish", text)
                self.assertRegex(text, r"PUBLISH <proje[ct]+o?> / <pla[no]+>")

    def test_examples_contain_no_real_targets_or_credentials(self) -> None:
        for name in (*self.DOCS, "docs/instructions.md"):
            text = read(name)
            with self.subTest(document=name):
                for url in re.findall(r"https://dev\.azure\.com/\S*", text):
                    self.assertRegex(url, r"<[^>]+>")
                self.assertIsNone(re.search(r"(?i)\b(?:pat|token|password)\s*[=:]\s*[A-Za-z0-9]{12,}", text))


class InstructionsTemplateTests(unittest.TestCase):
    def test_the_template_is_short_generic_and_self_explaining(self) -> None:
        text = read("docs/instructions.md")
        self.assertLess(len(text.splitlines()), 80)
        for phrase in ("free-form", "guidance, not authority", "never force a Test Case", "overrides this file",
                       "/ftd-gen --input-file"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
