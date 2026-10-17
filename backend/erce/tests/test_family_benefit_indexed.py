import tempfile
import unittest
from pathlib import Path

from backend.erce.family_benefit_indexed_evidence import family_indexed_rows
from backend.erce.scripts.check_family_benefit_indexed import reviewed_payloads
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class FamilyBenefitIndexedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"refs.sqlite3"
        save_variable_rows(family_indexed_rows(),self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_all_components_connected_not_saved_totals(self):
        totals=[]
        for _,p in reviewed_payloads():
            r=self.calculate(p)
            self.assertEqual(r["status"],"computed_review")
            self.assertTrue(all(t["applied"] for t in r["derivationTrace"]))
            totals.append(sum(r["annualAmountsThousand"]))
        self.assertEqual(totals,[26597927055,939846216,454150965])

    def test_parent_population_proxy_not_child_payment_rate(self):
        p=reviewed_payloads()[1][1]
        r=self.calculate(p)
        self.assertEqual(r["resolvedVariables"]["recipient_count"]["value"][0],217226)
        self.assertTrue(r["resolvedVariables"]["recipient_count"]["is_assumption"])
        self.assertAlmostEqual(r["resolvedVariables"]["benefit_per_recipient"]["value"][0],1022000)
        p["explicit_inputs"]["participation_rate"]=dict(value=.972,unit="ratio",source_ref="incorrect child payment rate")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.calculate(p)

    def test_missing_population_prompts_instead_of_zero(self):
        p=reviewed_payloads()[1][1]
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "population" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingVariables"],["recipient_count"])
        self.assertIn("parent_population",r["missingDerivationVariables"])
        self.assertNotIn("annualAmountsThousand",r)

    def test_age_proxy_year_and_geography_are_guarded(self):
        base=reviewed_payloads()[1][1]
        for changes in ({"parent_benefit_age":1},{"parent_benefit_age":True},
                        {"parent_population_proxy_note":""},{"parent_population_basis":"actual_recipients"},
                        {"child_population_geography":"서울"},{"start_year":2026},
                        {"child_index_base_year":2023},{"family_index_scope_note":""},
                        {"cutoff_date":"2026-10-01"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.calculate({**base,**changes})

    def test_floor_deflation_uses_inputs_and_not_target_amount(self):
        for _,p in reviewed_payloads():
            cpi="child_cpi_rates" if "under18" in p["support_derivation"] else "parent_cpi_rates"
            p["explicit_inputs"][cpi]=dict(value=[-.5]*5,unit="ratio/year",source_ref="synthetic deflation")
            r=self.calculate(p)
            floor=p["explicit_inputs"]["minimum_monthly_amount"]["value"]
            self.assertTrue(all(v==floor for v in r["resolvedVariables"]["benefit_per_recipient"]["value"]))
            if "parent" in p["support_derivation"] and p["parent_benefit_age"]==0:
                self.assertTrue(all(v<0 for v in r["annualAmountsThousand"]))

    def test_monthly_units_missing_floor_and_explicit_priority(self):
        p=reviewed_payloads()[1][1]
        p["explicit_inputs"]["minimum_monthly_amount"]["unit"]="KRW/person/year"
        with self.assertRaisesRegex(ValueError,"expected sourced"):
            self.calculate(p)
        p=reviewed_payloads()[1][1]
        p["explicit_inputs"].pop("minimum_monthly_amount")
        self.assertIn("minimum_monthly_amount",self.calculate(p)["missingDerivationVariables"])
        p=reviewed_payloads()[1][1]
        p["explicit_inputs"]["recipient_count"]=dict(value=100,unit="person",source_ref="confirmed synthetic recipients")
        self.assertEqual(self.calculate(p)["resolvedVariables"]["recipient_count"]["value"],100)

    def test_new_bill_reuse_and_separate_parent_change(self):
        p=reviewed_payloads()[0][1]
        self.assertEqual(self.calculate({**p,"bill_no":"NEW_FAMILY_BILL"})["status"],"computed_review")
        with self.assertRaisesRegex(ValueError,"handled separately"):
            self.calculate({**p,"parent_benefit_unchanged":True})

    def test_missing_start_is_requested(self):
        p=reviewed_payloads()[1][1];p.pop("start_year")
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("start_year",r["missingVariables"])
