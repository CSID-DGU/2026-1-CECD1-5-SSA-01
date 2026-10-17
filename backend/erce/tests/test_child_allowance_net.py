import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_child_allowance_net import reviewed_payload
from backend.erce.support_method_operands import support_operand_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class ChildAllowanceNetTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"refs.sqlite3"
        save_variable_rows(support_operand_rows(),self.db)

    def payload(self):
        return {**reviewed_payload(),"variable_db_path":str(self.db)}

    def test_existing_sources_full_net_and_display_accuracy(self):
        e=estimate_routed_item(self.payload())
        self.assertEqual(len(e.resolved_variables),5)
        self.assertAlmostEqual(e.resolved_variables["new_recipient_count"].value[0],6179508*.972)
        self.assertAlmostEqual(e.resolved_variables["existing_recipient_count"].value[0],2177000*.972)
        self.assertLess(abs(sum(e.annual_amounts_thousand)-88100000000)/88100000000,.002)

    def test_scenario_confirmation_date_and_duplicate_rate(self):
        for changes,message in [({"parent_benefit_unchanged":False},"unchanged parent benefit"),
            ({"child_allowance_scenario":"all_under18"},"scenario mismatch"),
            ({"child_allowance_scope_note":""},"applicability"),
            ({"cutoff_date":"2024-06-17"},"future"),
            ({"start_year":2026},"year mismatch"),
            ({"estimation_start_note":""},"separate basis")]:
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):
                estimate_routed_item({**self.payload(),**changes})
        p=self.payload()
        p["explicit_inputs"]["participation_rate"]=dict(value=.972,unit="ratio",source_ref="test")
        with self.assertRaisesRegex(ValueError,"duplicate adjustment"):
            estimate_routed_item(p)

    def test_monthly_amount_units_and_geography(self):
        p=self.payload()
        p["explicit_inputs"]["benefit_per_recipient"]["unit"]="KRW/person/year"
        with self.assertRaisesRegex(ValueError,"KRW/person/month"):
            estimate_routed_item(p)
        with self.assertRaisesRegex(ValueError,"child_population_geography mismatch"):
            estimate_routed_item({**self.payload(),"child_population_geography":"서울"})

    def test_new_bill_web_connection_missing_cohort_and_no_zero_default(self):
        p=self.payload()
        p["bill_no"]="NEW_CHILD_NET"
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"computed_review")
        self.assertTrue(r["derivationTrace"])
        p["selected_evidence_keys"]=[key for key in p["selected_evidence_keys"] if "age1_population" not in key]
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("age1_population",r["missingDerivationVariables"])
        self.assertNotIn("annualAmountsThousand",r)

    def test_inconsistent_age_cohorts_rejected(self):
        p=self.payload()
        p["explicit_inputs"]["age0_population"]=dict(value=99999999,unit="person",source_ref="test")
        with self.assertRaisesRegex(ValueError,"inconsistent child age cohorts"):
            estimate_routed_item(p)
