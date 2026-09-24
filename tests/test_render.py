from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

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
            {item["id"]: item for item in index["requirements"]}, "G", "Group", set(), {"JSON"}, {}, {},
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


class RequirementModalTests(unittest.TestCase):
    """v2.4 corrective UX round: modal paginates by requirement identifier, not by TC;
    TCs are accordion rows (disclosure state only, no review/localStorage concept)."""

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
        self.assertNotIn('id="expand-all"', report)

    def test_modal_structure_has_requirement_navigation_and_close(self) -> None:
        report = self.render_all()
        self.assertIn('id="tc-modal"', report)
        self.assertIn('id="tc-modal-body"', report)
        self.assertIn('id="tc-modal-title"', report)
        self.assertIn('id="tc-prev"', report)
        self.assertIn('id="tc-next"', report)
        self.assertIn('id="tc-position"', report)
        self.assertIn('id="tc-modal-close"', report)

    def test_pagination_is_by_requirement_not_by_test_case(self) -> None:
        report = self.render_all()
        self.assertIn('class="req-template"', report)
        self.assertIn('data-key=', report)
        self.assertIn('reqTemplates', report)
        self.assertIn('tcState.pages', report)
        # no leftover TC-level pagination state from the previous round
        self.assertNotIn('tcState.items', report)

    def test_one_family_with_three_identifiers_reports_1_of_3(self) -> None:
        # source_identifiers is additive metadata (unlike requirement_refs it carries no
        # cross-file coverage obligation), so it is the safe way to give one legacy-schema
        # family three distinct official identifiers without disturbing normative coverage.
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        # TC-002..TC-004 already share one requirement (REQ-002), so they already share one
        # family group; only their identifiers need to differ to prove the group now has 3 pages.
        same_group = [tc for tc in index["test_cases"] if tc["requirement_refs"] == ["REQ-002"]][:3]
        self.assertEqual(3, len(same_group))
        for tc, identifier in zip(same_group, ("SYN-A", "SYN-B", "SYN-C")):
            case_path = self.output / tc["file"]
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["source_identifiers"] = [identifier]
            case_path.write_text(json.dumps(case), encoding="utf-8")
        report = self.render_all()
        self.assertIn('POS_OF', report)
        self.assertGreaterEqual(report.count('class="req-template"'), 3)
        self.assertIn('data-key="SYN-A"', report)
        self.assertIn('data-key="SYN-B"', report)
        self.assertIn('data-key="SYN-C"', report)

    def test_no_tc_level_previous_next_pagination_remains(self) -> None:
        report = self.render_all()
        self.assertNotIn('renderCurrentCase', report)
        self.assertNotIn('tc-modal-family', report)

    def test_all_tcs_for_a_requirement_are_lightweight_accordion_rows(self) -> None:
        report = self.render_all()
        self.assertIn('class="tc-row"', report)
        self.assertIn('class="tc-row-toggle"', report)
        self.assertIn('aria-expanded="false"', report)
        self.assertIn('class="tc-row-body"', report)

    def test_full_tc_body_is_materialized_only_when_the_row_is_opened(self) -> None:
        report = self.render_all()
        self.assertIn('tpl.content.cloneNode(true)', report)
        self.assertIn("body.dataset.materialized", report)
        # exactly one full body per TC, in its own global template — never duplicated per row
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["test_cases"]), report.count('class="tc-template"'))
        self.assertEqual(0, report.count('class="tc-content"') - report.count('<template class="tc-template"'))

    def test_no_review_checkbox_or_localstorage_code_remains(self) -> None:
        report = self.render_all()
        for gone in (
            "tc-review-toggle", "REPORT_NS", "localStorage", "clear-review",
            "Aceito / Fechado", "Accepted / Closed", "Pendente", "isClosed", "setClosed",
        ):
            self.assertNotIn(gone, report)

    def test_multi_requirement_tc_appears_on_each_relevant_requirement_page_without_cloning_canonical_data(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        json_before = json.loads(json.dumps(index))
        tc_entry = index["test_cases"][0]
        case_path = self.output / tc_entry["file"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        # source_identifiers (not requirement_refs) is what drives requirement-page keys;
        # two identifiers on one TC is exactly the "same TC, several pages" scenario.
        case["source_identifiers"] = ["SYN-X", "SYN-Y"]
        case_path.write_text(json.dumps(case), encoding="utf-8")
        report = self.render_all()
        self.assertGreaterEqual(report.count(f'data-id="{case["id"]}"'), 2)
        self.assertEqual(1, report.count(f'id="tc-tpl-{case["id"]}"'))  # one global body, never cloned
        after = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(json_before["test_cases"], after["test_cases"])  # index itself untouched by rendering

    def test_finding_indicator_and_detail_appear_on_the_linked_tc(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["findings"] = [{
            "id": "FND-900", "type": "IMPLEMENTATION_DIVERGENCE",
            "statement": "The implementation allows X while the authority defines Y.",
            "requirement_refs": [index["requirements"][0]["id"]], "related_test_cases": [index["test_cases"][0]["id"]],
            "source_refs": [{"source": "examples/selected-source/order_service.py", "reference": "line 10"}],
        }]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        tc_entry = index["test_cases"][0]
        case_path = self.output / tc_entry["file"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case["finding_refs"] = ["FND-900"]
        case_path.write_text(json.dumps(case), encoding="utf-8")
        other_case_path = self.output / index["test_cases"][1]["file"]
        other_case = json.loads(other_case_path.read_text(encoding="utf-8"))
        self.assertNotIn("finding_refs", other_case)  # nothing else was touched
        report = self.render_all()
        self.assertIn("FND-900", report)
        self.assertIn("IMPLEMENTATION_DIVERGENCE", report)
        self.assertIn("The implementation allows X while the authority defines Y.", report)
        self.assertIn('class="tc-alerts"', report)
        self.assertIn("1 Finding", report)

    def test_question_indicator_and_detail_appear_on_the_linked_tc(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        questions_path = self.output / "questions.json"
        questions = json.loads(questions_path.read_text(encoding="utf-8"))
        questions["questions"] = questions.get("questions", []) + [{
            "id": "Q-900", "question": "What happens on a duplicate submission?",
            "reason": "The authority does not define duplicate-submission behavior.",
            "blocking": True, "impact": "EXPECTED_RESULT",
            "requirement_refs": [index["requirements"][0]["id"]], "related_test_cases": [index["test_cases"][0]["id"]],
            "source_refs": [{"source": "examples/selected-source/order_service.py", "reference": "section 2"}],
        }]
        questions_path.write_text(json.dumps(questions), encoding="utf-8")
        index["test_cases"][0]["status"] = "BLOCKED"  # a blocking Question needs a BLOCKED TC (schema 1.2 uses the literal status)
        index_path.write_text(json.dumps(index), encoding="utf-8")
        tc_entry = index["test_cases"][0]
        case_path = self.output / tc_entry["file"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case["question_refs"] = ["Q-900"]
        case["status"] = "BLOCKED"
        case_path.write_text(json.dumps(case), encoding="utf-8")
        report = self.render_all()
        self.assertIn("Q-900", report)
        self.assertIn("What happens on a duplicate submission?", report)
        self.assertIn("The authority does not define duplicate-submission behavior.", report)
        self.assertIn("blocking", report)  # question-item blocking styling class present

    def test_unrelated_tc_does_not_show_a_finding_it_is_not_linked_to(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["findings"] = [{
            "id": "FND-901", "type": "COVERAGE_GAP", "statement": "Only linked to TC-001.",
            "requirement_refs": [], "related_test_cases": [index["test_cases"][0]["id"]],
            "source_refs": [{"source": "examples/selected-source/order_service.py", "reference": "n/a"}],
        }]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        case_path = self.output / index["test_cases"][0]["file"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case["finding_refs"] = ["FND-901"]
        case_path.write_text(json.dumps(case), encoding="utf-8")
        render.render_markdown(self.output)
        render.render_report(self.output)
        # The TC's own template carries the alert; every other TC's template must not.
        other = json.loads((self.output / index["test_cases"][1]["file"]).read_text(encoding="utf-8"))
        labels = render.labels_for(index)
        requirements = {item["id"]: item for item in index["requirements"]}
        other_body = render.render_case_body(
            other, index["test_cases"][1], render.mermaid_source(other, labels), labels, requirements,
            "Group", {"JSON"}, {"FND-901": index["findings"][0]}, {},
        )
        self.assertNotIn("FND-901", other_body)

    def test_glossary_covers_expansion_and_blocking_question_in_portuguese(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["output_locale"] = "pt-BR"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        self.assertIn('id="glossary"', report)
        for term in (
            "Findings", "Normativos", "Derivados", "Cobertura", "CRITICAL", "HIGH",
            "READY", "NEEDS_REVIEW", "BLOCKED", "Exploratório", "Automação pronta",
            "Pergunta bloqueante", "Candidatos", "Materializados", "Já cobertos", "Não aplicável",
        ):
            self.assertIn(term, report)
        for code in render.EXPANSION_DIMENSION_INFO["pt"]:
            self.assertIn(code, report)

    def test_glossary_in_english_locale_uses_english_terms(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["output_locale"] = "en-US"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        for term in ("Findings", "Derived", "Coverage", "Normative", "Automation ready", "Blocking Question"):
            self.assertIn(term, report)

    def test_expansion_columns_are_explained_and_all_17_dimensions_documented(self) -> None:
        report = self.render_all()
        self.assertIn('class="expansion-help"', report)
        self.assertIn('class="expansion-legend"', report)
        for code in render.EXPANSION_DIMENSION_INFO["en"]:
            self.assertIn(code, report)
            label, _ = render.EXPANSION_DIMENSION_INFO["en"][code]
            self.assertIn(label, report)

    def test_expansion_metric_values_are_unchanged_by_the_explanatory_ui(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["expansion_summary"] = [{
            "dimension": "BOUNDARY", "evaluated": True, "candidates_considered": 4, "materialized": 2,
            "already_covered": 1, "question_required": 1, "not_applicable": 0,
        }]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        self.assertIn(">4<", report)
        self.assertIn(">2<", report)

    def test_filters_remove_requirement_pages_with_zero_matches_no_silent_fallback(self) -> None:
        report = self.render_all()
        self.assertIn("matchesId", report)
        self.assertIn(".filter(p=>p.matchedIds.length>0)", report)
        self.assertNotIn("matched.length===0)matched=own", report)  # no more "fall back to the whole group" behavior
        self.assertIn(render.LABELS["en"]["no_filter_results"], report)

    def test_no_matches_state_message_exists_in_both_locales(self) -> None:
        report_en = self.render_all()
        self.assertIn(render.LABELS["en"]["no_filter_results"], report_en)
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["output_locale"] = "pt-BR"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report_pt = self.render_all()
        self.assertIn(render.LABELS["pt"]["no_filter_results"], report_pt)

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

    def test_no_external_cdn_or_network_dependency_was_added(self) -> None:
        report = self.render_all()
        for forbidden in ("https://", "http://cdn", "<script src=", "unpkg.com", "jsdelivr.net"):
            self.assertNotIn(forbidden, report)

    def test_existing_filters_remain_present_and_reusable_by_the_modal_controller(self) -> None:
        report = self.render_all()
        for control_id in ("search", "status-filter", "priority-filter", "family-filter", "feature-filter"):
            self.assertIn(f'id="{control_id}"', report)
        self.assertIn("function matchesTemplate(tpl)", report)
        self.assertIn("openGroup(", report)

    def test_malicious_finding_statement_and_question_text_cannot_inject_script(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["findings"] = [{
            "id": "FND-902", "type": "COVERAGE_GAP",
            "statement": '</script><script>alert(1)</script>',
            "requirement_refs": [], "related_test_cases": [index["test_cases"][0]["id"]],
            "source_refs": [{"source": "examples/selected-source/order_service.py", "reference": "n/a"}],
        }]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        case_path = self.output / index["test_cases"][0]["file"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case["finding_refs"] = ["FND-902"]
        case_path.write_text(json.dumps(case), encoding="utf-8")
        questions_path = self.output / "questions.json"
        questions = json.loads(questions_path.read_text(encoding="utf-8"))
        questions["questions"] = questions.get("questions", []) + [{
            "id": "Q-902", "question": '</script><script>alert(2)</script>',
            "reason": '</script><script>alert(3)</script>', "blocking": False, "impact": "EXPECTED_RESULT",
            "requirement_refs": [index["requirements"][0]["id"]], "related_test_cases": [index["test_cases"][0]["id"]],
            "source_refs": [{"source": "examples/selected-source/order_service.py", "reference": "n/a"}],
        }]
        questions_path.write_text(json.dumps(questions), encoding="utf-8")
        case["question_refs"] = ["Q-902"]
        case_path.write_text(json.dumps(case), encoding="utf-8")
        report = self.render_all()
        self.assertNotIn("</script><script>", report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", report)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", report)
        self.assertIn("&lt;script&gt;alert(3)&lt;/script&gt;", report)

    def test_malicious_requirement_title_cannot_inject_script(self) -> None:
        index_path = self.output / "test-cases.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["requirements"][0]["source_title"] = '</script><script>alert(4)</script>'
        index["requirements"][0]["source_identifier"] = "REQ-X"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        report = self.render_all()
        self.assertNotIn("</script><script>", report)
        self.assertIn("&lt;script&gt;alert(4)&lt;/script&gt;", report)

    def test_rendering_never_touches_canonical_json(self) -> None:
        json_files = sorted(self.output.rglob("*.json"))
        before = {path: digest(path) for path in json_files}
        self.render_all()
        after = {path: digest(path) for path in json_files}
        self.assertEqual(before, after)

    def test_markdown_output_is_unaffected_by_the_modal_change(self) -> None:
        rendered = render.render_markdown(self.output)
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["test_cases"]), len(rendered))
        for entry in index["test_cases"]:
            markdown = (self.output / entry["markdown_file"]).read_text(encoding="utf-8")
            self.assertNotIn("tc-modal", markdown)
            self.assertNotIn("<template", markdown)

    def test_other_report_sections_still_render(self) -> None:
        report = self.render_all()
        for section_id in ("summary", "test-cases", "merge", "findings", "questions", "coverage", "expansion", "gates"):
            self.assertIn(f'id="{section_id}"', report)


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


class _FamilyPages(HTMLParser):
    """Collects, per family card, its announced count and each modal page's TC ids."""

    def __init__(self) -> None:
        super().__init__()
        self.families: dict[str, dict[str, Any]] = {}
        self._family: str | None = None
        self._page: dict[str, Any] | None = None
        self._in_count = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "section" and "tc-group" in classes:
            self._family = a["data-family"]
            self.families[self._family] = {"count": None, "pages": []}
        elif tag == "template" and "req-template" in classes:
            self._page = {"scope": a.get("data-scope"), "key": a.get("data-key"), "title": a.get("data-title"), "ids": []}
            self.families[a["data-family"]]["pages"].append(self._page)
        elif tag == "li" and "tc-row" in classes and self._page is not None:
            self._page["ids"].append(a["data-id"])
        elif tag == "span" and "tc-count" in classes:
            self._in_count = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "template":
            self._page = None

    def handle_data(self, data: str) -> None:
        if self._in_count and self._family:
            self.families[self._family]["count"] = int(data)
            self._in_count = False


class FamilyModalTests(unittest.TestCase):
    """A family card's "View Test Cases" opens on every unique TC the card counts; the
    identifier pages only refine that view."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)
        self.addCleanup(self.temp_dir.cleanup)

    def families(self) -> dict[str, dict[str, Any]]:
        render.render_markdown(self.output)
        parser = _FamilyPages()
        parser.feed(render.render_report(self.output).read_text(encoding="utf-8"))
        return parser.families

    def _identifiers(self, mapping: dict[str, list[str]]) -> None:
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        for entry in index["test_cases"]:
            if entry["id"] in mapping:
                path = self.output / entry["file"]
                case = json.loads(path.read_text(encoding="utf-8"))
                case["source_identifiers"] = mapping[entry["id"]]
                path.write_text(json.dumps(case), encoding="utf-8")

    def _family_of(self, families: dict[str, dict[str, Any]], tc: str) -> dict[str, Any]:
        return next(f for f in families.values() if tc in f["pages"][0]["ids"])

    def test_first_page_is_the_whole_family_with_exactly_the_card_count(self) -> None:
        for family in self.families().values():
            first = family["pages"][0]
            self.assertEqual("all", first["scope"])
            self.assertEqual(family["count"], len(first["ids"]))
            self.assertEqual(len(first["ids"]), len(set(first["ids"])))

    def test_identifier_pages_are_subsets_of_the_family(self) -> None:
        self._identifiers({"TC-002": ["SYN-A"], "TC-003": ["SYN-A", "SYN-B"], "TC-004": ["SYN-B"]})
        family = self._family_of(self.families(), "TC-002")
        pages = {p["key"]: p["ids"] for p in family["pages"][1:]}
        self.assertEqual(["TC-002", "TC-003"], pages["SYN-A"])
        self.assertEqual(["TC-003", "TC-004"], pages["SYN-B"])
        for ids in pages.values():
            self.assertLessEqual(set(ids), set(family["pages"][0]["ids"]))

    def test_multi_identifier_tc_appears_once_in_the_all_view(self) -> None:
        self._identifiers({"TC-002": ["SYN-A"], "TC-003": ["SYN-A", "SYN-B"], "TC-004": ["SYN-B"]})
        family = self._family_of(self.families(), "TC-003")
        self.assertEqual(1, family["pages"][0]["ids"].count("TC-003"))
        self.assertEqual(family["count"], len(family["pages"][0]["ids"]))
        on_pages = sum("TC-003" in p["ids"] for p in family["pages"][1:])
        self.assertEqual(2, on_pages)

    def test_card_count_equals_the_default_view_for_a_large_family(self) -> None:
        # Every TC with its own identifier: the first identifier page holds one TC, the
        # default page still holds the whole family.
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        self._identifiers({entry["id"]: [f"SYN-{n}"] for n, entry in enumerate(index["test_cases"])})
        for family in self.families().values():
            self.assertEqual(family["count"], len(family["pages"][0]["ids"]))
            self.assertEqual(len(family["pages"][0]["ids"]), sum(len(p["ids"]) for p in family["pages"][1:]))

    def test_modal_controller_defaults_to_the_all_page_and_keeps_navigation(self) -> None:
        render.render_markdown(self.output)
        report = render.render_report(self.output).read_text(encoding="utf-8")
        self.assertIn("tcState.index=0", report)
        self.assertIn('id="tc-page-select"', report)
        self.assertIn("page.scope==='all'", report)
        for wired in ("q('tc-prev').addEventListener", "q('tc-next').addEventListener",
                      "q('tc-page-select').addEventListener", ".filter(p=>p.matchedIds.length>0)"):
            self.assertIn(wired, report)
        for forbidden in ("https://", "<script src=", "unpkg", "jsdelivr"):
            self.assertNotIn(forbidden, report)



def _member(case: str, order: int, origin: str = "CANONICAL", **extra: str) -> dict[str, Any]:
    return {"case": case, "origin": origin, "via": "test", "order": order, **extra}


class ExecutionViewTests(unittest.TestCase):
    """An organization publishes views over the same Test Cases: the report shows them
    as tabs, in placement order, with post-suite cases discoverable and nothing cloned."""

    CHAOS = {"id": "CH-001", "key": "chaos-001:CH-001", "chaos_run_id": "chaos-001", "parent_run_id": "run-a",
             "title": "Dependency outage during submission", "rationale": "A dependency drops mid-request.",
             "related_test_cases": ["TC-002"], "execution_tags": ["CHAOS_RECOVERY"], "priority": "HIGH",
             "preconditions": ["Dependency reachable"], "test_data": [{"name": "ORDER_A", "description": "A valid order"}],
             "steps": [{"action": "Stop the dependency during submission", "expected_result": "The request fails cleanly"}],
             "postconditions": ["No partial order persists"], "unknowns": [], "notes": []}

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "output"
        shutil.copytree(ROOT / "examples" / "expected-output", self.output)
        self.addCleanup(self.temp_dir.cleanup)
        organization = {"schema_version": "1", "groups": [
            {"id": "REQ002", "kind": "FUNCTIONAL", "label": "REQ-002", "identifier": "REQ-002",
             "flow_reference": "UC-9", "order_source": "USE_CASE_MAIN_FLOW",
             "members": [_member("TC-004", 1), _member("TC-002", 2),
                         _member("CH-001", 3, "POST_SUITE", chaos_run_id="chaos-001"), _member("TC-003", 4)]},
            {"id": "LOAD_CONCURRENCY", "kind": "EXECUTION_VIEW", "label": "Load", "order_source": "EXECUTION_ORDER",
             "members": [_member("TC-003", 1)]},
            {"id": "CHAOS_RESILIENCE", "kind": "EXECUTION_VIEW", "label": "Chaos", "order_source": "EXECUTION_ORDER",
             "members": [_member("CH-001", 1, "POST_SUITE", chaos_run_id="chaos-001")]}],
            "memberships": {}, "post_suite_cases": [self.CHAOS]}
        (self.output / "organization.json").write_text(json.dumps(organization), encoding="utf-8")

    def render_all(self) -> str:
        render.render_markdown(self.output)
        return render.render_report(self.output).read_text(encoding="utf-8")

    def groups(self, report: str) -> dict[str, dict[str, Any]]:
        parser = _FamilyPages()
        parser.feed(report)
        return parser.families

    def test_views_are_tabs_and_the_functional_view_is_the_default(self) -> None:
        report = self.render_all()
        tabs = report[report.index('class="view-tabs"'):]
        order = [tabs.index(f'data-view="{view}"') for view in ("functional", "families", "load_concurrency",
                                                               "chaos_resilience", "all")]
        self.assertEqual(sorted(order), order)
        self.assertIn('<div class="case-view" data-view="functional">', report)
        self.assertIn('<div class="case-view" data-view="families" hidden>', report)

    def test_the_functional_group_follows_placement_order_not_canonical_order(self) -> None:
        pages = self.groups(self.render_all())["functional:REQ002"]["pages"]
        self.assertEqual("all", pages[0]["scope"])
        self.assertEqual(["TC-004", "TC-002", "chaos-001:CH-001", "TC-003"], pages[0]["ids"])

    def test_every_card_count_equals_its_whole_group_page(self) -> None:
        for group in self.groups(self.render_all()).values():
            self.assertEqual(group["count"], len(group["pages"][0]["ids"]))

    def test_a_post_suite_case_is_discoverable_with_its_own_body(self) -> None:
        report = self.render_all()
        self.assertIn('id="tc-tpl-chaos-001:CH-001"', report)
        self.assertIn("Stop the dependency during submission", report)
        self.assertEqual(["chaos-001:CH-001"], self.groups(report)["chaos_resilience:CHAOS_RESILIENCE"]["pages"][0]["ids"])

    def test_views_reference_cases_without_cloning_their_templates(self) -> None:
        report = self.render_all()
        self.assertEqual(12, report.count('class="tc-template"'))  # 11 canonical + 1 post-suite
        self.assertEqual(1, report.count('id="tc-tpl-TC-003"'))
        groups = self.groups(report)
        self.assertIn("TC-003", groups["load_concurrency:LOAD_CONCURRENCY"]["pages"][0]["ids"])
        self.assertEqual(11 + 1, len(groups["all:ALL"]["pages"][0]["ids"]))

    def test_modal_position_names_the_view_page_not_the_family(self) -> None:
        report = self.render_all()
        self.assertIn("PAGE_LABEL+' '+(tcState.index+1)+POS_OF", report)
        self.assertNotIn("page.key+' · '+(tcState.index+1)", report)
        self.assertIn('const PAGE_LABEL="View"', report)

    def test_without_an_organization_the_report_has_no_view_tabs(self) -> None:
        (self.output / "organization.json").unlink()
        report = self.render_all()
        self.assertNotIn('class="view-tabs"', report)
        self.assertEqual(11, report.count('class="tc-template"'))

    def test_markdown_execution_plan_references_cases_once_per_membership(self) -> None:
        organization = json.loads((self.output / "organization.json").read_text(encoding="utf-8"))
        index = json.loads((self.output / "test-cases.json").read_text(encoding="utf-8"))
        plan = render.render_execution_plan(organization, index)
        self.assertLess(plan.index("[TC-004]"), plan.index("[TC-002]"))
        self.assertEqual(2, plan.count("[TC-003]"))  # functional group + load view, a link each
        self.assertIn("CH-001 (post-suite chaos-001)", plan)
        self.assertIn("_Order: main-flow order (UC-9)_", plan)
        index["output_locale"] = "pt-BR"
        self.assertTrue(render.render_execution_plan(organization, index).startswith("# Plano de execução"))


if __name__ == "__main__":
    unittest.main()
