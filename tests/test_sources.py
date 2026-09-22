from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sources  # noqa: E402


class ScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / "docs" / "nested").mkdir(parents=True)
        (self.workspace / "docs" / "requirements.md").write_text("Selected requirement", encoding="utf-8")
        (self.workspace / "docs" / "nested" / "adr.md").write_text("Selected ADR", encoding="utf-8")
        (self.workspace / "sibling").mkdir()
        (self.workspace / "sibling" / "private.md").write_text("Outside", encoding="utf-8")
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "service.py").write_text("import hidden_module\n", encoding="utf-8")
        (self.workspace / "hidden_module.py").write_text("SECRET = True\n", encoding="utf-8")
        (self.workspace / "node_modules").mkdir()
        (self.workspace / "node_modules" / "noise.js").write_text("noise", encoding="utf-8")
        (self.workspace / "docs" / "diagram.png").write_bytes(b"not-opened")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_selected_file_resolves_only_itself(self) -> None:
        result = sources.resolve_selected_scope(self.workspace, ["docs/requirements.md"])
        self.assertEqual(["docs/requirements.md"], result["resolved_scope_paths"])

    def test_selected_directory_is_recursive_without_siblings_or_noise(self) -> None:
        result = sources.resolve_selected_scope(self.workspace, ["docs"])
        self.assertEqual(
            ["docs/diagram.png", "docs/nested/adr.md", "docs/requirements.md"], result["resolved_scope_paths"],
        )

    def test_import_is_not_followed(self) -> None:
        result = sources.resolve_selected_scope(self.workspace, ["src/service.py"])
        self.assertEqual(["src/service.py"], result["resolved_scope_paths"])

    def test_ambiguous_basename_requires_disambiguation(self) -> None:
        (self.workspace / "sibling" / "requirements.md").write_text("Other", encoding="utf-8")
        with self.assertRaisesRegex(sources.ScopeError, "ambiguous source name"):
            sources.resolve_selected_scope(self.workspace, ["requirements.md"])

    def test_parent_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(sources.ScopeError, "escapes the allowed boundary"):
            sources.resolve_selected_scope(self.workspace, ["../outside.md"])

    def test_one_record_per_physical_source_with_status_and_digest(self) -> None:
        selection = sources.assign_roles(self.workspace, [
            {"path": "docs", "role": "FUNCTIONAL_AUTHORITY"}, {"path": "src", "role": "IMPLEMENTATION_EVIDENCE"},
        ])
        records, texts = sources.build_source_records(self.workspace, selection["roles"])
        by_path = {item["path"]: item for item in records}
        self.assertEqual(4, len(records))
        self.assertEqual("METADATA_ONLY", by_path["docs/diagram.png"]["status"])
        self.assertEqual("READ", by_path["docs/requirements.md"]["status"])
        self.assertEqual(64, len(by_path["src/service.py"]["content_digest"]))
        self.assertNotIn("docs/diagram.png", texts)

    def test_every_selection_needs_a_role_and_an_authority(self) -> None:
        with self.assertRaisesRegex(sources.ScopeError, "requires a role"):
            sources.assign_roles(self.workspace, [{"path": "docs"}])
        with self.assertRaisesRegex(sources.ScopeError, "FUNCTIONAL_AUTHORITY"):
            sources.assign_roles(self.workspace, [{"path": "src", "role": "IMPLEMENTATION_EVIDENCE"}])

    def test_artifact_root_must_be_explicit_and_not_skill_or_source_root(self) -> None:
        with self.assertRaisesRegex(sources.ScopeError, "ambiguous"):
            sources.resolve_artifact_root(skill_root=ROOT, source_root=self.workspace, artifact_root=None)
        with self.assertRaisesRegex(sources.ScopeError, "skill root"):
            sources.resolve_artifact_root(skill_root=ROOT, source_root=self.workspace, artifact_root=ROOT)
        with self.assertRaisesRegex(sources.ScopeError, "source root"):
            sources.resolve_artifact_root(skill_root=ROOT, source_root=self.workspace, artifact_root=self.workspace)
        target = self.workspace / "out"
        self.assertEqual(target.resolve(), sources.resolve_artifact_root(
            skill_root=ROOT, source_root=self.workspace, artifact_root=target,
        ))


class IdentifierIndexTests(unittest.TestCase):
    TEXT = """Sumário
7.1. RF-10 – Emissão de Nota
7.2. RF-11 – Cancelamento de Nota
Regras
RN-3 - Numeração Única
Cada nota recebe um número único na série (RF-10).
RF-10 - Emissão de Nota
Descrição: o operador emite a nota para um pedido faturável.
RF-11 - Cancelamento de Nota
Descrição: notas podem ser canceladas em até 24 horas.
● FA-2.1 – Pedido bloqueado: o sistema recusa a emissão.
"""

    def test_definitions_keep_official_titles_and_prefer_the_body(self) -> None:
        entries = {item["identifier"]: item for item in sources.extract_identifiers(self.TEXT, "req.md")}
        self.assertEqual({"RF-10", "RF-11", "RN-3", "FA-2.1"}, set(entries))
        self.assertEqual("Emissão de Nota", entries["RF-10"]["title"])
        self.assertIn("faturável", entries["RF-10"]["excerpt"])
        self.assertEqual("Pedido bloqueado", entries["FA-2.1"]["title"])
        self.assertEqual("BUSINESS_RULE", entries["RN-3"]["kind"])
        self.assertEqual("ALTERNATIVE_FLOW", entries["FA-2.1"]["kind"])

    def test_inline_mentions_are_references_not_definitions(self) -> None:
        entries = sources.extract_identifiers("The total follows (BR-9) and BR-9, BR-10 apply.\n", "a.md")
        self.assertEqual([], entries)

    def test_locale_precedence(self) -> None:
        self.assertEqual("en", sources.infer_locale("en", [self.TEXT])["output_locale"])
        inferred = sources.infer_locale(None, [self.TEXT])
        self.assertEqual(("pt-BR", "FUNCTIONAL_AUTHORITY"), (inferred["output_locale"], inferred["locale_source"]))
        from_request = sources.infer_locale(None, ["RF-1 X"], "Gere os casos de teste para o módulo de notas")
        self.assertEqual("USER_REQUEST", from_request["locale_source"])
        self.assertEqual("FALLBACK_AMBIGUOUS", sources.infer_locale(None, ["RF-1 X"])["locale_source"])


class TestAssetDiscoveryTests(unittest.TestCase):
    def test_python_and_javascript_tests_are_discovered_statically(self) -> None:
        python = "class TestOrders:\n    def test_cancel(self):\n        pass\n\ndef test_issue():\n    pass\ndef helper():\n    pass\n"
        found = sources.discover_test_assets(python, "t/test_orders.py")
        self.assertEqual(["t/test_orders.py::TestOrders::test_cancel", "t/test_orders.py::test_issue"],
                         [item["asset"] for item in found])
        js = "describe('x', () => {\n  it('rejects expired tokens', () => {});\n  test(\"renews\", () => {});\n});\n"
        self.assertEqual(2, len(sources.discover_test_assets(js, "t/auth.spec.js")))


if __name__ == "__main__":
    unittest.main()
