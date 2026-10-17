import tempfile
import unittest
from pathlib import Path
from backend.erce.jobseeker_livelihood_evidence import jobseeker_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review,find_method_candidates
from backend.erce.scripts.check_jobseeker_livelihood import allowance_payload,service_review
from backend.erce.web_bridge import calculate_erce_web_item


class JobseekerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(jobseeker_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207706"],self.db)

    def payload(self):
        return {**allowance_payload(),"bill_no":"NEW_JOBSEEKER","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_previous_year_floor_and_actual_months(self):
        r=self.calculate(self.payload());t=r["derivationTrace"]
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(t[0]["floor_reference_year"],2025)
        self.assertEqual(t[0]["monthly_floor"],765444)
        self.assertEqual(t[0]["effective_recipients"],219743.44)
        self.assertEqual(t[0]["payment_months"],5.2)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,19799.93882)
        self.assertEqual([round(x/100000) for x in r["annualAmountsThousand"]],[3033,3474,3937,4423,4934])

    def test_missing_or_wrong_domain_does_not_use_population_or_cpi(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "recognized_jobseekers" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("recognized_jobseekers",r["missingDerivationVariables"])
        for change in ({"jobseeker_cohort":"all_unemployed"},{"livelihood_floor_projection":"cpi_2_percent"},
                       {"livelihood_floor_base_year":2024},{"start_year":2025},
                       {"payment_scope_note":""},{"bill_no":"2207706"},{"cutoff_date":"2025-02-17"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload();p.pop("start_year")
        self.assertIn("start_year",self.calculate(p)["missingVariables"])

    def test_explicit_source_priority_and_service_period_not_cash_period(self):
        p=self.payload()
        p["explicit_inputs"]["recognized_jobseekers"]=dict(value=[100,100],unit="person",source_ref="확인된 별도인정인원100")
        self.assertEqual(self.calculate(p)["derivationTrace"][0]["effective_recipients"],98)
        for key,value,unit in (("average_payment_months",24,"month/year"),("iap_completion_rate",1.2,"ratio"),
                               ("participation_rate",.98,"ratio")):
            q=self.payload();q["explicit_inputs"][key]=dict(value=value,unit=unit,source_ref="부적절입력")
            with self.assertRaises(ValueError):self.calculate(q)

    def test_sourced_non_estimation_is_not_zero_or_cash_non_estimation(self):
        p={**service_review(),"bill_no":"NEW_SERVICE_DURATION","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated")
        self.assertIsNone(r["amount"]);self.assertTrue(r["source_ref"]);self.assertTrue(r["reestimate_when"])
        for key in ("cash_payment_duration_extended","reliable_incremental_staffing_available","reliable_incremental_operating_cost_available"):
            q={**p,"decision_facts":{**p["decision_facts"],key:True}}
            with self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
        found=find_method_candidates(query="구직촉진수당 전년도생계급여최저보장수준 취업지원서비스2년기간연장",
            cutoff_date="2026-10-06",target_bill_no="NEW_SERVICE_DURATION",db_path=self.db)
        self.assertTrue({"2207706:jobseeker_livelihood_previous_year","2207706:service_duration_not_estimated"}
            <= {r["method_key"] for r in found})
