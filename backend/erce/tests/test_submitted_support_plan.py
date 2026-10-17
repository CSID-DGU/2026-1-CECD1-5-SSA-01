import tempfile
import unittest
from pathlib import Path
from backend.erce.submitted_support_plan import submitted_plan_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, find_method_candidates
from backend.erce.scripts.check_submitted_support_plan import plan_payload
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.engine import estimate_routed_item


class SubmittedPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"variables.sqlite3"
        save_variable_rows(submitted_plan_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2200482"],self.db)

    def payload(self,kind):
        return {**plan_payload(kind),"bill_no":"SIMILAR_ELDER_PLAN","evidence_mode":"holdout","variable_db_path":str(self.db)}

    def test_counts_are_candidates_and_one_time_costs_do_not_repeat(self):
        for kind, expected in (("operation",[1950000]*5),("research",[50000,0,0,0,0]),("system",[300000,0,0,0,0])):
            p = self.payload(kind)
            r = calculate_erce_web_item(p,variable_db_path=self.db)
            self.assertEqual(r["annualAmountsThousand"],expected)
        p = self.payload("operation")
        p["explicit_inputs"]={"regional_centers":{"value":10,"unit":"center","source_ref":"신규사업계획의 명시 기관수"}}
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(550000,)*5)
        for change in ({"plan_applicability_note":""},{"fiscal_scope":"national_only"},{"bill_no":"2200482"},
                       {"excluded_bill_nos":["2200482"]},{"cutoff_date":"2024-07-02"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                calculate_erce_web_item({**self.payload("operation"),**change},variable_db_path=self.db)

    def test_monthly_activity_requires_duration_and_cannot_use_table_shortcut(self):
        p=self.payload("project")
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingDerivationVariables"],["activity_months"])
        with self.assertRaises(ValueError):
            estimate_routed_item({**p,"activity_period_basis":"historical_table_unresolved_monthly_unit"})
        p["explicit_inputs"]={"activity_months":{"value":10,"unit":"month/year","source_ref":"입력된 사업계획의 10개월 활동가정"}}
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(867540,)*5)

    def test_salary_vintage_and_method_discovery(self):
        p=self.payload("staff")
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(2958768,3050784,3145635,3243483,3344328))
        with self.assertRaises(ValueError):
            estimate_routed_item({**p,"start_year":2026})
        found=find_method_candidates(query="경제적노인학대 지역사회지원체계 보호기관",cutoff_date="2026-10-06",
            target_bill_no="SIMILAR_ELDER_PLAN",db_path=self.db)
        self.assertTrue(any(r["method_key"]=="2200482:submitted_elder_protection_plan" for r in found))
