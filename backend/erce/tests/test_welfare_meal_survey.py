import tempfile
import unittest
from pathlib import Path
from backend.erce.care_worker_survey_evidence import welfare_meal_safety_survey_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_welfare_meal_survey import meal_survey_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class WelfareMealSurveyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name)/"test.sqlite3"
        save_variable_rows(welfare_meal_safety_survey_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2208199"], self.db)

    def web(self, **updates):
        return calculate_erce_web_item({**meal_survey_payload(),"bill_no":"NEW_WELFARE_MEAL_SURVEY","evidence_mode":"holdout",**updates}, variable_db_path=self.db)

    def test_reference_amount_and_disclosure(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"], 5)
        self.assertLess(r["attached_display_error_percent"], .02)
        self.assertEqual(r["reusable_web_result"]["estimatePurpose"], "reference_scenario")
        self.assertTrue(r["reusable_web_result"]["referenceNotice"])
        self.assertFalse(r["source_bill_version_match"])

    def test_reference_approval_required(self):
        for updates in ({"use_unmatched_source_as_reference":False}, {"unmatched_source_reference_note":""}, {"estimate_purpose":"official_estimate"}, {"reference_notice":""}):
            with self.assertRaises(ValueError):
                self.web(**updates)

    def test_new_law_cycle_and_explicit_budget_priority(self):
        p = dict(explicit_inputs={"recurrence_interval_years":dict(value=2,unit="year",source_ref="새원문2년주기")})
        annual = self.web(**p)["annualAmountsThousand"]
        self.assertTrue(all(annual[i]>0 for i in (0,2,4)))
        self.assertEqual([annual[1],annual[3]], [0,0])
        p["explicit_inputs"]["survey_unit_cost"] = dict(value=800000000,unit="KRW/survey",source_ref="새의안의2023기준명시예산")
        self.assertGreater(self.web(**p)["annualAmountsThousand"][0],annual[0])

    def test_wrong_task_own_answer_and_future_forecast_blocked(self):
        with self.assertRaises(ValueError):
            self.web(research_service_function="school_meal_staff_survey")
        with self.assertRaises(ValueError):
            calculate_erce_web_item(meal_survey_payload(), variable_db_path=self.db)
        with self.assertRaises(ValueError):
            self.web(start_year=2031)
