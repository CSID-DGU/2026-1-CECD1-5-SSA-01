import tempfile
import unittest
from pathlib import Path
from backend.erce.levy_sector_evidence import levy_sector_rows,EXPENSE,RECEIPTS
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_levy_sectors import sector_payload,zero_band_review,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class LevySectorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(levy_sector_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2208360"],self.db)

    def web(self,route=EXPENSE,**updates):
        return calculate_erce_web_item({**sector_payload(route),"bill_no":"NEW_SECTOR_LEVY","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_expense_years_and_reference_difference_reported(self):
        r=run_regression(self.db)
        self.assertEqual(r["parts"][0]["annual_display_matches"],5)
        self.assertEqual(round(r["parts"][0]["total_eok"]),2596)
        self.assertEqual(r["parts"][1]["annual_display_matches"],5)
        self.assertTrue(all(p["displayed_total_matches"] for p in r["parts"]))
        self.assertTrue(all(p["engine_and_web_same"] for p in r["parts"]))
        t=self.web()["derivationTrace"][0]
        self.assertEqual(t["liability_year"],2025)
        self.assertAlmostEqual(t["amount_won"],t["sector_amounts_won"]["civil"]+t["sector_amounts_won"]["non_civil"])

    def test_reference_disclosure_netting_and_ratio_proxy_blocked(self):
        self.assertEqual(self.web(RECEIPTS)["estimatePurpose"],"reference_scenario")
        for updates in ({"reference_notice":""},{"estimate_purpose":"official_expense"}):
            with self.assertRaises(ValueError):
                self.web(RECEIPTS,**updates)
        with self.assertRaises(ValueError):
            self.web(fiscal_reporting="net_receipts")
        with self.assertRaises(ValueError):
            self.web(explicit_inputs={"government_non_civil_share":dict(value=.064,unit="ratio",source_ref="부문별인원과중복대리비율")})

    def test_non_estimation_requires_unconfirmed_zero_band_not_zero_amount(self):
        p={**zero_band_review(),"bill_no":"NEW_SECTOR_LEVY","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated")
        self.assertIsNone(r["amount"])
        p["decision_facts"]["zero_employment_new_multiplier_confirmed"]=True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)

    def test_missing_counts_and_own_answer_exclusion(self):
        keys=[k for k in sector_payload()["selected_evidence_keys"] if "sector_unfilled" not in k]
        self.assertIn("levy_sector_unfilled",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            calculate_erce_web_item(sector_payload(),variable_db_path=self.db)

    def test_price_card_is_reusable_unit_not_answer_total(self):
        p=sector_payload();rows=levy_sector_rows()
        card=next(r for r in rows if r["variable_key"]=="levy_band_delta_price_card")
        self.assertEqual(card["value"]["monthly_delta_by_band"]["2"],395972)
        self.assertNotIn("annual_amount",card["value"])
        self.assertIn("levy_price_card_confirmation",self.web(levy_price_card_reuse_confirmed=False)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.web(explicit_inputs={"levy_band_difference_weight":dict(value=.3,unit="ratio",source_ref="다른가산배분")})
        counts=next(r["value"] for r in rows if r["variable_key"]=="levy_sector_unfilled")
        counts={k:dict(v) for k,v in counts.items()};counts["private"]["2"]+=100
        before=self.web(RECEIPTS)["annualAmountsThousand"]
        after=self.web(RECEIPTS,explicit_inputs={"levy_sector_unfilled":dict(value=counts,unit="sector_band_to_person",source_ref="합성 다른사업체 인원증가")})["annualAmountsThousand"]
        self.assertTrue(all(b>a for a,b in zip(before,after)))
