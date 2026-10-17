import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.basic_pension_staged_evidence import basic_pension_staged_rows,staged_reference_amounts
from backend.erce.scripts.check_basic_pension_staged import band_payload,decision_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.web_bridge import calculate_erce_web_item


class BasicPensionStagedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(basic_pension_staged_rows(),self.db)
        rows=[r for r in reviewed_method_rows() if r["method_key"]=="2203602:residency_exclusion_not_estimated"]
        save_method_rows(rows,self.db)

    def p(self,band):return {**band_payload(band),"bill_no":"SYNTHETIC_PENSION","evidence_mode":"holdout"}
    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_staged_rates_and_no_automatic_missing_coefficient(self):
        old,new=staged_reference_amounts()
        self.assertEqual(old,[350387,357395,364543,371834,379270])
        self.assertEqual(new["between30_50"][0],old[0])
        for band in ("lower30","between30_50"):
            r=self.calc(self.p(band))
            self.assertEqual(r["status"],"needs_input")
            self.assertEqual(r["missingVariables"],["recipient_count"])
            self.assertEqual(set(r["missingDerivationVariables"]),{"pension_take_up","pension_delta_payment_factor"})

    def test_synthetic_rates_compute_disjoint_additional_twenty_percent(self):
        p=self.p("between30_50")
        for k in ("pension_take_up","pension_delta_payment_factor"):
            p["explicit_inputs"][k]=dict(value=1,unit="ratio",source_ref="합성시험가정·실제DB에저장안함")
        r=self.calc(p)
        self.assertEqual(r["annualAmountsThousand"][0],0)
        trace=r["derivationTrace"][0]
        pop=next(x for x in basic_pension_staged_rows() if x["pension_income_band"]=="between30_50" and x["variable_key"]=="pension_elderly_population")["value"]
        self.assertAlmostEqual(trace["values"][0],pop[0]*.2)

    def test_own_answer_wrong_band_and_duplicate_rate_rejected(self):
        for change in ({"pension_income_band":"lower50"},{"start_year":2027},{"bill_no":"2203602"},{"pension_payment_model":"automatic"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p("lower30"),**change})
        p=self.p("lower30");p["explicit_inputs"]["participation_rate"]=dict(value=.7,unit="ratio",source_ref="중복")
        with self.assertRaises(ValueError):self.calc(p)

    def test_non_estimation_requires_both_unknown_population_and_delegated_scope(self):
        p={**decision_payload(),"bill_no":"SYNTHETIC_RESIDENCY","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        p=copy.deepcopy(p);p["decision_facts"]["exclusion_scope_confirmed"]=True
        with self.assertRaises(ValueError):validate_non_estimation_review(p,db_path=self.db)
