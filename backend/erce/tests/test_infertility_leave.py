import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.infertility_leave import infertility_leave_recipients
from backend.erce.infertility_leave_evidence import infertility_leave_rows
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class InfertilityLeaveTests(unittest.TestCase):
    def test_civil_population_and_relative_share_growth(self):
        basis = {"base_year": 2023, "priority_company_share": .5,
                 "priority_share_growth_rate": .1,
                 "insured_cohorts": [{"insured_population": 1000, "insured_growth_rate": .2,
                                     "civil_leave_users": 10, "civil_staff": 100}]}
        counts = infertility_leave_recipients(basis, 2024, 2, method="civil_proxy")
        self.assertAlmostEqual(counts[0], 66)
        self.assertAlmostEqual(counts[1], 87.12)

    def test_budget_population_and_day_units(self):
        basis = {"base_year": 2023, "priority_company_share": .5,
                 "priority_share_growth_rate": 0,
                 "historical_infertility_patients": [800, 1200],
                 "employee_share": .8, "insurance_enrollment_share": .75, "leave_uptake_rate": .5}
        payload = {"route_key": "infertility_leave_budget_proxy", "start_year": 2025, "years": 2,
                   "explicit_inputs": {"infertility_population_basis": {"value": basis},
                                       "paid_leave_days": {"value": 3},
                                       "daily_leave_benefit": {"value": 100000, "unit": "KRW/person/day"}}}
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand, (45000, 45000))
        basis["leave_uptake_rate"] = 1.1
        with self.assertRaises(ValueError):
            estimate_routed_item(payload)

    def test_answer_evidence_excluded_from_original_holdout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "variables.sqlite3"
            save_variable_rows(infertility_leave_rows(), path)
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-11", db_path=path), [])
            self.assertEqual(find_variable_candidates(cutoff_date="2024-09-01", target_bill_no="2200349", db_path=path), [])
            self.assertEqual(len(find_variable_candidates(cutoff_date="2024-09-01", target_bill_no="other", db_path=path)), 3)
