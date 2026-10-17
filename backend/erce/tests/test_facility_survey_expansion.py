import tempfile
import unittest
from pathlib import Path
from backend.erce.facility_survey_expansion_evidence import facility_survey_expansion_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_facility_survey_expansion import expansion_payload, unchanged_review_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class FacilitySurveyExpansionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(facility_survey_expansion_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2210775"],self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def payload(self):
        return {**expansion_payload(),"bill_no":"NEW_FACILITY_EXPANSION"}

    def test_delta_full_regression_and_web(self):
        r = run_regression(self.db)
        self.assertEqual(r["total_eok"],20)
        self.assertEqual(r["error_percent"],0)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertTrue(r["unverified_baseline_exclusion_blocked"])
        self.assertFalse(r["independent_evaluation"])

    def test_missing_baseline_not_assumed_zero(self):
        p = self.payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"]
            if "existing_survey_annual_budget" not in k]
        self.assertIn("existing_survey_annual_budget",self.calculate(p)["missingDerivationVariables"])

    def test_unconfirmed_expansion_needs_input(self):
        p = self.payload()
        p["facility_expansion_scenario_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_unknown_coverage_or_expansion_prevents_existing_program_exclusion(self):
        for changes in [dict(existing_coverage_comparison_complete=False),
                        dict(survey_target_and_sample_unchanged=False),
                        dict(new_service_scope_or_staffing_expansion_confirmed=True)]:
            p = unchanged_review_payload()
            p["decision_facts"] = {**p["decision_facts"],**changes}
            with self.assertRaises(ValueError):
                validate_non_estimation_review(p,db_path=self.db)

    def test_sample_ratio_not_used_for_budget_and_bad_coverage_rejected(self):
        p = self.payload()
        p["explicit_inputs"] = {"existing_survey_covered_facilities":dict(value=40,unit="facility",source_ref="다른표본 시험입력")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[400000]*5)
        p["explicit_inputs"]["existing_survey_covered_facilities"]["value"] = 526
        with self.assertRaises(ValueError):
            self.calculate(p)
