import unittest
from backend.erce.basic_pension_income_history import basic_pension_income_rows
from backend.erce.scripts.check_basic_pension_answer_consistency import audit


class PensionIncomeHistoryTests(unittest.TestCase):
    def test_income_histories_reconcile_without_fake_joint_records(self):
        row=basic_pension_income_rows()[0]
        self.assertEqual([r["year"] for r in row["value"]],[2021,2022,2023])
        self.assertEqual([r["total_recipients"] for r in row["value"]],[5973059,6238798,6508574])
        for year in row["value"]:
            for kind in ("single","couple"):
                data=year[kind]
                self.assertEqual(len(data["counts"]),len(data["upper_income_bounds"]))
                self.assertEqual(sum(data["counts"]),data["total"])
        self.assertEqual(row["pension_history_usage"],"historical_distribution_only")

    def test_conditional_gold_consistency_problem_not_rounding(self):
        r=audit()
        self.assertGreater(r["rounding_interval"][0],r["displayed_delta_interval"][1])
        self.assertFalse(r["consistent_under_assumptions"])
        self.assertTrue(r["diagnostic_only"])
