import tempfile
import unittest
from pathlib import Path

from backend.erce.care_worker_survey_evidence import care_worker_survey_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class CareWorkerSurveyTests(unittest.TestCase):
    def test_replay_and_reuse_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "variables.sqlite3"
            rows = care_worker_survey_rows()
            self.assertEqual(save_variable_rows(rows, path), 2)
            self.assertEqual(find_variable_candidates(cutoff_date="2024-11-28", db_path=path), [])
            self.assertEqual(find_variable_candidates(cutoff_date="2024-12-02", target_bill_no="2205985", db_path=path), [])
            self.assertEqual(len(find_variable_candidates(cutoff_date="2024-12-02", target_bill_no="new", db_path=path)), 2)
            payload = {"route_key": "research_survey", "bill_no": "2205985",
                       "cutoff_date": "2024-12-02", "start_year": 2025, "years": 5,
                       "evidence_mode": "development_review", "variable_db_path": path,
                       "selected_evidence_keys": [row["evidence_key"] for row in rows],
                       "explicit_inputs": {"recurrence_interval_years": {
                           "value": 2, "unit": "year", "source_ref": "原文: 2년마다 조사"}}}
            result = estimate_routed_item(payload)
            self.assertEqual(result.annual_amounts_thousand, (178000, 0, 178000, 0, 178000))
            self.assertTrue(result.resolved_variables["survey_unit_cost"].is_assumption)
            for change, message in (({"evidence_mode": "holdout"}, "target answer"),
                                    ({"bill_no": "new"}, "applicability")):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                    estimate_routed_item({**payload, **change})
            reused = estimate_routed_item({**payload, "bill_no": "new", "evidence_mode": "holdout",
                "evidence_selection_reasons": {r["evidence_key"]: "同種 보수조사·전국 통합 시행과 단가 동결 가정을 확인" for r in rows}})
            self.assertEqual(reused.annual_amounts_thousand, result.annual_amounts_thousand)
