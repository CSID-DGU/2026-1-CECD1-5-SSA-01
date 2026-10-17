import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.low_income_couple_pension import low_income_couple_rows
from backend.erce.scripts.check_low_income_couple_pension import payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class LowIncomeCoupleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(low_income_couple_rows(),self.db)
    def p(self,group):return {**payload(group),"bill_no":"SYNTHETIC_LOW_COUPLE","evidence_mode":"holdout"}
    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_missing_real_denominator_and_increment_factor_are_not_invented(self):
        r=self.calc(self.p("nr_full"))
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingVariables"],["recipient_count"])
        self.assertEqual(set(r["missingDerivationVariables"]),{"pension_type_recipients","pension_increment_factor"})

    def test_conditional_percentage_applies_to_its_own_type_count(self):
        p=self.p("nr_full")
        p["explicit_inputs"]["pension_type_recipients"]=dict(value=100,unit="person",source_ref="합성NR전액유형인원")
        p["explicit_inputs"]["pension_increment_factor"]=dict(value=.8,unit="ratio",source_ref="합성실제회복계수")
        r=self.calc(p);t=next(t for t in r["derivationTrace"] if t["variable_key"]=="recipient_count")
        self.assertAlmostEqual(t["values"][0],100*.296*.8)
        self.assertLess(r["annualAmountsThousand"][0],r["annualAmountsThousand"][3])

    def test_wrong_group_scope_year_and_self_source_blocked(self):
        for change in ({"pension_group":"no_nr_full"},{"low_income_scope":"all_couples"},
            {"pension_standard_vintage":"2025_03"},{"start_year":2026},{"bill_no":"2213794"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p("nr_full"),**change})

    def test_printed_zero_is_not_automatic_legal_zero(self):
        p=self.p("no_nr_reduced")
        p["explicit_inputs"]["pension_type_recipients"]=dict(value=100,unit="person",source_ref="합성인원")
        p["explicit_inputs"]["pension_increment_factor"]=dict(value=1,unit="ratio",source_ref="합성회복")
        r=self.calc(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("printed_zero_precision_review",r["missingDerivationVariables"])
        r=self.calc({**p,"accept_printed_zero_as_scenario":True})
        self.assertEqual(r["annualAmountsThousand"],[0]*5)
