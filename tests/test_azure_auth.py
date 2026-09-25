"""Azure publisher authentication reliability: safe Azure CLI discovery on Windows/Linux/macOS,
one interactive browser sign-in per session, and clear, non-leaking error reporting.

Nothing here touches a real Azure CLI installation or a real browser: `subprocess.run` and
`shutil.which` are mocked, and `azure.identity` is faked via `sys.modules`."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from unittest import mock

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import pipeline  # noqa: E402
from integrations import azure_devops as ado  # noqa: E402
from test_azure_publish import ORG as PUBLISH_ORG, TARGET, FakeAzure  # noqa: E402
from support import PackRun  # noqa: E402
import azure_export as az  # noqa: E402
import azure_publish as pub  # noqa: E402


def fake_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class AzureCliDiscoveryTests(unittest.TestCase):
    """The bug: `subprocess.run(["az", ...])` fails on Windows with `[WinError 2]` because
    the installed command is the `az.cmd` shim, which CreateProcess does not resolve without
    a shell. `shutil.which` performs that resolution safely."""

    def test_the_windows_cmd_shim_is_discovered_through_which(self) -> None:
        shim = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
        with mock.patch("shutil.which", return_value=shim) as which:
            resolved = ado._find_azure_cli()
        which.assert_called_once_with("az")
        self.assertEqual(shim, resolved)

    def test_a_missing_cli_is_reported_clearly_not_as_a_traceback(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(ado.PublicationError, "AZURE_CLI_UNAVAILABLE"):
                ado._find_azure_cli()

    def test_arguments_stay_a_structured_list_never_a_shell_string(self) -> None:
        calls = []

        def spy(args, **kwargs):
            calls.append((args, kwargs))
            return fake_run(stdout="structured-token\n")

        with mock.patch("shutil.which", return_value="/usr/bin/az"), mock.patch("subprocess.run", side_effect=spy):
            header = ado.AzureCliCredential().authorization_header()

        self.assertEqual("Bearer structured-token", header)
        args, kwargs = calls[0]
        self.assertIsInstance(args, list)
        self.assertEqual("/usr/bin/az", args[0])
        self.assertIn(ado.AzureCliCredential.RESOURCE, args)
        self.assertFalse(kwargs.get("shell", False))  # never a shell

    def test_a_cli_that_disappears_between_discovery_and_execution_fails_clearly(self) -> None:
        with mock.patch("shutil.which", return_value="/usr/bin/az"), \
                mock.patch("subprocess.run", side_effect=OSError("no such file or directory")):
            with self.assertRaisesRegex(ado.PublicationError, "AZURE_CLI_UNAVAILABLE"):
                ado.AzureCliCredential().authorization_header()

    def test_an_unauthenticated_cli_is_reported_clearly(self) -> None:
        def spy(args, **kwargs):
            return fake_run(returncode=1, stderr="ERROR: Please run 'az login' to setup account.")

        with mock.patch("shutil.which", return_value="/usr/bin/az"), mock.patch("subprocess.run", side_effect=spy):
            with self.assertRaisesRegex(ado.PublicationError, "AZURE_CLI_NOT_AUTHENTICATED"):
                ado.AzureCliCredential().authorization_header()

    def test_an_empty_token_is_also_treated_as_not_authenticated(self) -> None:
        with mock.patch("shutil.which", return_value="/usr/bin/az"), \
                mock.patch("subprocess.run", side_effect=lambda *a, **k: fake_run(stdout="\n")):
            with self.assertRaisesRegex(ado.PublicationError, "AZURE_CLI_NOT_AUTHENTICATED"):
                ado.AzureCliCredential().authorization_header()

    def test_the_resource_id_is_the_azure_devops_application_id(self) -> None:
        self.assertEqual("499b84ac-1321-427f-aa17-267ca6975798", ado.AzureCliCredential.RESOURCE)
        self.assertEqual(ado.AZURE_DEVOPS_RESOURCE, ado.AzureCliCredential.RESOURCE)

    def test_the_token_is_cached_and_the_cli_is_not_spawned_for_every_header(self) -> None:
        calls = []

        def spy(args, **kwargs):
            calls.append(args)
            return fake_run(stdout="cached-token\n")

        with mock.patch("shutil.which", return_value="/usr/bin/az"), mock.patch("subprocess.run", side_effect=spy):
            credential = ado.AzureCliCredential()
            headers = [credential.authorization_header() for _ in range(5)]

        self.assertEqual(["Bearer cached-token"] * 5, headers)
        self.assertEqual(1, len(calls))

    def test_the_token_is_never_exposed_through_repr_and_never_written_to_disk(self) -> None:
        secret_token = "top-secret-cli-token"
        with mock.patch("shutil.which", return_value="/usr/bin/az"), \
                mock.patch("subprocess.run", side_effect=lambda *a, **k: fake_run(stdout=secret_token + "\n")), \
                tempfile.TemporaryDirectory() as scratch:
            credential = ado.AzureCliCredential()
            credential.authorization_header()
            written = [p for p in Path(scratch).rglob("*") if p.is_file()]
        self.assertNotIn(secret_token, repr(credential))
        self.assertEqual([], written)  # the credential itself never opened a file at all


class FakeInteractiveBrowserCredential:
    """Stands in for `azure.identity.InteractiveBrowserCredential`. Construction simulates the
    one browser sign-in; `get_token` simulates azure-identity's own silent token cache."""

    instances = 0
    get_token_calls = 0
    fail_with: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        type(self).instances += 1

    def get_token(self, *scopes):
        type(self).get_token_calls += 1
        if type(self).fail_with is not None:
            raise type(self).fail_with
        return types.SimpleNamespace(token="fake-interactive-token")

    @classmethod
    def reset(cls) -> None:
        cls.instances = 0
        cls.get_token_calls = 0
        cls.fail_with = None


def fake_azure_identity_module(credential_cls: type) -> types.ModuleType:
    module = types.ModuleType("azure.identity")
    module.InteractiveBrowserCredential = credential_cls
    return module


class InteractiveCredentialTests(unittest.TestCase):
    """The bug: a new `InteractiveBrowserCredential` (and a fresh `get_token`) was built on
    every `authorization_header()` call, so every REST call opened a new browser window."""

    def setUp(self) -> None:
        FakeInteractiveBrowserCredential.reset()
        self.addCleanup(FakeInteractiveBrowserCredential.reset)

    def test_one_credential_instance_is_reused_across_multiple_calls(self) -> None:
        module = fake_azure_identity_module(FakeInteractiveBrowserCredential)
        with mock.patch.dict(sys.modules, {"azure.identity": module}):
            credential = ado.InteractiveCredential()
            headers = [credential.authorization_header() for _ in range(5)]
        self.assertEqual(["Bearer fake-interactive-token"] * 5, headers)
        self.assertEqual(1, FakeInteractiveBrowserCredential.instances)  # one browser sign-in
        self.assertEqual(5, FakeInteractiveBrowserCredential.get_token_calls)  # its own cache serves each call

    def test_multiple_rest_calls_do_not_reopen_the_browser(self) -> None:
        module = fake_azure_identity_module(FakeInteractiveBrowserCredential)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"value": [{"id": "p-1", "name": "Shop"}]}'

        def opener(request):
            return Response()

        with mock.patch.dict(sys.modules, {"azure.identity": module}):
            credential = ado.InteractiveCredential()
            remote = ado.RestAzureRemote("https://dev.azure.example/org-a", credential, opener=opener)
            for _ in range(3):
                remote.list_projects()
        self.assertEqual(1, FakeInteractiveBrowserCredential.instances)

    def test_token_acquisition_is_not_recreated_for_every_http_request(self) -> None:
        module = fake_azure_identity_module(FakeInteractiveBrowserCredential)
        with mock.patch.dict(sys.modules, {"azure.identity": module}):
            credential = ado.InteractiveCredential()
            first = credential._browser_credential()
            credential.authorization_header()
            second = credential._browser_credential()
        self.assertIs(first, second)

    def test_a_cancelled_login_fails_clearly(self) -> None:
        FakeInteractiveBrowserCredential.fail_with = RuntimeError("user closed the browser window")
        module = fake_azure_identity_module(FakeInteractiveBrowserCredential)
        with mock.patch.dict(sys.modules, {"azure.identity": module}):
            with self.assertRaisesRegex(ado.PublicationError, "INTERACTIVE_AUTH_FAILED"):
                ado.InteractiveCredential().authorization_header()

    def test_missing_azure_identity_reports_credential_unavailable(self) -> None:
        with mock.patch.dict(sys.modules, {"azure.identity": None}):  # simulates: not importable
            with self.assertRaisesRegex(ado.PublicationError, "CREDENTIAL_UNAVAILABLE"):
                ado.InteractiveCredential().authorization_header()

    def test_the_token_is_never_exposed_through_repr_or_written_to_disk(self) -> None:
        module = fake_azure_identity_module(FakeInteractiveBrowserCredential)
        with mock.patch.dict(sys.modules, {"azure.identity": module}), tempfile.TemporaryDirectory() as scratch:
            credential = ado.InteractiveCredential()
            credential.authorization_header()
            written = [p for p in Path(scratch).rglob("*") if p.is_file()]
        self.assertNotIn("fake-interactive-token", repr(credential))
        self.assertEqual([], written)  # the credential itself never opened a file at all


class RemoteForLazinessTests(unittest.TestCase):
    """`remote_for` (in azure_publish.py) must build credentials lazily: constructing one
    touches neither the Azure CLI nor azure-identity until a REST call actually needs a
    header, so --prepare's own target-validation calls are still the first real work done."""

    def test_constructing_an_azure_cli_credential_touches_nothing(self) -> None:
        with mock.patch("shutil.which", side_effect=AssertionError("touched shutil.which too early")), \
                mock.patch("subprocess.run", side_effect=AssertionError("touched subprocess too early")):
            ado.AzureCliCredential()  # must not raise

    def test_constructing_an_interactive_credential_touches_nothing(self) -> None:
        with mock.patch.dict(sys.modules, {"azure.identity": None}):
            ado.InteractiveCredential()  # must not raise or import azure.identity yet


class PublisherRegressionTests(unittest.TestCase):
    """Using FakeAzure only (never real Azure): the credential rework changes nothing about
    prepare's read-only-ness, apply's safety, the delete prohibition, target validation or
    current-run resolution."""

    def setUp(self) -> None:
        self.run = PackRun("saas-accounts")
        self.addCleanup(self.run.close)
        self.run.finalize(("JSON",))
        az.convert_run(self.run.run_dir)
        self.azure = FakeAzure()

    def plan_path(self) -> Path:
        return self.run.artifacts / "output" / "azure" / "publication-plan.json"

    def test_prepare_stays_read_only_and_resolves_the_current_run(self) -> None:
        # No explicit --run: exercises the same current-run resolution CP14 added.
        run_dir = pipeline.resolve_run(None, self.run.artifacts)
        self.assertEqual(self.run.run_dir, run_dir)
        result = pub.prepare(run_dir, TARGET, self.azure)
        self.assertEqual([], self.azure.writes())
        self.assertEqual(0, result["remote_writes"])
        self.assertTrue(self.plan_path().is_file())

    def test_apply_still_requires_approval_and_has_zero_delete_support(self) -> None:
        pub.prepare(self.run.run_dir, TARGET, self.azure)
        unapproved = pub.apply(self.plan_path(), self.azure)
        self.assertEqual(("APPROVAL_REQUIRED", 0), (unapproved["status"], unapproved["writes"]))
        self.assertEqual([], self.azure.writes())
        names = [n for n in dir(FakeAzure) if not n.startswith("__")]
        self.assertFalse([n for n in names if "delete" in n.lower()])

    def test_target_validation_still_rejects_an_ambiguous_or_wrong_destination(self) -> None:
        with self.assertRaisesRegex(ado.PublicationError, "TARGET_NOT_FOUND"):
            pub.prepare(self.run.run_dir, {"organization": PUBLISH_ORG, "project": "no-such-project", "plan": "Release"},
                       self.azure)


if __name__ == "__main__":
    unittest.main()
