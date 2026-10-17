import tempfile
import unittest
from pathlib import Path

from backend.erce.child_allowance_birth_order_evidence import birth_order_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.method_evidence_store import save_method_rows,validate_selected_methods
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_child_allowance_birth_order import reviewed_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class BirthOrderChildAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"refs.sqlite3"
        save_variable_rows(birth_order_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2208381"],self.db)

    def payload(self,scenario="table4_fixed2026"):
        return {**reviewed_payload(scenario),"variable_db_path":str(self.db)}

    def test_both_scenarios_complete_and_distinct(self):
        annual=estimate_routed_item(self.payload("table3_annual"))
        fixed=estimate_routed_item(self.payload())
        self.assertEqual(sum(annual.annual_amounts_thousand),31217952138)
        self.assertEqual(sum(fixed.annual_amounts_thousand),31607098831)
        self.assertEqual(len(fixed.resolved_variables),5)
        self.assertNotEqual(sum(fixed.annual_amounts_thousand),31800000000)

    def test_synthetic_reuse_web_and_own_answer_rejection(self):
        p=self.payload()
        r=calculate_erce_web_item({**p,"bill_no":"NEW_BIRTH_ORDER_BILL"},variable_db_path=self.db)
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(len(r["derivationTrace"]),3)
        with self.assertRaisesRegex(ValueError,"target answer"):
            calculate_erce_web_item(p,variable_db_path=self.db)

    def test_share_sum_no_silent_normalization_or_missing_zero(self):
        p=self.payload();p["explicit_inputs"]["birth_share_first"]=dict(value=.9,unit="ratio",source_ref="invalid synthetic share")
        with self.assertRaisesRegex(ValueError,"sum to one"):
            estimate_routed_item(p)
        p=self.payload();p["bill_no"]="NEW_BIRTH_ORDER_BILL"
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "third_plus" not in k]
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["missingVariables"],["benefit_per_recipient"])
        self.assertIn("birth_share_third_plus",r["missingDerivationVariables"])

    def test_scope_scenario_dates_duplicate_and_units_guarded(self):
        for changes in ({"birth_order_share_scenario":"table3_annual"},{"parent_benefit_unchanged":False},
                        {"birth_order_scope_note":""},{"birth_order_scenario_note":""},
                        {"birth_order_population_basis":"actual_recipients"},{"child_population_geography":"서울"},
                        {"start_year":2025},{"cutoff_date":"2025-04-02"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                estimate_routed_item({**self.payload(),**changes})
        for key in ("participation_rate","growth_rate"):
            p=self.payload();p["explicit_inputs"][key]=dict(value=.972,unit="ratio",source_ref="duplicate")
            with self.assertRaisesRegex(ValueError,"duplicate"):
                estimate_routed_item(p)
        p=self.payload();p["explicit_inputs"]["birth_amount_first"]["unit"]="KRW/person/year"
        with self.assertRaisesRegex(ValueError,"unit/source"):
            estimate_routed_item(p)

    def test_inputs_drive_result_and_explicit_upper_has_priority(self):
        p=self.payload();p["explicit_inputs"]["birth_amount_second"]["value"]=160000
        self.assertGreater(sum(estimate_routed_item(p).annual_amounts_thousand),31607098831)
        p=self.payload();p["explicit_inputs"]["benefit_per_recipient"]=dict(value=120000,unit="KRW/person/month",source_ref="confirmed synthetic average")
        self.assertEqual(estimate_routed_item(p).resolved_variables["benefit_per_recipient"].value,120000)

    def test_selected_method_scenario_is_checked(self):
        p=self.payload();p.update(payer="government",selected_method_keys=["2208381:birth_order:table3_annual"])
        with self.assertRaisesRegex(ValueError,"scenario mismatch"):
            validate_selected_methods(p,db_path=self.db)

    def test_missing_start_requested(self):
        p=self.payload();p["bill_no"]="NEW_BIRTH_ORDER_BILL";p.pop("start_year")
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("start_year",r["missingVariables"])
