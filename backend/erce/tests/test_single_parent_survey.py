import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.single_parent_survey_evidence import single_parent_rows
from backend.erce.child_allowance_birth_order_evidence import birth_order_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,find_method_candidates
from backend.erce.scripts.check_birth_single_parent import single_parent_payload,birth_payload
from backend.erce.web_bridge import calculate_erce_web_item


class SingleParentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(single_parent_rows()+birth_order_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2212823"],self.db)

    def payload(self):
        return {**single_parent_payload(),"bill_no":"SIMILAR_SINGLE_PARENT","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_households_children_and_execution_are_separate(self):
        r=self.calculate(self.payload())
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(r["derivationTrace"][0]["gross_children"],483000)
        self.assertEqual(r["derivationTrace"][0]["effective_recipients"],481068)
        self.assertEqual(r["annualAmountsThousand"],[577281600]*5)
        p=self.payload();p["explicit_inputs"]["single_parent_households"]=dict(value=100,unit="household",source_ref="확인된 대상100가구")
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[179280]*5)

    def test_missing_population_and_wrong_income_cohort_are_not_filled(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "households" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("single_parent_households",r["missingDerivationVariables"])
        for change in ({"single_parent_population_scope":"low_income_cash_benefit_recipients"},
                {"single_parent_projection":"automatic_growth"},{"single_parent_support_additive":False},
                {"survey_scope_note":""},{"bill_no":"2212823"},{"cutoff_date":"2025-09-09"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})

    def test_duplicate_factor_blocked_and_both_methods_discoverable(self):
        p=self.payload();p["explicit_inputs"]["participation_rate"]=dict(value=.996,unit="ratio",source_ref="중복집행계수")
        with self.assertRaisesRegex(ValueError,"duplicate"):self.calculate(p)
        found=find_method_candidates(query="아동수당 둘째 셋째 한부모가족 아동 추가지급",cutoff_date="2026-10-06",
            target_bill_no="SIMILAR_SINGLE_PARENT",db_path=self.db)
        self.assertTrue({"2212823:single_parent_survey_support","2212823:birth_order_table_calculation_policy"}
            <= {r["method_key"] for r in found})

    def test_birth_formula_kept_and_explicit_table_scenario_required(self):
        p={**birth_payload(),"bill_no":"SIMILAR_SINGLE_PARENT","evidence_mode":"holdout"}
        r=self.calculate(p)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/1e9,31.607098831)
        q=copy.deepcopy(p);q["birth_order_share_scenario"]="table3_annual"
        with self.assertRaisesRegex(ValueError,"scenario mismatch"):self.calculate(q)
