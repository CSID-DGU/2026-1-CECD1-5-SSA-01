import tempfile
import unittest
from pathlib import Path
from backend.erce.care_worker_survey_evidence import social_worker_treatment_plan_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_social_worker_treatment_plan import treatment_plan_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class TreatmentPlanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name)/"test.sqlite3"
        save_variable_rows(social_worker_treatment_plan_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207435"], self.db)

    def web(self, **updates):
        p = {**treatment_plan_payload(), "bill_no":"NEW_TREATMENT_PLAN", "evidence_mode":"holdout", **updates}
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_gold_and_reusable_web(self):
        r = run_regression(self.db)
        self.assertEqual(r["error_percent"], 0)
        self.assertEqual(r["annual_matches"], 5)
        self.assertTrue(r["regression_scope_complete"])

    def test_new_law_period_and_explicit_price_priority(self):
        inputs = dict(treatment_plan_payload()["explicit_inputs"])
        inputs["recurrence_interval_years"] = dict(value=2, unit="year", source_ref="다른 의안 원문2년주기")
        self.assertEqual(self.web(explicit_inputs=inputs)["annualAmountsThousand"], [80000,0,80000,0,80000])
        inputs["plan_unit_cost"] = dict(value=90000000, unit="KRW/plan", source_ref="법안에 명시한 계획예산")
        self.assertEqual(self.web(explicit_inputs=inputs)["annualAmountsThousand"], [90000,0,90000,0,90000])

    def test_wrong_task_and_missing_price_do_not_get_filled(self):
        with self.assertRaises(ValueError):
            self.web(research_service_function="social_worker_wage_survey")
        r = self.web(selected_evidence_keys=["2207435:treatment_plan:price_freeze"])
        self.assertIn("plan_unit_cost", r["missingVariables"])

    def test_own_answer_excluded_and_scope_confirmation_required(self):
        with self.assertRaises(ValueError):
            calculate_erce_web_item(treatment_plan_payload(), variable_db_path=self.db)
        p = treatment_plan_payload()
        p["method_confirmations"]["2207435:separate_treatment_basic_plan"]["separate_plan_scope_note"] = ""
        with self.assertRaises(ValueError):
            self.web(method_confirmations=p["method_confirmations"])
