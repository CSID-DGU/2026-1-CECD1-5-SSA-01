import tempfile
import unittest
from pathlib import Path
from backend.erce.standard_workplace_evidence import standard_workplace_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_standard_workplace import workplace_payload,capacity_payload
from backend.erce.web_bridge import calculate_erce_web_item


class StandardWorkplaceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(standard_workplace_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2200200"],self.db)

    def payload(self,scenario="increase1"):
        return {**workplace_payload(scenario),"bill_no":"NEW_STANDARD_WORKPLACE","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_three_fixed_annual_increments_and_displays(self):
        cases=[("increase1",1,[301,308,315,321,328]),("increase5",4,[1206,1232,1258,1285,1312]),
               ("increase10",8,[2412,2465,2517,2570,2624])]
        for scenario,extra,annual in cases:
            r=self.calculate(self.payload(scenario))
            self.assertEqual([round(v/1000) for v in r["annualAmountsThousand"]],annual)
            self.assertTrue(all(t["additional_applications"]==extra for t in r["derivationTrace"]))
            self.assertEqual(r["derivationTrace"][0]["reference_subsidiary_workplaces"],79)

    def test_budget_and_scope_not_automatic(self):
        r=self.calculate({**self.payload(),"budget_expansion_assumed":False})
        self.assertIn("budget_expansion_confirmation",r["missingDerivationVariables"])
        for change in [{"bill_no":"2200200"},{"workplace_form":"government_equity"},
                       {"application_increase_mode":"compound_growth"}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.calculate({**self.payload(),**change})

    def test_confirmed_applications_priority_and_no_extra_subsidy(self):
        p=self.payload()
        p["explicit_inputs"]={"annual_additional_workplaces":dict(value=2,unit="workplace/year",source_ref="확인된연간추가2건")}
        r=self.calculate(p)
        self.assertTrue(all(t["additional_applications"]==2 for t in r["derivationTrace"]))
        p["explicit_inputs"]["subsidy_rate"]=dict(value=.75,unit="ratio",source_ref="평균지원금에중복지원률 검증")
        with self.assertRaises(ValueError):self.calculate(p)

    def test_existing_capacity_decision_requires_capacity_review(self):
        p={**capacity_payload(),"bill_no":"NEW_STANDARD_WORKPLACE","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"out_of_scope");self.assertIsNone(r["amount"])
        p["decision_facts"]["existing_administration_sufficient"]=False
        with self.assertRaises(ValueError):validate_non_estimation_review(p,db_path=self.db)
