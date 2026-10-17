import tempfile
import unittest
from pathlib import Path
from backend.erce.survey_annualization_evidence import survey_annualization_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_care_leaver_survey import care_survey_payload,counselling_review,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class CareLeaverSurveyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(survey_annualization_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207176"],self.db)

    def web(self,**updates):
        return calculate_erce_web_item({**care_survey_payload(),"bill_no":"NEW_CARE_SURVEY","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_gold_phase_and_display_without_gross_double_counting(self):
        r=run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["displayed_total_million"],671)
        self.assertLess(r["raw_error_percent"],.06)
        self.assertTrue(r["engine_and_web_same"])
        self.assertEqual(r["web_result"]["annualAmountsThousand"][0],0)
        self.assertEqual(r["web_result"]["annualAmountsThousand"][3],0)
        self.assertEqual([t["year"] for t in r["web_result"]["derivationTrace"] if t["baseline_survey_due"]],[2026,2029])

    def test_new_law_existing_cycle_is_not_hardcoded_three(self):
        inputs=dict(care_survey_payload()["explicit_inputs"])
        inputs["existing_survey_interval"]=dict(value=2,unit="year",source_ref="합성 새원문기존2년주기")
        r=self.web(explicit_inputs=inputs)
        self.assertEqual([t["year"] for t in r["derivationTrace"] if t["baseline_survey_due"]],[2027,2029])
        inputs["amended_survey_interval"]=dict(value=2,unit="year",source_ref="합성 새원문개정2년주기")
        with self.assertRaises(ValueError):
            self.web(explicit_inputs=inputs)

    def test_missing_unit_and_self_source_blocked(self):
        keys=[k for k in care_survey_payload()["selected_evidence_keys"] if "unit_cost" not in k]
        self.assertIn("survey_unit_cost",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            calculate_erce_web_item(care_survey_payload(),variable_db_path=self.db)

    def test_existing_counselling_exclusion_needs_positive_evidence_and_same_scope(self):
        p={**counselling_review(),"bill_no":"NEW_CARE_SURVEY","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"no_incremental_cost")
        self.assertIsNone(r["amount"])
        with self.assertRaises(ValueError):
            validate_non_estimation_review({**p,"reliable_estimation_basis_available":False},db_path=self.db)
        p["decision_facts"]["new_service_scope_or_staffing_expansion_confirmed"]=True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)
