import tempfile
import unittest
from pathlib import Path
from backend.erce.activity_support_research_evidence import activity_support_research_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.scripts.check_activity_support_research import research_payload,pay_review
from backend.erce.web_bridge import calculate_erce_web_item


class ActivitySupportResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(activity_support_research_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2212766"],self.db)

    def payload(self,kind):
        return {**research_payload(kind),"bill_no":"NEW_ACTIVITY_RESEARCH","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_survey_and_plan_recurrence_not_annual_flat_cost(self):
        survey=self.calculate(self.payload("survey"));plan=self.calculate(self.payload("plan"))
        self.assertEqual(survey["annualAmountsThousand"],[90000,0,0,90000,0])
        self.assertEqual(plan["annualAmountsThousand"],[40000,0,0,0,0])

    def test_contract_scope_and_own_answer_guard(self):
        for change in ({"research_cost_scope":"field_and_contract"},{"research_service_function":"salary_only_survey"},
                       {"bill_no":"2212766"},{"cutoff_date":"2025-10-21"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload("survey"),**change})
        p=self.payload("plan");p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "plan_unit_cost" not in k]
        r=self.calculate(p);self.assertEqual(r["status"],"needs_input")
        self.assertIn("plan_unit_cost",r["missingVariables"])

    def test_law_or_confirmed_period_and_price_override_comparable(self):
        p=self.payload("survey")
        p["explicit_inputs"]={"recurrence_interval_years":dict(value=2,unit="year",source_ref="확인된별도법정주기")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[90000,0,90000,0,90000])
        p=self.payload("plan")
        p["explicit_inputs"]={"plan_unit_cost":dict(value=50000000,unit="KRW/plan",source_ref="해당계획의확인견적")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[50000,0,0,0,0])

    def test_pay_non_estimation_has_reasons_and_rejects_new_standards(self):
        p={**pay_review(),"bill_no":"NEW_ACTIVITY_PAY","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        self.assertTrue(r["source_ref"]);self.assertTrue(r["reestimate_when"])
        for key in ("pay_standard_confirmed","benefit_reflection_method_confirmed"):
            q={**p,"decision_facts":{**p["decision_facts"],key:True}}
            with self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
