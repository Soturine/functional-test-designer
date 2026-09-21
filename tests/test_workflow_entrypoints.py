from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_entrypoints import INTENTS, dispatch, dispatch_request, normalize_intent  # noqa: E402


class WorkflowEntrypointTests(unittest.TestCase):
    def test_all_host_wrappers_are_thin_and_share_canonical_intents(self) -> None:
        for intent in INTENTS:
            name = intent.removeprefix("ftd-")
            self.assertTrue((ROOT / "entrypoints" / f"{name}.md").is_file())
            for host in (".cursor", ".claude"):
                text = (ROOT / host / "commands" / f"{intent}.md").read_text(encoding="utf-8")
                self.assertIn("shared core", text)
                self.assertNotIn("Coverage Point", text)

    def test_natural_generation_and_command_use_same_handoff(self) -> None:
        natural = dispatch_request(
            "Generate Test Cases from these files and give me only HTML.",
            sources=["requirements.md"], formats=["HTML"],
        )
        command = dispatch_request(
            "/ftd-gen requirements.md only HTML",
            sources=["requirements.md"], formats=["HTML"],
        )
        self.assertEqual(natural, command)
        self.assertEqual("shared-generation-core", natural["handoff"])

    def test_natural_language_is_primary_for_every_capability(self) -> None:
        examples = {
            "Ask me the important questions that are still ambiguous.": "ftd-clarify",
            "Audit whether the generated TCs are executable by someone who has never seen the product.": "ftd-check",
            "Render the last run as JSON and Markdown.": "ftd-render",
            "Prepare the last suite for Azure DevOps and show me the preview before writing anything.": "ftd-mcp",
        }
        for request, expected in examples.items():
            self.assertEqual(expected, normalize_intent(request))

    def test_slash_and_dollar_forms_are_only_aliases(self) -> None:
        for intent in INTENTS:
            self.assertEqual(intent, normalize_intent(f"/{intent}"))
            self.assertEqual(intent, normalize_intent(f"${intent}"))

    def test_mcp_entrypoint_falls_back_to_deterministic_preview(self) -> None:
        case = {
            "id": "TC-001", "title": "Create order", "priority": "HIGH", "status": "READY",
            "preconditions": [], "steps": [{"action": "Submit", "expected_result": "Created"}],
            "tags": [], "requirement_refs": ["REQ-001"], "coverage_point_refs": ["CP-001"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = dispatch(
                "ftd-mcp", cases=[case], mapping={}, project="Demo", plan="Regression",
                suite="Orders", artifact_root=Path(temporary), mcp_available=False,
            )
            self.assertEqual(1, len(result["create"]))
            self.assertEqual(3, len(result["fallback_exports"]))


if __name__ == "__main__":
    unittest.main()
