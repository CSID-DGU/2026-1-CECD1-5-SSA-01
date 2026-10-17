import tempfile
import unittest
from pathlib import Path
from backend.erce.ombudsman_evidence import ombudsman_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_ombudsman import ombudsman_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class OmbudsmanTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(ombudsman_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2205719"],self.db)

    def web(self,component,**updates):
        return calculate_erce_web_item({**ombudsman_payload(component),"bill_no":"NEW_OMBUDSMAN","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_gold_display_raw_difference_and_four_components(self):
        r=run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertTrue(r["displayed_total_matches"])
        self.assertGreater(r["raw_error_percent"],0)
        self.assertLess(r["raw_error_percent"],.01)
        self.assertEqual(r["display_table"]["rounded_components_plus_meeting_total_million"],17518)
        self.assertEqual(r["display_table"]["summed_display_total_million"],17517)
        for k,part in r["parts"].items():
            self.assertEqual(list(part["result"]["annual_amounts_thousand"]),r["reusable_web_results"][k]["annualAmountsThousand"])

    def test_non_salaried_appointee_and_first_year_assets(self):
        meeting=self.web("meeting")
        self.assertEqual(meeting["annualAmountsThousand"],[19200]*5)
        self.assertTrue(all(t["appointee_salary_included"] is False for t in meeting["derivationTrace"]))
        self.assertEqual(self.web("initial_asset")["annualAmountsThousand"][1:],[0]*4)
        self.assertIn("ombudsman_asset_price_confirmation",self.web("initial_asset",ombudsman_asset_price_note="")["missingDerivationVariables"])

    def test_target_staffing_overrides_reference_denominator(self):
        normal=self.web("personnel")["annualAmountsThousand"]
        higher=self.web("personnel",explicit_inputs={"ombudsman_professional_per_office":dict(value=20,unit="person/office",source_ref="확인된새계획 전문위원20명")})["annualAmountsThousand"]
        self.assertAlmostEqual(higher[0],normal[0]*20/16,delta=1)
        asset=self.web("initial_asset",explicit_inputs={"ombudsman_professional_per_office":dict(value=20,unit="person/office",source_ref="확인된새계획 전문위원20명")})
        self.assertGreater(asset["annualAmountsThousand"][0],self.web("initial_asset")["annualAmountsThousand"][0])

    def test_missing_payroll_scope_and_self_source_excluded(self):
        keys=[k for k in ombudsman_payload("personnel")["selected_evidence_keys"] if "reference_payroll" not in k]
        self.assertIn("ombudsman_reference_payroll",self.web("personnel",selected_evidence_keys=keys)["missingDerivationVariables"])
        self.assertIn("ombudsman_confirmation",self.web("operation",ombudsman_model_confirmed=False)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            calculate_erce_web_item(ombudsman_payload("operation"),variable_db_path=self.db)
