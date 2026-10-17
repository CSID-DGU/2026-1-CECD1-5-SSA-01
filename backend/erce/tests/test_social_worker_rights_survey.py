import tempfile
import unittest
from pathlib import Path
from backend.erce.care_worker_survey_evidence import care_worker_survey_rows, social_worker_rights_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_social_worker_rights_survey import rights_payload
from backend.erce.web_bridge import calculate_erce_web_item


class SocialWorkerRightsSurveyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(care_worker_survey_rows() + social_worker_rights_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2203955"], self.db)

    def payload(self):
        return {**rights_payload(), "bill_no": "NEW_RIGHTS_SURVEY", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_recurrence_and_confirmed_unit_priority(self):
        r = self.calculate(self.payload())
        self.assertEqual(r["annualAmountsThousand"], [50000, 0, 0, 50000, 0])
        p = self.payload()
        p["explicit_inputs"]["survey_unit_cost"] = dict(value=60000000, unit="KRW/survey", source_ref="확인된 신규동일과업 견적")
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [60000, 0, 0, 60000, 0])

    def test_scope_and_approval_do_not_silently_fall_back(self):
        for change in [{"bill_no": "2203955"}, {"research_service_function": "social_worker_wage_survey"},
                       {"research_cost_scope": "whole_existing_survey_budget"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})
        p = self.payload()
        p["method_confirmations"] = {"2203955:separate_rights_survey": {}}
        with self.assertRaises(ValueError):
            self.calculate(p)

    def test_missing_price_and_existing_wage_budget_preserved(self):
        p = self.payload()
        p["selected_evidence_keys"] = ["2203955:rights_survey:price_freeze"]
        r = self.calculate(p)
        self.assertEqual(r["status"], "needs_input")
        self.assertIn("survey_unit_cost", r["missingVariables"])
        original = next(r for r in care_worker_survey_rows() if r["evidence_key"] == "2205985:social_worker_wage_survey:2023")
        self.assertEqual(original["value"], 178000000)
