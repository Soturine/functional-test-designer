from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workflow import privacy_safe_metrics, rank_questions, record_answer, should_stop  # noqa: E402


class ClarificationTests(unittest.TestCase):
    def test_limits_round_and_prioritizes_oracle(self) -> None:
        questions = [
            {"id": f"Q-{i}", "question": str(i), "category": category}
            for i, category in enumerate(("style", "procedure", "oracle", "trigger", "test_data", "environment"), 1)
        ]
        ranked = rank_questions(questions)
        self.assertEqual(5, len(ranked))
        self.assertEqual("oracle", ranked[0]["category"])

    def test_answer_has_distinct_provenance_and_conflict_is_not_silent(self) -> None:
        answer = record_answer({
            "id": "Q-1", "question": "Final state?", "affected_refs": ["REQ-001"],
            "approved_authority_answer": "FINALIZED",
        }, "CLOSED")
        self.assertEqual("USER_CLARIFICATION", answer["source_role"])
        self.assertTrue(answer["conflict_requires_review"])
        self.assertNotIn("CLOSED", str(privacy_safe_metrics([answer])))

    def test_stop_words_are_respected(self) -> None:
        for value in ("stop", "Done", "proceed", "skip"):
            self.assertTrue(should_stop(value))


if __name__ == "__main__":
    unittest.main()
