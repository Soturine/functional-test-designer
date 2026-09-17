from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evidence_map", ROOT / "scripts/evidence_map.py")
assert spec and spec.loader
EVIDENCE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVIDENCE)


class EvidenceMapTests(unittest.TestCase):
    def test_source_and_family_pack_are_built_once_and_reused(self) -> None:
        evidence = EVIDENCE.EvidenceMap({"requirements.md"})
        source_loads = []
        pack_builds = []

        first = evidence.source("requirements.md", lambda: source_loads.append(1) or "content")
        second = evidence.source("requirements.md", lambda: source_loads.append(1) or "wrong")
        pack_a = evidence.pack("RF001:finalize", lambda: pack_builds.append(1) or {"path": ["Open", "Finalize"]})
        pack_b = evidence.pack("RF001:finalize", lambda: pack_builds.append(1) or {})

        self.assertEqual(first, second)
        self.assertIs(pack_a, pack_b)
        self.assertEqual(1, len(source_loads))
        self.assertEqual(1, len(pack_builds))
        self.assertEqual(1, evidence.metrics()["evidence_map_hits"])
        self.assertEqual(1, evidence.metrics()["tc_generation_reuse_hits"])
        self.assertEqual(0, evidence.metrics()["source_files_reopened"])

    def test_cache_rejects_source_outside_resolved_scope(self) -> None:
        evidence = EVIDENCE.EvidenceMap({"requirements.md"})

        with self.assertRaisesRegex(ValueError, "outside the resolved selected scope"):
            evidence.source("neighbor.md", lambda: "must not load")


if __name__ == "__main__":
    unittest.main()
