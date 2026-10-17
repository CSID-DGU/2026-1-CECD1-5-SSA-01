import copy
import tempfile
import unittest
from pathlib import Path

from backend.erce.disability_couple_evidence import disability_couple_rows
from backend.erce.scripts.check_disability_couple_recovery import payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class DisabilityCoupleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(disability_couple_rows(),self.db)
        self.p={**payload(),"bill_no":"SYNTHETIC_DISABILITY_CASE","evidence_mode":"holdout"}

    def run_item(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_prior_year_cpi_and_per_person_recovery(self):
        r=self.run_item(self.p)
        self.assertEqual(r["status"],"computed_review")
        trace={t["variable_key"]:t for t in r["derivationTrace"]}
        self.assertAlmostEqual(trace["benefit_per_recipient"]["values"][0],334810*1.025)
        self.assertAlmostEqual(trace["recipient_count"]["values"][0],120867*.029)
        self.assertAlmostEqual(trace["existing_benefit_per_recipient"]["values"][0],334810*1.025*.8)
        self.assertEqual(sum(r["annualAmountsThousand"]),15035703)

    def test_missing_cohort_is_not_replaced_with_gold_total(self):
        p=copy.deepcopy(self.p)
        p["selected_evidence_keys"]=p["selected_evidence_keys"][1:]
        r=self.run_item(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingVariables"],["recipient_count"])
        self.assertIn("disability_reference_cohort",r["missingDerivationVariables"])

    def test_scope_basis_notes_start_and_supplementary_guards(self):
        for change in ({"disability_benefit_scope":"all_disability_recipients"},
                       {"disability_population_basis":"automatic"}, {"population_proxy_note":""},
                       {"supplementary_benefit_unchanged":False}, {"start_year":2026},
                       {"benefit_index_base_year":2025}, {"years":6}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_item({**self.p,**change})

    def test_own_answer_future_excluded_and_duplicate_adjustment(self):
        for change in ({"bill_no":"2204018","evidence_mode":"development_review"},
                       {"cutoff_date":"2024-09-13"}, {"excluded_bill_nos":["2204018"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_item({**self.p,**change})
        p=copy.deepcopy(self.p)
        p["explicit_inputs"]["participation_rate"]=dict(value=.7059,unit="ratio",source_ref="중복수급률")
        with self.assertRaises(ValueError):self.run_item(p)

    def test_explicit_numeric_inputs_are_not_replaced_by_reference(self):
        p=copy.deepcopy(self.p)
        p["explicit_inputs"]["recipient_count"]=dict(value=10,unit="person",source_ref="합성법안 명시인원")
        r=self.run_item(p)
        trace=next(t for t in r["derivationTrace"] if t["variable_key"]=="recipient_count")
        self.assertFalse(trace["applied"])
        self.assertLess(sum(r["annualAmountsThousand"]),100000)
