import tempfile
import unittest
from pathlib import Path
from backend.erce.prefunded_annual_survey_evidence import prefunded_survey_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_prefunded_annual_survey import survey_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class PrefundedSurveyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(prefunded_survey_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2216008"],self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def payload(self):
        return {**survey_payload(),"bill_no":"NEW_PREFUNDED_INTERFACE"}

    def test_conditional_replay_and_baseline_excluded(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["result"]["annual_amounts_thousand"][0],0)
        self.assertTrue(r["reference_scenario"])
        self.assertFalse(r["independent_evaluation"])

    def test_lag_is_not_silently_accepted(self):
        p = self.payload()
        p["survey_lagged_cpi_assumption_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_future_funding_assumption_required(self):
        p = self.payload()
        p["future_unfunded_survey_assumption_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_calendar_future_cpi_not_automatically_extended(self):
        p = {**survey_payload(False),"bill_no":"NEW_CALENDAR"}
        self.assertIn("prefunded_survey_cpi_year_coverage",self.calculate(p)["missingDerivationVariables"])

    def test_later_funding_can_be_subtracted_and_missing_baseline_not_zero(self):
        p = self.payload()
        p["explicit_inputs"] = {"prefunded_survey_existing_budget":dict(value={
            "2026":870000000,"2027":886530000},unit="year_to_KRW",source_ref="추가예산입력 테스트")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"][:2],[0,0])
        p = self.payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "funded_budget" not in k]
        self.assertIn("prefunded_survey_existing_budget",self.calculate(p)["missingDerivationVariables"])
