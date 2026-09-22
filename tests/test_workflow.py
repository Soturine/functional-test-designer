"""Public workflow compatibility: natural language and every alias reach the same core."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import PackRun

import pipeline
import workflow
from workflow import dispatch, dispatch_request, normalize_intent


def minimal_pdf(path: Path, lines: list[str]) -> None:
    """Write a small valid PDF with one text line per entry (Helvetica, WinAnsi)."""
    text = "BT /F1 11 Tf 40 780 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines
    ) + " ET"
    stream = text.encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + content + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(body)


class AliasTests(unittest.TestCase):
    def test_every_alias_and_its_natural_form_reach_the_same_intent(self) -> None:
        cases = {
            "ftd-gen": ["/ftd-gen docs", "$ftd-gen", "Generate test cases from these files",
                        "Gere os casos de teste destas fontes", "Use this PDF and generate the Test Cases"],
            "ftd-clarify": ["/ftd-clarify", "Ask me the important questions", "Pergunte o que estiver ambíguo"],
            "ftd-check": ["/ftd-check", "Audit whether the suite is executable by a tester", "Verifique se os TCs estão prontos"],
            "ftd-render": ["/ftd-render", "Render the last run as HTML", "Renderize a última execução como Markdown"],
            "ftd-mcp": ["/ftd-mcp", "Prepare the last suite for Azure DevOps Test Plans"],
        }
        for intent, phrases in cases.items():
            for phrase in phrases:
                with self.subTest(phrase=phrase):
                    self.assertEqual(intent, normalize_intent(phrase))


class NaturalGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "project"
        for folder in ("docs/user", "apps/orders", "config", "outside"):
            (self.workspace / folder).mkdir(parents=True)
        minimal_pdf(self.workspace / "requirements.pdf", [
            "RF-01 - Emitir Pedido", "O vendedor emite o pedido e o sistema gera o numero do pedido.",
            "RN-01 - Numero Unico", "Cada pedido recebe um numero unico.",
        ])
        (self.workspace / "docs/user/orders.md").write_text("# Orders\nOpen Orders and click New.", encoding="utf-8")
        (self.workspace / "apps/orders/service.py").write_text("def issue(order):\n    return order\n", encoding="utf-8")
        (self.workspace / "apps/orders/test_service.py").write_text("def test_issue():\n    assert True\n", encoding="utf-8")
        (self.workspace / "config/settings.py").write_text("ORDER_PREFIX = 'PED'\n", encoding="utf-8")
        (self.workspace / "outside/secret.md").write_text("never read", encoding="utf-8")
        self.sources = [
            {"path": "requirements.pdf", "role": "FUNCTIONAL_AUTHORITY"},
            {"path": "docs/user", "role": "TECHNICAL_CONTEXT"},
            {"path": "apps", "role": "IMPLEMENTATION_EVIDENCE"},
            {"path": "config", "role": "IMPLEMENTATION_EVIDENCE"},
        ]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_documented_natural_request_still_works(self) -> None:
        result = dispatch_request(
            "Use this PDF, docs/user, apps and config, generate the Test Cases, save HTML/JSON/Markdown and enable diagnostics.",
            workspace=self.workspace, artifact_root=self.root / "artifacts", run_id="natural", sources=self.sources,
        )
        run = json.loads((Path(result["run_dir"]) / "run.json").read_text(encoding="utf-8"))
        sources = json.loads((Path(result["run_dir"]) / "sources.json").read_text(encoding="utf-8"))
        paths = [item["path"] for item in sources["records"]]
        self.assertEqual(["HTML", "JSON", "MARKDOWN", "DIAGNOSTICS"], run["formats"])
        self.assertEqual({"RF-01", "RN-01"}, {item["identifier"] for item in sources["authority_index"]})
        self.assertIn("apps/orders/test_service.py", paths)
        self.assertIn("docs/user/orders.md", paths)
        self.assertNotIn("outside/secret.md", paths)
        self.assertEqual("pt-BR", result["output_locale"])
        order = json.loads(Path(result["work_order"]).read_text(encoding="utf-8"))
        self.assertEqual(["HTML", "JSON", "MARKDOWN", "DIAGNOSTICS"], order["requested_formats"])

    def test_alias_and_natural_language_start_identical_runs(self) -> None:
        natural = dispatch_request("Generate test cases from these sources", workspace=self.workspace,
                                   artifact_root=self.root / "a", run_id="r", sources=self.sources)
        alias = dispatch_request("/ftd-gen", workspace=self.workspace, artifact_root=self.root / "b", run_id="r",
                                 sources=self.sources)
        read = lambda result: json.loads((Path(result["run_dir"]) / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(read(natural), read(alias))

    def test_legacy_selectors_with_roles_are_accepted(self) -> None:
        result = dispatch("ftd-gen", workspace=self.workspace, artifact_root=self.root / "c", run_id="legacy",
                          selectors=["requirements.pdf", "apps"],
                          roles={"requirements.pdf": "FUNCTIONAL_AUTHORITY", "apps": "IMPLEMENTATION_EVIDENCE"})
        self.assertEqual(2, result["authority_identifiers"])
        with self.assertRaisesRegex(ValueError, "needs a role"):
            dispatch("ftd-gen", workspace=self.workspace, artifact_root=self.root / "d", run_id="x", selectors=["apps"])

    def test_source_order_and_prior_clarifications_reach_the_model(self) -> None:
        answer = workflow.record_answer({"id": "Q-001", "question": "Numero sequencial?"}, "Sim, por ano")
        result = dispatch("ftd-gen", workspace=self.workspace, artifact_root=self.root / "e", run_id="ordered",
                          sources=self.sources, source_order=[["requirements.pdf"], ["apps", "config"]],
                          clarifications=[answer])
        order = json.loads(Path(result["work_order"]).read_text(encoding="utf-8"))
        self.assertEqual([["requirements.pdf"], ["apps", "config"]], order["source_order"])
        self.assertEqual("USER_CLARIFICATION", order["user_clarifications"][0]["source_role"])
        with self.assertRaisesRegex(Exception, "outside the selection"):
            dispatch("ftd-gen", workspace=self.workspace, artifact_root=self.root / "f", run_id="bad",
                     sources=self.sources, source_order=[["outside"]])


class DownstreamAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        started = dispatch_request(
            "Generate test cases, only JSON with diagnostics", workspace=self.run.workspace,
            artifact_root=self.run.artifacts, run_id="compat",
            sources=[{"path": path, "role": item["role"]} for path, item in self.run.pack["sources"].items()],
        )
        self.run_dir = Path(started["run_dir"])
        for stage in ("design", "expansion", "procedures"):
            pipeline.submit_stage(self.run_dir, stage, self.run.pack["stages"][stage])
        self.finished = pipeline.finalize_run(self.run_dir)

    def test_requested_formats_and_diagnostics_are_applied_at_finalize(self) -> None:
        self.assertEqual(["DIAGNOSTICS", "JSON"], self.finished["render"]["rendered_public_formats"])
        self.assertTrue((self.run.artifacts / "diagnostics" / "run-metrics.json").is_file())
        self.assertFalse((self.run.artifacts / "output" / "report.html").exists())

    def test_render_check_clarify_and_mcp_work_from_the_run(self) -> None:
        canonical = str(self.run_dir / "canonical-suite.json")
        rendered = dispatch_request("Render the last run as HTML", canonical_path=canonical, formats=["HTML"])
        self.assertEqual(0, rendered["source_reads_during_render"])
        self.assertTrue((self.run.artifacts / "output" / "report.html").is_file())
        pipeline.verify_manifest(self.run_dir)
        checked = dispatch_request("/ftd-check", run_dir=self.run_dir, focus="procedure")
        self.assertFalse(checked["suite_mutated"])
        questions = dispatch_request("Ask me the important questions", run_dir=self.run_dir)
        self.assertLessEqual(len(questions), 5)
        self.assertTrue(questions)
        preview = dispatch_request("/ftd-mcp", run_dir=self.run_dir, project="P", plan="Plan", suite="Suite",
                                   artifact_root=self.run.artifacts)
        self.assertNotIn("delete", preview)
        self.assertTrue(preview["fallback_exports"])


if __name__ == "__main__":
    unittest.main()
