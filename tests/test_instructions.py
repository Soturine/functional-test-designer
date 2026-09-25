"""The instructions file (instructions.md / .txt): resolution, free-form sections,
precedence, and seeds that guide without becoming authority. Synthetic fixtures only."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import PackRun

import instructions
import pipeline
import workflow

ROOT = Path(__file__).resolve().parents[1]

FREE_FORM = """# Whatever the team wants

## Night shift worries
- an invitation accepted twice from two devices
- the owner leaves in the middle of an invite

## Things that scare QA
Seats running out while an invite is pending.

## Output
Only HTML please.
"""


class ResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.skill = self.root / "skill"
        for folder in (self.workspace / "docs", self.skill / "docs", self.root / "elsewhere"):
            folder.mkdir(parents=True)

    def resolve(self, explicit=None) -> Path:
        return instructions.resolve_input_file(explicit, workspace=self.workspace, skill_root=self.skill)

    def test_explicit_file_path_wins(self) -> None:
        (self.workspace / "docs" / "instructions.md").write_text("workspace", encoding="utf-8")
        chosen = self.root / "elsewhere" / "instructions.txt"
        chosen.write_text("explicit", encoding="utf-8")
        self.assertEqual(chosen.resolve(), self.resolve(chosen))

    def test_md_and_txt_are_the_runtime_names(self) -> None:
        for name in ("instructions.md", "instructions.txt", "INSTRUCTIONS.MD"):
            path = self.root / "elsewhere" / name
            path.write_text("x", encoding="utf-8")
            self.assertEqual(path.resolve(), self.resolve(path))
            path.unlink()

    def test_any_other_basename_is_a_clear_error(self) -> None:
        other = self.root / "elsewhere" / "notes.md"
        other.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(instructions.InstructionsError, "instructions.md / instructions.txt"):
            self.resolve(other)

    def test_explicit_directory_resolves_its_instructions_file_without_recursion(self) -> None:
        folder = self.root / "elsewhere"
        (folder / "nested").mkdir()
        (folder / "nested" / "instructions.md").write_text("deep", encoding="utf-8")
        with self.assertRaisesRegex(instructions.InstructionsError, "directory without"):
            self.resolve(folder)
        (folder / "instructions.md").write_text("top", encoding="utf-8")
        self.assertEqual((folder / "instructions.md").resolve(), self.resolve(folder))

    def test_two_instructions_files_in_one_directory_are_ambiguous(self) -> None:
        (self.workspace / "docs" / "instructions.md").write_text("a", encoding="utf-8")
        (self.workspace / "docs" / "instructions.txt").write_text("b", encoding="utf-8")
        with self.assertRaisesRegex(instructions.InstructionsError, "several instructions files"):
            self.resolve()

    def test_workspace_docs_precede_the_skill_default(self) -> None:
        (self.skill / "docs" / "instructions.md").write_text("skill", encoding="utf-8")
        self.assertEqual((self.skill / "docs" / "instructions.md").resolve(), self.resolve())
        (self.workspace / "docs" / "instructions.txt").write_text("workspace", encoding="utf-8")
        self.assertEqual((self.workspace / "docs" / "instructions.txt").resolve(), self.resolve())

    def test_missing_file_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(instructions.InstructionsError, "an instructions file is required"):
            self.resolve()

    def test_the_public_template_is_generic_and_says_sections_are_examples(self) -> None:
        text = (ROOT / "docs" / "instructions.md").read_text(encoding="utf-8")
        self.assertIn("Headings and wording are free-form: rename, delete or add sections", text)
        self.assertIn("This file is guidance, not authority", text)
        for role in ("FUNCTIONAL_AUTHORITY", "TECHNICAL_CONTEXT", "IMPLEMENTATION_EVIDENCE", "TEST_ASSET"):
            self.assertIn(role, text)
        self.assertIn("overrides this file", text)
        self.assertIn("recursively, but only inside itself", text)


class TextAndOutputTests(unittest.TestCase):
    def test_markdown_is_read_as_written_and_html_conversion_is_reduced_to_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            md = Path(temp) / "instructions.md"
            md.write_text(FREE_FORM, encoding="utf-8")
            self.assertEqual(FREE_FORM, instructions.load_input(md)["text"])
            html = Path(temp) / "instructions.html"
            html.write_text("<h2>Rollback</h2><ul><li>undo &amp; retry</li></ul><script>x()</script>", encoding="utf-8")
            self.assertEqual("## Rollback\n- undo & retry\n", instructions.load_input(html)["text"])

    def test_output_tokens_are_case_insensitive(self) -> None:
        self.assertEqual(["JSON", "MARKDOWN", "HTML"], instructions.parse_output("JSON,md,Html"))
        self.assertEqual(["MARKDOWN"], instructions.parse_output("markdown"))
        self.assertIsNone(instructions.parse_output(None))
        with self.assertRaises(instructions.InstructionsError):
            instructions.parse_output("pdf")

    def test_the_runtime_hardcodes_no_section_names(self) -> None:
        source = (ROOT / "scripts" / "instructions.py").read_text(encoding="utf-8").casefold()
        for heading in ('"flow"', '"chaos"', '"load"', '"device"', '"fluxo"', '"carga"'):
            self.assertNotIn(heading, source)


class GenerationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.input = self.run.workspace / "guide" / "instructions.md"
        self.input.parent.mkdir()
        self.input.write_text(FREE_FORM, encoding="utf-8")

    def normalized(self, **over) -> dict:
        document = instructions.load_input(self.input)
        request = {
            "schema_version": "1", "input_file": {"path": str(self.input), "digest": document["digest"]},
            "scope_root": str(self.run.workspace),
            "sources": [{"path": path, "role": item["role"]} for path, item in self.run.pack["sources"].items()],
            "output": {"formats": ["html"]},
            "reading": {"strategy": "MULTI_AGENT_PER_SOURCE", "worker_model": "haiku", "concurrency": 2},
            "guidance": ["Prefer realistic owner behavior."],
            "seeds": [{"text": "an invitation accepted twice from two devices", "section": "Night shift worries"},
                      {"text": "Seats running out while an invite is pending.", "section": "Things that scare QA"}],
        }
        request.update(over)
        return request

    def generate(self, normalized=None, **explicit) -> dict:
        return workflow.generate(input_file=self.input, normalized=normalized, explicit=explicit,
                                 workspace=self.run.workspace, run_id="gen")

    def test_first_phase_hands_the_host_the_text_and_the_contract(self) -> None:
        order = self.generate(output="json")
        self.assertEqual("NORMALIZE_INSTRUCTIONS", order["phase"])
        self.assertEqual(FREE_FORM, order["instructions_text"])
        self.assertEqual({"output": "json"}, order["explicit_overrides"])

    def test_arbitrary_headings_are_accepted_and_seeds_are_anchored(self) -> None:
        result = self.generate(self.normalized(), output_dir=str(self.run.artifacts))
        saved = json.loads(Path(result["normalized_request"]).read_text(encoding="utf-8"))
        self.assertEqual(["instructions.md#seed-001", "instructions.md#seed-002"], [s["anchor"] for s in saved["seeds"]])
        self.assertEqual("Night shift worries", saved["seeds"][0]["section"])
        self.assertEqual("reading", result["next_stage"])

    def test_explicit_cli_output_overrides_the_file_hint(self) -> None:
        result = self.generate(self.normalized(), output="json,md", output_dir=str(self.run.artifacts))
        run = json.loads((Path(result["run_dir"]) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(["JSON", "MARKDOWN"], run["formats"])
        self.assertEqual("EXPLICIT", result["provenance"]["formats"])
        self.assertEqual("INSTRUCTIONS", result["provenance"]["reading.worker_model"])

    def test_explicit_no_subagents_overrides_the_file_preference(self) -> None:
        result = self.generate(self.normalized(), reading_strategy="SEQUENTIAL", output_dir=str(self.run.artifacts))
        self.assertEqual("SEQUENTIAL", result["reading"]["strategy"])
        self.assertIsNone(result["reading"]["worker_model"])
        self.assertEqual("design", result["next_stage"])

    def test_file_hints_apply_when_nothing_explicit_is_given(self) -> None:
        result = self.generate(self.normalized(), output_dir=str(self.run.artifacts))
        run = json.loads((Path(result["run_dir"]) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(["HTML"], run["formats"])
        self.assertEqual({"strategy": "MULTI_AGENT_PER_SOURCE", "worker_model": "haiku", "concurrency": 2}, result["reading"])

    def test_seeds_reach_design_as_guidance_never_as_authority(self) -> None:
        result = self.generate(self.normalized(), reading_strategy="SEQUENTIAL", output_dir=str(self.run.artifacts))
        order = json.loads(Path(result["work_order"]).read_text(encoding="utf-8"))
        self.assertIn("never authority", order["user_guidance"]["note"].replace("not authority", "never authority"))
        self.assertEqual(2, len(order["user_guidance"]["seeds"]))
        sources = json.loads((Path(result["run_dir"]) / "sources.json").read_text(encoding="utf-8"))
        self.assertNotIn("guide/instructions.md", [r["path"] for r in sources["records"]])
        authority = {item["identifier"] for item in sources["authority_index"]}
        self.assertTrue(authority)
        self.assertFalse(any("seed" in ident.casefold() for ident in authority))

    def test_the_instructions_file_cannot_select_itself_as_a_source(self) -> None:
        request = self.normalized()
        request["sources"].append({"path": "guide/instructions.md", "role": "FUNCTIONAL_AUTHORITY"})
        with self.assertRaisesRegex(instructions.InstructionsError, "cannot select itself"):
            self.generate(request, output_dir=str(self.run.artifacts))

    def test_a_request_for_another_revision_of_the_file_is_rejected(self) -> None:
        request = self.normalized()
        self.input.write_text(FREE_FORM + "\n- one more idea\n", encoding="utf-8")
        with self.assertRaisesRegex(instructions.InstructionsError, "different revision"):
            self.generate(request, output_dir=str(self.run.artifacts))

    def test_unknown_request_keys_and_roles_are_rejected(self) -> None:
        with self.assertRaisesRegex(instructions.InstructionsError, "unknown keys"):
            self.generate(self.normalized(flow=["x"]), output_dir=str(self.run.artifacts))
        bad = self.normalized()
        bad["sources"][0]["role"] = "SEED"
        with self.assertRaisesRegex(instructions.InstructionsError, "requires a role"):
            self.generate(bad, output_dir=str(self.run.artifacts))


class ChaosSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.run.finalize(("JSON",))
        self.input = self.run.workspace / "instructions.md"
        self.input.write_text(FREE_FORM, encoding="utf-8")

    def normalized(self) -> dict:
        return {"input_file": {"digest": instructions.load_input(self.input)["digest"]},
                "seeds": [{"text": "an invitation accepted twice from two devices"},
                          {"text": "the owner leaves in the middle of an invite"}]}

    def test_chaos_with_an_instructions_file_is_two_phase_and_seeds_are_item_level(self) -> None:
        order = workflow.chaos(self.run.run_dir, input_file=self.input)
        self.assertEqual("chaos", order["command"])
        started = workflow.chaos(self.run.run_dir, input_file=self.input, normalized=self.normalized())
        self.assertEqual(2, started["seed_items_received"])
        work = json.loads(Path(started["work_order"]).read_text(encoding="utf-8"))
        anchors = [item["anchor"] for seed in work["seeds"] for item in seed["items"]]
        self.assertEqual(["instructions.md#seed-001", "instructions.md#seed-002"], anchors)

    def test_chaos_runs_are_isolated_and_the_canonical_suite_is_untouched(self) -> None:
        from common import file_digest
        before = file_digest(self.run.run_dir / "canonical-suite.json")
        first = workflow.chaos(self.run.run_dir)
        second = workflow.chaos(self.run.run_dir)
        self.assertNotEqual(first["challenge_dir"], second["challenge_dir"])
        self.assertEqual(before, file_digest(self.run.run_dir / "canonical-suite.json"))

    def test_chaos_requires_a_finalized_parent(self) -> None:
        fresh = PackRun("saas-accounts")
        self.addCleanup(fresh.close)
        fresh.through("design")
        with self.assertRaises(ValueError):
            workflow.chaos(fresh.run_dir)

    def test_finalize_publishes_the_requested_chaos_outputs(self) -> None:
        import challenge
        started = workflow.chaos(self.run.run_dir, input_file=self.input, normalized=self.normalized(), output="md,html")
        chaos_id = Path(started["challenge_dir"]).name
        challenge.submit_challenge(self.run.run_dir, chaos_id, {
            "cases": [{"key": "H1", "title": "Invitation accepted twice from two devices", "discovery": "HUMAN_AND_MODEL",
                       "inspired_by": ["instructions.md#seed-001"],
                       "rationale": "Two devices racing on one invitation could add the member twice.",
                       "execution_tags": ["MANUAL"]}],
            "seed_dispositions": [
                {"seed_ref": "instructions.md#seed-001", "disposition": "MATERIALIZED", "cases": ["H1"]},
                {"seed_ref": "instructions.md#seed-002", "disposition": "QUESTIONED",
                 "summary": "No evidence says what happens to pending invites when an owner leaves."},
            ],
        })
        result = challenge.finalize_challenge(self.run.run_dir, chaos_id)
        destination = self.run.artifacts / "output" / "chaos" / chaos_id
        self.assertEqual({"chaos-plan.md", "chaos-plan.html"}, {Path(p).name for p in result["published"]})
        html = (destination / "chaos-plan.html").read_text(encoding="utf-8")
        self.assertIn("<h1>Manual / Physical / Field Test Plan</h1>", html)
        self.assertNotIn("http", html.replace("http-equiv", ""))


if __name__ == "__main__":
    unittest.main()
