import tempfile
import unittest
from pathlib import Path
from backend.erce.protected_child_insurance_evidence import protected_child_insurance_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_protected_child_insurance import insurance_payload,survey_review_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class ProtectedChildInsuranceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(protected_child_insurance_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2216665"],self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_reference_replay_and_law_scope_remains_different(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertNotEqual(r["law_under18_total_eok"],r["total_eok"])
        self.assertEqual(r["survey_expansion_review"]["decision"],"not_estimated")
        self.assertIsNone(r["survey_expansion_review"]["amount"])
        self.assertFalse(r["independent_evaluation"])

    def test_age_conflict_requires_reference_and_approval(self):
        p = {**insurance_payload(True),"bill_no":"NEW_INSURANCE"}
        p["protected_child_age_conflict_approved"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")
        p["protected_child_age_conflict_approved"] = True
        p["estimate_purpose"] = "normal"
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_normal_mode_is_zero_to_seventeen(self):
        p = {**insurance_payload(),"bill_no":"NEW_LAW_INSURANCE"}
        r = self.calculate(p)
        self.assertEqual(r["derivationTrace"][0]["population_age_max"],17)

    def test_missing_share_and_future_population_not_invented(self):
        p = {**insurance_payload(),"bill_no":"NEW_MISSING_INSURANCE"}
        p["selected_evidence_keys"] = p["selected_evidence_keys"][:1]
        self.assertIn("protected_child_population_share",self.calculate(p)["missingDerivationVariables"])
        p = {**insurance_payload(),"bill_no":"NEW_FUTURE_INSURANCE","years":6}
        self.assertIn("protected_child_population_year_coverage",self.calculate(p)["missingDerivationVariables"])

    def test_new_survey_design_invalidates_non_estimation(self):
        p = survey_review_payload()
        p["decision_facts"]["expanded_sample_size_confirmed"] = True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)
