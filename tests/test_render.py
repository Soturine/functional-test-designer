from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LegacySuiteRenderTests(unittest.TestCase):
    """Schema 1.2 suites stay renderable; rendering never changes JSON."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def render_all(self) -> str:
        render.render_markdown(self.output)
        return render.render_report(self.output).read_text(encoding="utf-8")

    def test_offline_html_without_changing_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path: digest(path) for path in json_files}
        report = self.render_all()
        self.assertEqual(before, {path: digest(path) for path in json_files})
        self.assertIn("Submit a create-order request", report)
        self.assertIn('href="test-cases/TC-001.json"', report)
        self.assertIn('href="test-cases-md/TC-010.md"', report)
        self.assertEqual(0, report.count('class="tc-card"'))
        self.assertEqual(11, report.count('class="tc-template"'))
        for forbidden in ("https://", "<script src=", "unpkg", "jsdelivr", "mermaid.min.js", 'src="http'):
            self.assertNotIn(forbidden, report)

    def test_one_markdown_per_case_contains_every_step(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        rendered = render.render_markdown(self.output)
        self.assertEqual(len(index["test_cases"]), len(rendered))
        for entry in index["test_cases"]:
            case = json.loads((self.output / entry["file"]).read_text(encoding="utf-8"))
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            for step in case["steps"]:
                self.assertIn(step["action"], markdown)

    def test_mermaid_is_last_linear_and_identical_in_html(self) -> None:
        report = self.render_all()
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        for entry in index["test_cases"]:
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            mermaid = render.extract_mermaid(markdown)
            self.assertTrue(markdown.rstrip().endswith("```"))
            self.assertNotIn("-->|", mermaid)
            self.assertIn(render.esc(mermaid), report)
        self.assertEqual(len(index["test_cases"]), report.count('class="mermaid-svg"'))

    def test_missing_expected_result_is_marked_without_invention(self) -> None:
        case = json.loads((self.output / "test-cases/TC-010.json").read_text(encoding="utf-8"))
        case["steps"][0]["expected_result"] = None
        case["steps"][0]["needs_clarification"] = True
        labels = render.LABELS["en"]
        source = render.mermaid_source(case, labels)
        self.assertIn(labels["needs_answer"], source)
        self.assertIn("class C1 clarification", source)

    def test_mermaid_labels_wrap_and_sanitize(self) -> None:
        label = "Confirm the synthetic reservation and then inspect the resulting availability for the selected item"
        wrapped = render._mermaid_label(label, width=50)
        self.assertIn("<br/>", wrapped)
        self.assertEqual(label, wrapped.replace("<br/>", " "))
        sanitized = render._mermaid_label('<script>"bad" [node] {shape} | value & more')
        for token in ("<script>", '"', "[", "]", "{", "}", "|"):
            self.assertNotIn(token, sanitized)

    def test_source_content_is_escaped(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        case = json.loads((self.output / "test-cases/TC-001.json").read_text(encoding="utf-8"))
        case["steps"][0]["action"] = '<script>alert("x")</script>'
        labels = render.labels_for(index)
        html = render.render_case_body(
            case, index["test_cases"][0], render.mermaid_source(case, labels), labels,
            {item["id"]: item for item in index["requirements"]}, "Group", {"JSON"},
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_a_case_ending_with_a_script_close_tag_cannot_break_out_of_its_template(self) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        case = json.loads((self.output / "test-cases/TC-001.json").read_text(encoding="utf-8"))
        case["title"] = '</script><script>alert(1)</script>'
        labels = render.labels_for(index)
        html = render.render_case_template(
            case, index["test_cases"][0], render.mermaid_source(case, labels), labels,
            {item["id"]: item for item in index["requirements"]}, "G", "Group", set(), {"JSON"},
        )
        self.assertNotIn("</script><script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_refuses_missing_or_divergent_markdown(self) -> None:
        render.render_markdown(self.output)
        markdown = self.output / "test-cases-md/TC-001.md"
        markdown.write_text(markdown.read_text(encoding="utf-8").replace("Submit", "Send"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs"):
            render.render_report(self.output)
        markdown.unlink()
        with self.assertRaisesRegex(ValueError, "Missing Markdown artifact"):
            render.render_report(self.output)

    def test_renderer_refuses_invalid_output(self) -> None:
        (self.output / "test-cases" / "TC-001.json").unlink()
        with self.assertRaisesRegex(ValueError, "Output validation failed"):
            render.render_report(self.output)


class ModalReviewGlossaryTests(unittest.TestCase):
    """v2.4 HTML UX round: one-Test-Case-at-a-time modal, local review toggle, glossary."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)
        self.addCleanup(self.temp_dir.cleanup)

    def render_all(self) -> str:
        render.render_markdown(self.output)
        return render.render_report(self.output).read_text(encoding="utf-8")

    def test_group_cards_open_a_modal_instead_of_expanding_inline(self) -> None:
        report = self.render_all()
        self.assertIn('class="open-group"', report)
        self.assertNotIn('class="group-toggle"', report)
        self.assertNotIn("id=\"expand-all\"", report)

    def test_modal_structure_has_pagination_counter_and_close(self) -> None:
        report = self.render_all()
        self.assertIn('id="tc-modal"', report)
        self.assertIn('id="tc-modal-body"', report)
        self.assertIn('id="tc-prev"', report)
        self.assertIn('id="tc-next"', report)
        self.assertIn('id="tc-position"', report)
        self.assertIn('id="tc-modal-close"', report)

    def test_only_one_template_per_case_no_visible_expanded_duplicate_card(self) -> None:
        report = self.render_all()
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["test_cases"]), report.count('class="tc-template"'))
        self.assertEqual(0, report.count('class="tc-content"') - report.count('<template class="tc-template"'))

    def test_review_toggle_control_exists_with_report_scoped_and_tc_scoped_storage_key(self) -> None:
        report = self.render_all()
        self.assertIn('id="tc-review-toggle"', report)
        self.assertIn("REPORT_NS=", report.replace(" ", ""))
        self.assertIn("functionstorageKey(id){returnREPORT_NS+':'+id;}", report.replace(" ", ""))
        # The namespace must not be a bare literal like just "review": it is derived from
        # the run's generated_at so unrelated reports never collide on the same TC id.
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertIn(json.dumps(str(index["generated_at"])), report)

    def test_rendering_and_reviewing_never_touches_canonical_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path: digest(path) for path in json_files}
        self.render_all()
        after = {path: digest(path) for path in json_files}
        self.assertEqual(before, after)
        report = (self.output / "report.html").read_text(encoding="utf-8")
        self.assertNotIn('"accepted"', report)  # no canonical-looking review field was introduced

    def test_localstorage_failure_is_handled_safely(self) -> None:
        report = self.render_all()
        self.assertIn("try{", report.replace(" ", ""))
        self.assertIn("catch(e){}", report.replace(" ", "").replace("catch(e){return false;}", "catch(e){}"))

    def test_modal_is_a_native_accessible_dialog_with_escape_and_focus_return(self) -> None:
        report = self.render_all()
        self.assertIn('<dialog id="tc-modal"', report)
        self.assertIn('aria-labelledby="tc-modal-title"', report)
        self.assertIn("tcModal.showModal()", report)
        self.assertIn("tcState.opener.focus()", report)

    def test_keyboard_arrow_navigation_is_wired_and_ignores_form_controls(self) -> None:
        report = self.render_all()
        self.assertIn("ArrowLeft", report)
        self.assertIn("ArrowRight", report)
        self.assertIn("['INPUT','SELECT','TEXTAREA']", report)

    def test_glossary_section_defines_the_major_report_terms_in_portuguese(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["output_locale"] = "pt-BR"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        self.assertIn('id="glossary"', report)
        for term in (
            "Findings", "Normativos", "Derivados", "Cobertura", "CRITICAL", "HIGH",
            "READY", "NEEDS_REVIEW", "BLOCKED", "Exploratório", "Automação pronta",
        ):
            self.assertIn(term, report)

    def test_glossary_in_english_locale_uses_english_terms(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["output_locale"] = "en-US"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        for term in ("Findings", "Derived", "Coverage", "Normative", "Automation ready"):
            self.assertIn(term, report)

    def test_no_external_cdn_or_network_dependency_was_added(self) -> None:
        report = self.render_all()
        for forbidden in ("https://", "http://cdn", "<script src=", "unpkg.com", "jsdelivr.net"):
            self.assertNotIn(forbidden, report)

    def test_existing_filters_remain_present_and_reusable_by_the_modal_controller(self) -> None:
        report = self.render_all()
        for control_id in ("search", "status-filter", "priority-filter", "family-filter", "feature-filter"):
            self.assertIn(f'id="{control_id}"', report)
        self.assertIn("function matches(tpl)", report)
        self.assertIn("openGroup(", report)

    def test_markdown_output_is_unaffected_by_the_modal_change(self) -> None:
        rendered = render.render_markdown(self.output)
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["test_cases"]), len(rendered))
        for entry in index["test_cases"]:
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            self.assertNotIn("tc-modal", markdown)
            self.assertNotIn("<template", markdown)


class OfficialTitleTests(unittest.TestCase):
    def test_label_uses_stored_identifier_and_title_only(self) -> None:
        requirement = {
            "id": "REQ-001", "statement": "x", "source_identifier": "RF-7", "source_title": "Consulta de Saldo",
            "source_refs": [{"source": "a.md", "reference": "RF-7 header"}],
        }
        self.assertEqual("RF-7 — Consulta de Saldo", render.requirement_label(requirement))

    def test_reference_text_is_never_parsed_into_a_title(self) -> None:
        requirement = {"id": "REQ-002", "statement": "x", "source_refs": [{"source": "a.md", "reference": "RF-8 header"}]}
        label = render.requirement_label(requirement)
        self.assertEqual("REQ-002", label)
        self.assertNotIn("header", label)


if __name__ == "__main__":
    unittest.main()
