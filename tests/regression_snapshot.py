"""The v2.4.2 behavioral baseline of the public workflows, over the public synthetic domain packs.

`snapshot()` drives every pack through the normal (non-ADR) workflows — /ftd-gen, /ftd-render,
/ftd-check, /ftd-clarify, /ftd-chaos, /ftd-azure, /ftd-azure --manual-import and the guarded
/ftd-azure-publish prepare/apply against a fake Azure — and records stable semantic digests:
timestamps, temporary paths and line endings are normalized, nothing else is.

`tests/fixtures/regression-baseline.json` was written by the v2.4.2 implementation before any
ADR code existed. `test_regression_firewall.py` regenerates the snapshot and requires it to be
identical. Rewriting the fixture (`python tests/regression_snapshot.py --write`) is a deliberate
act that must be justified by an intended change of existing behavior — never by "ADR was added".
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import azure_export as az  # noqa: E402
import azure_publish as pub  # noqa: E402
import challenge as ch  # noqa: E402
import pipeline  # noqa: E402
import workflow  # noqa: E402
from integrations import azure_devops as ado  # noqa: E402
from support import PACKS, PackRun  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "regression-baseline.json"
VOLATILE_KEYS = {"generated_at", "created_at", "started_at", "submitted_at", "finalized_at", "validated_at",
                 "stage_started_at", "rendered_at", "published_at", "timestamp", "elapsed_seconds", "stage_seconds",
                 "seconds", "duration_seconds",
                 # digests over a document that embeds its own generation timestamp
                 "semantic_fingerprint", "canonical_digest", "package_digest", "parent_canonical_digest",
                 # a digest of the pack's source bytes, which the platform's line endings change
                 "content_digest"}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
CHAOS_TEXT = {"en": ("Two operators act on the same record at once",
                     "Concurrent operators could leave the record in an inconsistent state.")}


class Normalizer:
    def __init__(self, *roots: Path):
        self.roots = sorted({str(r) for root in roots for r in (root, root.resolve())}, key=len, reverse=True)

    def text(self, value: str) -> str:
        for root in self.roots:
            for form in (root, root.replace("\\", "/"), root.replace("\\", "\\\\"), json.dumps(root)[1:-1]):
                value = value.replace(form, "<ROOT>")
        value = value.replace("\r\n", "\n")
        return TIMESTAMP.sub("<TS>", value)

    def value(self, item: Any) -> Any:
        if isinstance(item, dict):
            return {k: self.value(v) for k, v in item.items() if k not in VOLATILE_KEYS}
        if isinstance(item, list):
            return [self.value(v) for v in item]
        if isinstance(item, str):
            text = self.text(item)
            return text.replace("\\", "/") if "<ROOT>" in text else text
        return item


def digest(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _files(folder: Path, norm: Normalizer) -> dict[str, str]:
    def content(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return digest(norm.value(json.loads(text))) if path.suffix == ".json" else digest(norm.text(text))
    return {p.relative_to(folder).as_posix(): content(p)
            for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix in {".json", ".md", ".html", ".csv"}}


def _canonical(canonical: dict[str, Any], norm: Normalizer) -> dict[str, Any]:
    index = norm.value(canonical["index"])
    return {
        "count": len(canonical["cases"]), "ids": [c["id"] for c in canonical["cases"]],
        "cases": {c["id"]: digest(norm.value(c)) for c in canonical["cases"]},
        "statuses": {c["id"]: [c["status"], c.get("automation_suitability"), c.get("automation_readiness"),
                               c.get("readiness_blockers"), c.get("automation_layer"), c.get("automation_tool_hint")]
                     for c in canonical["cases"]},
        "procedures": {c["id"]: digest([c["preconditions"], c["test_data"], c["steps"], c["postconditions"],
                                        c["cleanup"], c.get("execution_variants"), c.get("request_contract")])
                       for c in canonical["cases"]},
        "requirements": digest(index["requirements"]), "claims": digest(index["normative_clauses"]),
        "coverage_points": digest(index["coverage_points"]), "findings": digest(index["findings"]),
        "questions": digest(norm.value(canonical["questions"])), "index": digest(index),
        # the canonical fingerprint's own inputs, without the generation timestamp it embeds
        "semantic_fingerprint": digest(norm.value({k: canonical[k] for k in ("index", "questions", "cases")})),
    }


def _organization(organization: dict[str, Any]) -> list[list[Any]]:
    return [[g["id"], g["kind"], g["label"], [[m["origin"], m.get("chaos_run_id"), m["case"]] for m in g["members"]]]
            for g in organization["groups"]]


def _azure(run: PackRun, norm: Normalizer) -> dict[str, Any]:
    result = az.convert_run(run.run_dir)
    package = run.output("azure/azure-export-package.json")
    preview = run.output("azure/azure-preview.json")
    fields, metadata, hashes = {}, {}, {}
    for item in preview["create"]:
        key = item["local_id"]
        emitted = ado.work_item_fields(item["payload"], key)
        fields[key] = digest(norm.value(emitted))
        metadata[key] = norm.value(ado.read_ftd_metadata(emitted["System.Description"]))
        hashes[key] = item["content_hash"]
    return {
        "result": {k: v for k, v in result.items() if k not in {"package", "preview"}},
        "export_keys": [c["export_key"] for c in package["test_cases"]],
        "package": digest(norm.value({k: v for k, v in package.items() if k != "source_run"})),
        "suites": [[s["suite_name"], s["kind"], s["test_case_refs"]] for s in package["suites"]],
        "fields": fields, "metadata": digest(metadata), "content_hashes": digest(hashes),
        "preview": {k: len(preview[k]) for k in ("create", "update", "unchanged", "skipped", "conflicts")},
    }


def _manual_import(run: PackRun, norm: Normalizer) -> dict[str, Any]:
    imported = az.convert_run(run.run_dir, manual_import={"fresh_target": True, "area_path": "Project\\Area"})
    folder = Path(imported["manual_import"]["manual_import_dir"])
    fresh = {"summary": {k: v for k, v in imported["manual_import"].items() if k != "manual_import_dir"},
             "files": _files(folder, norm)}
    # Reimport what Azure would export after that import: every case is UNCHANGED, nothing is created.
    created = [r for p in sorted((folder / "manual-import-create").glob("*.csv"))
               for r in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))]
    ids: dict[str, str] = {}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(created[0]), lineterminator="\r\n")
    writer.writeheader()
    for row in created:
        key = next(t for t in row["Tags"].split("; ") if t.startswith("ftd-key:"))
        writer.writerow({**row, "ID": ids.setdefault(key, str(1000 + len(ids)))})
    export = folder / "azure-current.csv"
    export.write_text(out.getvalue(), encoding="utf-8")
    again = az.convert_run(run.run_dir, manual_import={"existing_azure_export": str(export), "area_path": "Project\\Area"})
    plan = json.loads((folder / "manual-import-plan.json").read_text(encoding="utf-8"))
    return {"fresh": fresh, "existing": {k: v for k, v in again["manual_import"].items() if k != "manual_import_dir"},
            "existing_actions": {e["export_key"]: [e["action"], e["azure_id"]] for e in plan["cases"]}}


def _publication(run: PackRun) -> dict[str, Any]:
    from test_azure_publish import FakeAzure, TARGET
    az.convert_run(run.run_dir)
    azure = FakeAzure()
    plan_path = run.artifacts / "output" / "azure" / "publication-plan.json"
    first = pub.prepare(run.run_dir, TARGET, azure)["summary"]
    denied = pub.apply(plan_path, azure)["status"]
    applied = pub.apply(plan_path, azure, approved=True)
    second = pub.prepare(run.run_dir, TARGET, azure)["summary"]
    titles = sorted(item["title"] for item in azure.items.values())
    next(iter(azure.items.values()))["rev"] += 1
    state_path = run.run_dir / "integration-state" / "azure-devops.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for entry in state["test_cases"].values():
        entry["content_hash"] = "changed-locally"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    conflict = pub.prepare(run.run_dir, TARGET, azure)["summary"]
    return {"first": first, "approval_required": denied, "applied": [applied["status"], applied["writes"]],
            "second": second, "conflict": conflict, "titles": digest(titles),
            "writes": [c for c in azure.calls if c in ado.WRITE_METHODS].count("create_test_case")}


def _current_run(run: PackRun) -> dict[str, Any]:
    resolved = pipeline.resolve_run(None, run.artifacts) == run.run_dir
    explicit = pipeline.resolve_run(str(run.run_dir), run.artifacts) == run.run_dir
    pointer = run.artifacts / ".ftd" / "current-run.json"
    saved = pointer.read_bytes()
    data = json.loads(saved)
    pointer.write_text(json.dumps({**data, "canonical_digest": "0" * 64}), encoding="utf-8")
    try:
        pipeline.resolve_run(None, run.artifacts)
        stale = "ACCEPTED"
    except pipeline.IntegrityError:
        stale = "REFUSED"
    pointer.write_bytes(saved)
    return {"automatic": resolved, "explicit": explicit, "stale_pointer": stale}


def pack_snapshot(name: str) -> dict[str, Any]:
    run = PackRun(name)
    try:
        norm = Normalizer(run.root)
        run.finalize()
        canonical = pipeline.read_canonical(run.run_dir / "canonical-suite.json")
        result: dict[str, Any] = {
            "canonical": _canonical(canonical, norm),
            "organization": _organization(pipeline.organization_for_run(run.run_dir)),
            "outputs": _files(run.artifacts / "output", norm),
            "current_run": _current_run(run),
            "check": digest(norm.value(workflow.dispatch("ftd-check", run_dir=str(run.run_dir)))),
            "clarify": digest(norm.value(workflow.dispatch("ftd-clarify", run_dir=str(run.run_dir)))),
        }
        rendered = workflow.dispatch("ftd-render", run_dir=str(run.run_dir))
        result["render"] = {"outputs_unchanged": _files(run.artifacts / "output", norm) == result["outputs"],
                            "files": sorted(norm.value(rendered.get("files", [])))}
        locale = (canonical["index"].get("output_locale") or "en").split("-")[0]
        if locale in CHAOS_TEXT:
            title, rationale = CHAOS_TEXT[locale]
            ch.start_challenge(run.run_dir, "regression", seeds=[])
            ch.submit_challenge(run.run_dir, "regression", {"cases": [{
                "key": "R1", "title": title, "discovery": "MODEL_DERIVED", "rationale": rationale,
                "execution_tags": ["EXPLORATORY"], "related_test_cases": [canonical["cases"][0]["id"]]}],
                "seed_dispositions": []})
            ch.finalize_challenge(run.run_dir, "regression")
            cases = json.loads((run.run_dir / "challenges" / "regression" / "challenge-cases.json").read_text(encoding="utf-8"))
            result["chaos"] = {"cases": digest(norm.value(cases)),
                               "organization": _organization(pipeline.organization_for_run(run.run_dir)),
                               "canonical_unchanged": pipeline.read_canonical(run.run_dir / "canonical-suite.json")
                               ["semantic_fingerprint"] == canonical["semantic_fingerprint"]}
        result["azure"] = _azure(run, norm)
        result["manual_import"] = _manual_import(run, norm)
        result["publication"] = _publication(run)
        return result
    finally:
        run.close()


def snapshot() -> dict[str, Any]:
    return {"packs": {path.stem: pack_snapshot(path.stem) for path in sorted(PACKS.glob("*.json"))},
            "metadata_samples": metadata_samples()}


def metadata_samples() -> list[dict[str, Any]]:
    """FTD_METADATA_V1 as v2.4.2 emits it for representative payloads: the producer/parser contract."""
    contract = {"method": "POST", "endpoint": "/items/{id}/confirm", "parameters": ["id: an eligible item"],
                "body": '{"note": "<a> & \\"b\\""}', "fixture_pool": None, "varies": ["id"],
                "measurements": ["latency per request"]}
    samples = []
    for key, case in (
            ("canonical:TC-001", {"id": "canonical:TC-001", "title": "Confirm an item", "priority": "HIGH", "status": "READY",
                                  "steps": [{"action": "Confirm the item.", "expected_result": "The item is confirmed."}]}),
            ("chaos:run:CH-002", {"id": "chaos:run:CH-002", "title": "Review an item", "priority": "LOW",
                                  "status": "NEEDS_REVIEW", "automation_suitability": "HIGH",
                                  "automation_readiness": "NEEDS_FIXTURE", "readiness_blockers": ["MISSING_FIXTURE"],
                                  "automation_layer": "API", "automation_tool_hint": "API_TEST", "question_refs": ["Q-003"],
                                  "related_test_cases": ["TC-001"], "requirement_refs": ["REQ-1"], "source_kind": "CHAOS",
                                  "request_contract": contract, "steps": []})):
        fields = ado.work_item_fields(ado.map_test_case(copy.deepcopy(case)), key)
        samples.append({"description": fields["System.Description"], "parsed": ado.read_ftd_metadata(fields["System.Description"])})
    return samples


if __name__ == "__main__":
    data = snapshot()
    if "--write" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE}")
    else:
        print(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)[:4000])
