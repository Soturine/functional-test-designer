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


class PostGenerationDocsTests(unittest.TestCase):
    def test_follow_up_actions_are_documented_as_free_form_and_local(self) -> None:
        readme, skill, template = read("README.md"), read("SKILL.md"), read("docs/instructions.md")
        self.assertIn("## Depois da run\n- fazer chaos\n- converter azure", readme.replace("\r\n", "\n"))
        self.assertIn("`/ftd-azure-publish` nunca roda sozinho", readme)
        self.assertIn("Any Azure wording means the local export", skill)
        self.assertIn("publishing to Azure DevOps is never automatic", template)



class RepositoryLayoutTests(unittest.TestCase):
    ROOT_FILES = {"README.md", "SKILL.md", "CHANGELOG.md", "LICENSE", "ATTRIBUTION.md", "VERSION", "requirements.txt",
                  ".gitignore"}

    def test_the_root_holds_only_current_entry_point_files(self) -> None:
        files = {p.name for p in ROOT.iterdir() if p.is_file()}
        self.assertEqual(set(), files - self.ROOT_FILES)
        self.assertFalse(list(ROOT.glob("MIGRATION-*.md")))
        self.assertFalse((ROOT / "SIMPLIFICATION_REPORT.md").exists())

    def test_historical_documents_are_kept_and_indexed(self) -> None:
        index = read("docs/migrations/README.md")
        for version in ("v2.2", "v2.2.1", "v2.2.2", "v2.3.0"):
            self.assertTrue((ROOT / "docs" / "migrations" / f"{version}.md").is_file())
            self.assertIn(f"({version}.md)", index)
        self.assertTrue((ROOT / "docs" / "history" / "v2.3-simplification-report.md").is_file())

    def test_no_document_or_script_points_at_the_old_root_paths(self) -> None:
        stale = re.compile(r"MIGRATION-v2|SIMPLIFICATION_REPORT")
        for path in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "references").glob("*.md"),
                     *(ROOT / "entrypoints").glob("*.md"), *(ROOT / "scripts").rglob("*.py")]:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIsNone(stale.search(path.read_text(encoding="utf-8")))

    def test_every_relative_markdown_link_resolves(self) -> None:
        link = re.compile(r"\]\(([^)\s]+)\)")
        folders = (ROOT, ROOT / "docs", ROOT / "references", ROOT / "entrypoints")
        documents = {p for folder in folders for p in (folder.rglob("*.md") if folder != ROOT else folder.glob("*.md"))}
        for document in sorted(documents):
            for target in link.findall(document.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                with self.subTest(document=document.relative_to(ROOT).as_posix(), link=target):
                    self.assertTrue((document.parent / target.split("#", 1)[0]).exists())


if __name__ == "__main__":
    unittest.main()
