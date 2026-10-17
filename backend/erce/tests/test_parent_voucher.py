import tempfile
import unittest
from pathlib import Path
from backend.erce.common_population_evidence import common_population_rows
from backend.erce.parent_voucher_indexed_evidence import parent_voucher_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,find_method_candidates
from backend.erce.scripts.check_parent_voucher import voucher_payload
from backend.erce.web_bridge import calculate_erce_web_item


class ParentVoucherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(common_population_rows()+parent_voucher_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2212022"],self.db)

    def payload(self,age=0):
        return {**voucher_payload(age),"bill_no":"NEW_PARENT_VOUCHER","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_annual_increment_and_first_year_retro_decomposed(self):
        r=self.calculate(self.payload())
        self.assertEqual(r["status"],"computed_review")
        t=r["derivationTrace"]
        self.assertEqual(t[0]["paid_months"],10)
        self.assertEqual(t[0]["retro_months"],6)
        self.assertEqual(t[0]["population"],217079)
        self.assertEqual(t[0]["monthly_increment"],24664.5)
        self.assertGreater(t[0]["retro_won"],0)
        self.assertEqual(t[1]["retro_won"],0)
        self.assertAlmostEqual(t[1]["monthly_increment"],25737.40575)
        self.assertEqual(r["annualAmountsThousand"],[87401081,69310475,75551720,81913294,88285768])

    def test_missing_rate_or_population_requests_instead_of_fabrication(self):
        for substring,key in (("voucher_growth_rate","voucher_growth_rate"),("retro_population","retro_population"),("2026-2030:common","age0_population")):
            p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if substring not in k]
            r=self.calculate(p)
            self.assertEqual(r["status"],"needs_input")
            self.assertIn(key,r["missingDerivationVariables"])
            self.assertNotIn("annualAmountsThousand",r)

    def test_semantic_period_and_self_answer_guards(self):
        p=self.payload()
        for change in ({"parent_benefit_age":1},{"parent_benefit_age":True},{"bill_no":"2212022"},
            {"population_geography":"서울"},{"statistical_sex":"female"},{"population_vintage":"2025-12"},
            {"start_year":2027,"benefit_index_base_year":2026},{"law_effective_date":"2026-03-02"},
            {"retroactive_date":"2024-07-01"},{"fiscal_scope":"national_only"},
            {"voucher_projection_basis":"cpi"},{"voucher_overlap_note":""},{"cutoff_date":"2025-08-06"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**p,**change})
        p["explicit_inputs"]={"participation_rate":{"value":.985,"unit":"ratio","source_ref":"double execution"}}
        with self.assertRaises(ValueError):self.calculate(p)

    def test_explicit_rate_priority_and_retrieval(self):
        p=self.payload()
        p["explicit_inputs"]={"voucher_growth_rate":{"value":0,"unit":"ratio/year","source_ref":"확인된 동결 시나리오"}}
        r=self.calculate(p)
        self.assertEqual(r["derivationTrace"][0]["regular_won"],0)
        self.assertEqual(r["annualAmountsThousand"][1:], [0]*4)
        found=find_method_candidates(query="2세미만 부모급여 보육서비스 이용권 상승분 연동",
            cutoff_date="2026-10-06",target_bill_no="NEW_PARENT_VOUCHER",db_path=self.db)
        self.assertTrue(any(x["method_key"]=="2212022:parent_voucher_annual_increment" for x in found))
