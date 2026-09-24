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

    def test_other_ecosystem_conventions_are_discovered(self) -> None:
        go = "package orders\n\nfunc TestCancelOrder(t *testing.T) {}\nfunc helper() {}\n"
        self.assertEqual(["TestCancelOrder"], [a["reference"] for a in sources.discover_test_assets(go, "orders_test.go")])
        java = "class LedgerTest {\n  @Test\n  void rejectsNegativeAmount() {\n  }\n  void helper() {}\n}\n"
        self.assertEqual(["rejectsNegativeAmount"],
                         [a["reference"] for a in sources.discover_test_assets(java, "LedgerTest.java")])
        kotlin = "class DoseTest {\n  @Test fun capsDailyDose() {}\n}\n"
        self.assertEqual(["capsDailyDose"], [a["reference"] for a in sources.discover_test_assets(kotlin, "DoseTest.kt")])
        csharp = "public class CartTests {\n  [Fact]\n  public async Task EmptyCartCannotCheckout() {}\n}\n"
        self.assertEqual(["EmptyCartCannotCheckout"],
                         [a["reference"] for a in sources.discover_test_assets(csharp, "CartTests.cs")])
        gherkin = "Feature: Transfers\n  Scenario: Transfer above the daily limit is refused\n"
        self.assertEqual(["Transfer above the daily limit is refused"],
                         [a["reference"] for a in sources.discover_test_assets(gherkin, "transfers.feature")])

    def test_test_file_facet_follows_ecosystem_conventions_only(self) -> None:
        for path in ("app/tests/test_orders.py", "svc/orders_test.go", "web/src/cart.spec.ts",
                     "web/__tests__/cart.js", "core/src/test/java/LedgerTest.java", "spec/models/user_spec.rb",
                     "features/transfers.feature"):
            self.assertTrue(sources.is_test_file(path), path)
        for path in ("app/orders.py", "app/testing_utils.md", "app/contest.py", "app/tests/fixture.json",
                     "docs/test-plan.md"):
            self.assertFalse(sources.is_test_file(path), path)

    def test_tests_inside_an_implementation_selection_challenge_without_changing_role(self) -> None:
        records = [
            {"path": "app/billing/tests/test_invoices.py", "role": "IMPLEMENTATION_EVIDENCE"},
            {"path": "app/billing/invoices.py", "role": "IMPLEMENTATION_EVIDENCE"},
            {"path": "docs/rules.md", "role": "FUNCTIONAL_AUTHORITY"},
            {"path": "qa/test_refunds.py", "role": "TEST_ASSET"},
        ]
        texts = {
            "app/billing/tests/test_invoices.py": "def test_overdue_invoice_is_flagged():\n    pass\n",
            # an ordinary implementation file whose function merely starts with "test" is not a test asset
            "app/billing/invoices.py": "def test_mode_enabled():\n    return False\n",
            "docs/rules.md": "BR-1 - Overdue invoices\n",
            "qa/test_refunds.py": "def test_refund_window():\n    pass\n",
        }
        found = sources.discover_all_test_assets(records, texts)
        self.assertEqual(
            {("app/billing/tests/test_invoices.py::test_overdue_invoice_is_flagged", "IMPLEMENTATION_EVIDENCE"),
             ("qa/test_refunds.py::test_refund_window", "TEST_ASSET")},
            {(a["asset"], a["source_role"]) for a in found},
        )
        self.assertEqual("IMPLEMENTATION_EVIDENCE", records[0]["role"])

    def test_unparseable_implementation_test_file_is_a_warning_not_a_failure(self) -> None:
        warnings: list[str] = []
        records = [{"path": "app/tests/test_broken.py", "role": "IMPLEMENTATION_EVIDENCE"}]
        self.assertEqual([], sources.discover_all_test_assets(records, {"app/tests/test_broken.py": "def (:\n"}, warnings))
        self.assertTrue(warnings and warnings[0].startswith("TEST_ASSET_NOT_PARSED"))
        with self.assertRaises(sources.ScopeError):  # an explicit TEST_ASSET selection still fails loudly
            sources.discover_all_test_assets([{"path": "t/test_x.py", "role": "TEST_ASSET"}], {"t/test_x.py": "def (:\n"})


if __name__ == "__main__":
    unittest.main()
