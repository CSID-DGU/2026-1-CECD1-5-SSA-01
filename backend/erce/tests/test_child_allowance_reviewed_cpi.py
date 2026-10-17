import tempfile
import unittest
from pathlib import Path
from backend.erce.common_population_evidence import common_population_rows
from backend.erce.child_allowance_reviewed_cpi import reviewed_child_cpi_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,find_method_candidates
from backend.erce.scripts.check_child_allowance_reviewed_cpi import reviewed_payload
from backend.erce.web_bridge import calculate_erce_web_item


class ReviewedCPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(common_population_rows()+reviewed_child_cpi_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2212685"],self.db)

    def payload(self):
        return {**reviewed_payload(),"bill_no":"SIMILAR_CPI_CHILD","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_confirmed_first_year_and_compounding(self):
        r=self.calculate(self.payload());t=r["derivationTrace"]
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(t[0]["indexed_monthly_benefit"],204000)
        self.assertAlmostEqual(t[1]["indexed_monthly_benefit"],208080)
        self.assertEqual(t[0]["existing_monthly_benefit"],100000)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/1e9,35.15155163)

    def test_no_global_two_percent_or_double_indexing(self):
        for change in ({"cpi_application_confirmed":False},{"cpi_application_confirmed":None},
                {"cpi_application_note":""},{"cpi_first_year_included":False},{"existing_benefit_price_policy":"indexed"},
                {"population_geography":"서울"},{"start_year":2031,"benefit_index_base_year":2030},
                {"bill_no":"2212685"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload()
        p["explicit_inputs"]["benefit_per_recipient"]=dict(value=204000,unit="KRW/person/month",source_ref="already indexed")
        with self.assertRaisesRegex(ValueError,"duplicate"):self.calculate(p)

    def test_missing_forecast_or_start_is_requested(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "child_cpi:" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input");self.assertIn("reviewed_cpi_rates",r["missingDerivationVariables"])
        p=self.payload();p.pop("start_year")
        self.assertIn("start_year",self.calculate(p)["missingVariables"])

    def test_official_or_confirmed_alternate_rate_is_not_ignored(self):
        p=self.payload()
        p["explicit_inputs"]["reviewed_cpi_rates"]=dict(value=[.01]*5,unit="ratio/year",source_ref="사용자가확인한대안전망")
        self.assertEqual(self.calculate(p)["derivationTrace"][0]["indexed_monthly_benefit"],202000)
        found=find_method_candidates(query="아동수당13세미만 물가검토 적정성보고",cutoff_date="2026-10-06",
            target_bill_no=p["bill_no"],db_path=self.db)
        self.assertTrue(any(x["method_key"]=="2212685:child_allowance_reviewed_cpi" for x in found))
