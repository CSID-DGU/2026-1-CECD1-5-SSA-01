import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.jobseeker_livelihood_evidence import jobseeker_rows
from backend.erce.jobseeker_duration_evidence import duration_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.scripts.check_jobseeker_duration import extension_payload,service_payload
from backend.erce.web_bridge import calculate_erce_web_item


class CashDurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(jobseeker_rows()+duration_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] in {"2207706","2208052"}],self.db)

    def payload(self):
        return {**extension_payload(),"bill_no":"NEW_DURATION_BILL","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_utilization_and_extra_period_not_service_proxy(self):
        r=self.calculate(self.payload());t=r["derivationTrace"][-1]
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(t["extra_months"],5.2)
        self.assertEqual(t["total_implied_months"],10.4)
        self.assertAlmostEqual(t["utilization"],5.2/6)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,48366.58602)
        p=self.payload();p["explicit_inputs"]["new_statutory_months"]["value"]=18
        self.assertEqual(self.calculate(p)["derivationTrace"][-1]["extra_months"],10.4)

    def test_missing_cap_or_observation_is_requested(self):
        p=self.payload();p["explicit_inputs"].pop("new_statutory_months")
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("new_statutory_months",r["missingDerivationVariables"])
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "average_payment_months" not in k]
        self.assertIn("average_payment_months",self.calculate(p)["missingDerivationVariables"])

    def test_duplicate_period_wrong_rule_and_confirmed_actual_priority(self):
        for change in ({"payment_behavior_rule":"service_length_proxy"},{"payment_period_projection_note":""},
                       {"bill_no":"2208052"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload();p["explicit_inputs"]["payments_per_year"]=dict(value=12,unit="month/year",source_ref="총기간중복")
        with self.assertRaises(ValueError):self.calculate(p)
        p=self.payload();p["explicit_inputs"]["additional_payment_months"]=dict(value=3,unit="month/year",source_ref="확인된 실제추가지급행태")
        self.assertEqual(self.calculate(p)["derivationTrace"][-1]["extra_months"],3)
        p=self.payload();p["explicit_inputs"]["old_statutory_months"]["value"]=0
        with self.assertRaises(ValueError):self.calculate(p)

    def test_service_non_estimation_does_not_cancel_cash_extension(self):
        p={**service_payload(),"bill_no":"NEW_DURATION_BILL","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        for key in ("reliable_incremental_staffing_available","reliable_incremental_operating_cost_available"):
            q=copy.deepcopy(p);q["decision_facts"][key]=True
            with self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
        q=copy.deepcopy(p);q["decision_facts"]["cash_duration_change_separately_estimated"]=False
        with self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
