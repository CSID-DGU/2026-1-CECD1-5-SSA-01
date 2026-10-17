from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.hitl_feedback import collect_committee_feedback


class HitlFeedbackTest(unittest.TestCase):
    def test_collects_once_and_keeps_human_data_out_of_retrieval(self) -> None:
        result = {
            "channel": "committee",
            "billNo": "TEST-1",
            "billName": "가상위원회법안",
            "committees": [
                {
                    "id": "committee-1",
                    "name": "가상위원회",
                    "formula": "인원 × 수당 × 횟수",
                    "formula_selection": {"family": "meeting_allowance"},
                    "articles": [{"no": "제3조"}],
                    "variables": {
                        "incumbent_paid_members": {
                            "value": 10,
                            "unit": "명",
                            "label": "기존 제도 지급대상 인원(선택)",
                            "basis": "사용자가 확인",
                        }
                    },
                }
            ],
        }
        inputs = [
            {
                "committeeId": "committee-1",
                "variable": "incumbent_paid_members",
                "value": 10,
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            first = collect_committee_feedback(result, inputs, path=path)
            second = collect_committee_feedback(result, inputs, path=path)
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(first["queued"], 1)
        self.assertEqual(second["queued"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["assumption_key"],
            "committee_incumbent_paid_member_count",
        )
        self.assertEqual(rows[0]["review_status"], "pending")
        self.assertFalse(rows[0]["eligible_for_retrieval"])


if __name__ == "__main__":
    unittest.main()
