from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.court_organization_evidence import court_organization_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import find_variable_candidates, save_variable_rows


class CourtOrganizationEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "evidence.sqlite3"
        save_variable_rows(court_organization_rows(), self.db_path)
        self.common = dict(
            bill_no="2213969", agency="대법원", policy_domain="법원조직",
            start_year=2026, years=5, variable_db_path=str(self.db_path),
        )

    def test_before_answer_prior_rates_exist_but_target_staff_does_not(self) -> None:
        rows = find_variable_candidates(
            cutoff_date="2025-11-06", agency="대법원", policy_domain="법원조직",
            target_bill_no="2213969", start_year=2026, years=5,
            db_path=self.db_path,
        )
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["source_bill_no"] == "2212273" for row in rows))
        salary_key = "2212273:court_salary_by_grade:2025"
        with self.assertRaisesRegex(ValueError, "headcount_by_grade"):
            estimate_routed_item({**self.common, "cutoff_date": "2025-11-06",
                "route_path": ["인건비", "보수", "직급별"],
                "selected_evidence_keys": [salary_key],
                "evidence_selection_reasons": {salary_key: "같은 법원 지원 승격의 직급별 보수표"}})

    def test_post_answer_staff_reconstructs_salary_and_derived_costs(self) -> None:
        prior = ["2212273:court_salary_by_grade:2025",
                 "2212273:court_wage_growth:2026-2030",
                 "2212273:court_salary_base_year:2025"]
        reasons = {key: "같은 법원 지원 승격·법원공무원; 2025년 보수와 전망 시기 일치"
                   for key in prior}
        salary = estimate_routed_item({**self.common,
            "cutoff_date": "2025-11-12", "evidence_mode": "development_review",
            "route_path": ["인건비", "보수", "직급별"],
            "selected_evidence_keys": prior + [
                "2213969:anyang_net_staff_by_grade:2026",
                "2213969:anyang_first_year_fraction:2026"],
            "evidence_selection_reasons": reasons})
        self.assertEqual(salary.annual_amounts_thousand,
                         (1_639_047, 2_014_061, 2_062_399, 2_111_896, 2_162_582))

        salary_won = [amount * 1000 for amount in salary.annual_amounts_thousand]
        derived = {}
        for route, key in (
            (["인건비", "기관부담금"], "2212273:court_employer_rate:2026-2030"),
            (["인건비", "기본경비"], "2212273:court_basic_expense_ratio:2025"),
        ):
            derived[key] = estimate_routed_item({**self.common,
                "cutoff_date": "2025-11-12", "evidence_mode": "development_review",
                "route_path": route, "selected_evidence_keys": [key],
                "evidence_selection_reasons": {key: "법원 인건비 파생비율 선례"},
                "calculated_inputs": {"annual_salary_amount": {
                    "value": salary_won, "unit": "KRW/year",
                    "source_ref": "2212273 보수표 × 2213969 순증인원"}},
            })
        self.assertEqual(derived["2212273:court_employer_rate:2026-2030"].annual_amounts_thousand,
                         (214_158, 264_446, 272_113, 280_587, 289_353))
        self.assertEqual(derived["2212273:court_basic_expense_ratio:2025"].annual_amounts_thousand,
                         (106_046, 130_310, 133_437, 136_640, 139_919))

        asset_key = "2212273:asset_price_per_person:2026"
        asset = estimate_routed_item({**self.common,
            "cutoff_date": "2025-11-12", "evidence_mode": "development_review",
            "route_path": ["자본지출", "인원기반자산취득"],
            "selected_evidence_keys": [asset_key],
            "evidence_selection_reasons": {asset_key: "같은 정부기관의 2026년 1인당 자산취득비"},
            "calculated_inputs": {"headcount": {"value": 28, "unit": "person",
                "source_ref": "2213969 순증인원 합계"}},
            "explicit_inputs": {"duration": 1},
        })
        self.assertEqual(asset.annual_amounts_thousand, (139_468, 0, 0, 0, 0))

    def test_target_staff_cannot_leak_into_proposal_date(self) -> None:
        key = "2213969:anyang_net_staff_by_grade:2026"
        with self.assertRaisesRegex(ValueError, "future"):
            estimate_routed_item({**self.common, "cutoff_date": "2025-11-06",
                "route_path": ["인건비", "보수", "직급별"],
                "selected_evidence_keys": [key]})


if __name__ == "__main__":
    unittest.main()
