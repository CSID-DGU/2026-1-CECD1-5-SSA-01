import tempfile
import unittest
from pathlib import Path
from backend.erce.regional_resident_benefit_evidence import regional_resident_benefit_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_regional_resident_benefit import regional_payload,field_review_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class RegionalResidentBenefitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(regional_resident_benefit_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2214355"],self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def payload(self):
        return {**regional_payload(),"bill_no":"NEW_SAME_REGION_INTERFACE"}

    def test_full_replay_and_funding_components(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],dict(public_total=5,national=5,local=5))
        self.assertEqual(round(r["total_eok"]["public_total"]),552125)
        self.assertAlmostEqual(r["total_eok"]["national"]+r["total_eok"]["local"],r["total_eok"]["public_total"])
        self.assertEqual(r["field_inspection_review"]["decision"],"not_estimated")
        self.assertIsNone(r["field_inspection_review"]["amount"])

    def test_residence_filter_cannot_silently_be_omitted(self):
        p = self.payload()
        p["regional_residence_filter_omission_approved"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_region_mismatch_rejected(self):
        p = self.payload()
        p["regional_population_scope"] = "different_regions"
        with self.assertRaises(ValueError):
            self.calculate(p)

    def test_raw_precision_and_missing_history(self):
        p = self.payload()
        p["regional_trend_precision_mode"] = "raw_mean"
        r = self.calculate(p)
        self.assertEqual(r["derivationTrace"][0]["population"],4646114)
        p["selected_evidence_keys"] = []
        self.assertIn("regional_population_history",self.calculate(p)["missingDerivationVariables"])

    def test_available_inspection_plan_prevents_non_estimation(self):
        p = field_review_payload()
        p["decision_facts"]["approved_field_inspection_plan_available"] = True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)
