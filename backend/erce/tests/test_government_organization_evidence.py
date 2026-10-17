from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.government_organization_evidence import government_organization_rows
from backend.erce.variable_evidence_store import find_variable_candidates, save_variable_rows

SALARY_KEYS = ["2204756:moe_vice_office_headcount:convention",
               "2204756:moe_vice_office_salary_by_grade:2024",
               "nabo:central_wage_growth:2025-2029:v202411",
               "nabo:central_salary_base_year:2024:v202411"]
EMPLOYER_KEY = "nabo:central_employer_rate:2025-2029:v202411"


class GovernmentOrganizationEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "evidence.sqlite3"
        save_variable_rows(government_organization_rows(), self.db_path)
        self.common = dict(bill_no="2204756", agency="환경부",
                           policy_domain="정부조직", start_year=2025, years=5,
                           variable_db_path=str(self.db_path))

    @staticmethod
    def _reasons(keys):
        return {key: "차관 신설·중앙행정기관 인건비 전망, 추계기간 일치" for key in keys}

    def test_answer_rows_are_invisible_at_proposal_date(self) -> None:
        rows = find_variable_candidates(cutoff_date="2024-10-17", policy_domain="정부조직",
                                        db_path=self.db_path)
        self.assertEqual(rows, [])

    def test_answer_rows_are_target_answer_in_holdout_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "target answer"):
            estimate_routed_item({**self.common, "cutoff_date": "2024-12-23",
                "route_path": ["인건비", "보수", "직급별"],
                "selected_evidence_keys": SALARY_KEYS,
                "evidence_selection_reasons": self._reasons(SALARY_KEYS)})

    def test_post_answer_regression_reproduces_salary_and_employer_cost(self) -> None:
        review = {**self.common, "cutoff_date": "2024-12-23", "evidence_mode": "development_review"}
        salary = estimate_routed_item({**review, "route_path": ["인건비", "보수", "직급별"],
            "selected_evidence_keys": SALARY_KEYS,
            "evidence_selection_reasons": self._reasons(SALARY_KEYS)})
        self.assertEqual(salary.annual_amounts_thousand,
                         (368_927, 375_937, 383_079, 390_358, 397_775))
        employer = estimate_routed_item({**review, "route_path": ["인건비", "기관부담금"],
            "selected_evidence_keys": [EMPLOYER_KEY],
            "evidence_selection_reasons": self._reasons([EMPLOYER_KEY]),
            "calculated_inputs": {"annual_salary_amount": {
                "value": [amount * 1000 for amount in salary.annual_amounts_thousand],
                "unit": "KRW/year", "source_ref": "차관실 보수 총액"}}})
        self.assertEqual(sum(employer.annual_amounts_thousand), 251_745)

    def test_central_forecast_needs_recorded_applicability_for_a_ministry(self) -> None:
        payload = {**self.common, "cutoff_date": "2024-12-23", "evidence_mode": "development_review",
            "route_path": ["인건비", "기관부담금"], "selected_evidence_keys": [EMPLOYER_KEY],
            "calculated_inputs": {"annual_salary_amount": {
                "value": [100_000_000] * 5, "unit": "KRW/year", "source_ref": "test"}}}
        with self.assertRaisesRegex(ValueError, "scope mismatch \\(agency\\)"):
            estimate_routed_item(payload)

    def test_ministry_specific_office_rows_do_not_transfer_to_other_ministry(self) -> None:
        with self.assertRaisesRegex(ValueError, "scope mismatch \\(agency\\)"):
            estimate_routed_item({**self.common, "agency": "국방부", "bill_no": "9999999",
                "cutoff_date": "2025-01-01",
                "route_path": ["인건비", "보수", "직급별"],
                "selected_evidence_keys": SALARY_KEYS,
                "evidence_selection_reasons": self._reasons(SALARY_KEYS)})


if __name__ == "__main__":
    unittest.main()
