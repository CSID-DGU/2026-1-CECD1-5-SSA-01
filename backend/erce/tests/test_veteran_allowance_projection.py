from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.veteran_allowance_baselines import veteran_allowance_baseline_rows
from backend.erce.veteran_allowance_projection import estimate_veteran_allowance_delta_from_baselines


class VeteranAllowanceProjectionTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "variables.sqlite3"
        save_variable_rows(veteran_allowance_baseline_rows(), self.db_path)
        self.precedent_keys = ["2200169:raw:" + name for name in (
            "concurrent_excluded_2023", "existing_recipients_2019",
            "existing_recipients_2023", "existing_monthly_benefit_2020",
            "existing_monthly_benefit_2024")]
        self.keys = self.precedent_keys + [
            "official:mohw:median_income_2020", "official:mohw:median_income_2024"]
        self.payload = dict(
            bill_no="2204070", cutoff_date="2024-09-19",
            agency="국가보훈부", policy_domain="참전유공자 예우",
            start_year=2026, years=5, evidence_mode="holdout",
            variable_db_path=str(self.db_path), selected_evidence_keys=self.keys,
            evidence_selection_reasons={key:
                "동일 참전유공자 집단의 과거 실적을 이용한 인원·급여 추세 가정"
                for key in self.precedent_keys})

    def test_reuses_only_historical_baselines_for_two_cost_components(self):
        concurrent, increase = estimate_veteran_allowance_delta_from_baselines(
            self.payload, legal_median_share=0.35)
        self.assertEqual(concurrent.formula_key, "TRANSFER_RECIPIENT_V1")
        self.assertEqual(increase.formula_key, "TRANSFER_RECIPIENT_DELTA_V1")
        self.assertEqual(round(sum(concurrent.annual_amounts_thousand) / 100000), 35726)
        self.assertEqual(round(sum(increase.annual_amounts_thousand) / 100000), 22163)

    def test_precedent_needs_applicability_reason(self):
        with self.assertRaisesRegex(ValueError, "applicability reason"):
            estimate_veteran_allowance_delta_from_baselines(
                {**self.payload, "evidence_selection_reasons": {}}, legal_median_share=0.35)

    def test_future_precedent_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "from the future"):
            estimate_veteran_allowance_delta_from_baselines(
                {**self.payload, "cutoff_date": "2024-08-01"}, legal_median_share=0.35)


if __name__ == "__main__":
    unittest.main()
