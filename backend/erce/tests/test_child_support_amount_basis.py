import tempfile
import unittest
from pathlib import Path
from backend.erce.child_support_advance_evidence import child_support_rows
from backend.erce.child_support_amount_basis import amount_basis_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_child_support_amount_basis import proxy_payload,standard_payload,reference_reproduction_status
from backend.erce.web_bridge import calculate_erce_web_item


class AmountBasisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(child_support_rows()+amount_basis_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] in {"2201707","2203287"}],self.db)

    def proxy(self):
        return {**proxy_payload(),"bill_no":"NEW_STANDARD_PROXY","evidence_mode":"holdout"}

    def standard(self):
        return {**standard_payload(),"bill_no":"NEW_STANDARD_TABLE","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_proxy_reproduces_only_after_explicit_approval(self):
        p=self.proxy()
        self.assertAlmostEqual(sum(self.calculate(p)["annualAmountsThousand"])/100000,3216.806)
        for change in ({"proxy_assumption_confirmed":False},{"proxy_basis_note":""},{"statutory_basis_difference_note":""}):
            r=self.calculate({**p,**change})
            self.assertEqual(r["status"],"needs_input")
            self.assertIn("policy_proxy_confirmation",r["missingDerivationVariables"])
        with self.assertRaises(ValueError):self.calculate({**p,"bill_no":"2203287"})

    def test_standard_mode_never_falls_back_to_twenty_manwon(self):
        r=self.calculate(self.standard())
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingDerivationVariables"],["standard_support_cells","standard_cell_weights"])

    def test_reference_completion_keeps_raw_error_and_separate_mode(self):
        proxy = self.calculate(self.proxy())
        result = reference_reproduction_status(proxy["annualAmountsThousand"], proxy["status"])
        self.assertTrue(result["reproduction_complete"])
        self.assertEqual(result["displayed_total_eok"], 3216.81)
        self.assertGreater(result["raw_error_percent"], 0)
        self.assertEqual(self.calculate(self.standard())["status"], "needs_input")
        self.assertFalse(reference_reproduction_status([0] * 5, "computed_review")["reproduction_complete"])
        self.assertFalse(reference_reproduction_status(proxy["annualAmountsThousand"], "needs_input")["reproduction_complete"])

    def supplied_standard(self):
        p=self.standard()
        cells={"A":dict(age_band="0~2세",income_band="월400만원",base_monthly_support=1000000,
                       adjustment_won=200000,parents_combined_income=4000000,debtor_income=2000000),
               "B":dict(age_band="3~5세",income_band="월700만원",base_monthly_support=1500000,
                       adjustment_won=-100000,parents_combined_income=7000000,debtor_income=2100000)}
        p["explicit_inputs"]={"standard_support_cells":dict(value=cells,unit="income_age_support_cells",source_ref="합성원문기준계산검증용자료"),
            "standard_cell_weights":dict(value={"A":.25,"B":.75},unit="cell_to_ratio",source_ref="합성코호트구성비")}
        return p

    def test_adjustments_income_share_and_cohort_weights(self):
        r=self.calculate(self.supplied_standard())
        self.assertEqual(r["status"],"computed_review")
        self.assertAlmostEqual(r["derivationTrace"][0]["weighted_monthly_amount"],465000)
        self.assertEqual(r["derivationTrace"][0]["cell_details"][0]["monthly_amount"],600000)

    def test_invalid_income_weights_or_flat_override_rejected(self):
        p=self.supplied_standard()
        p["explicit_inputs"]["standard_cell_weights"]["value"]={"A":.3,"B":.8}
        with self.assertRaises(ValueError):self.calculate(p)
        p=self.supplied_standard()
        p["explicit_inputs"]["standard_support_cells"]["value"]["A"]["parents_combined_income"]=0
        with self.assertRaises(ValueError):self.calculate(p)
        p=self.supplied_standard()
        p["explicit_inputs"]["advance_monthly_amount"]=dict(value=200000,unit="KRW/person/month",source_ref="표준모드잘못된정액")
        with self.assertRaises(ValueError):self.calculate(p)
