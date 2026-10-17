import tempfile
import unittest
from pathlib import Path

from backend.erce.child_allowance_indexed_evidence import child_allowance_indexed_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_child_allowance_indexed import reviewed_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class ChildAllowanceIndexedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"refs.sqlite3"
        save_variable_rows(child_allowance_indexed_rows(),self.db)

    def payload(self):
        return {**reviewed_payload(),"variable_db_path":str(self.db)}

    def test_full_indexed_regression(self):
        e=estimate_routed_item(self.payload())
        self.assertEqual(len(e.resolved_variables),5)
        self.assertAlmostEqual(e.resolved_variables["benefit_per_recipient"].value[1],104448.4)
        self.assertAlmostEqual(e.resolved_variables["existing_recipient_count"].value[0],2177000*.972)
        self.assertEqual(sum(e.annual_amounts_thousand),29480826640)

    def test_web_new_bill_and_own_answer_exclusion(self):
        r=calculate_erce_web_item({**self.payload(),"bill_no":"NEW_INDEXED_BILL"},variable_db_path=self.db)
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual(len(r["derivationTrace"]),3)
        with self.assertRaisesRegex(ValueError,"target answer"):
            calculate_erce_web_item(self.payload(),variable_db_path=self.db)

    def test_missing_population_remains_missing_without_zero(self):
        p=self.payload();p["bill_no"]="NEW_INDEXED_BILL"
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "under19_population" not in k]
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertEqual(r["missingVariables"],["new_recipient_count"])
        self.assertIn("under19_population",r["missingDerivationVariables"])
        self.assertNotIn("annualAmountsThousand",r)

    def test_wrong_scenario_year_geography_and_duplicate_rejected(self):
        for changes in ({"child_allowance_scenario":"under2_parent_only"},
                        {"parent_benefit_unchanged":False}, {"start_year":2026},
                        {"child_population_geography":"서울"}, {"child_index_base_year":2023},
                        {"estimation_start_note":""}, {"cutoff_date":"2024-10-01"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                estimate_routed_item({**self.payload(),**changes})
        p=self.payload();p["explicit_inputs"]["participation_rate"]=dict(value=.972,unit="ratio",source_ref="test")
        with self.assertRaisesRegex(ValueError,"duplicate adjustment"):
            estimate_routed_item(p)

    def test_explicit_confirmed_upper_value_not_overwritten(self):
        p=self.payload();p["explicit_inputs"]["benefit_per_recipient"]=dict(value=110000,unit="KRW/person/month",source_ref="확인한 다른 지급액 시나리오")
        e=estimate_routed_item(p)
        self.assertEqual(e.resolved_variables["benefit_per_recipient"].value,110000)
        self.assertEqual(e.resolved_variables["benefit_per_recipient"].source_class,"target_explicit")

    def test_deflation_and_new_values_use_formula_not_saved_total(self):
        p=self.payload()
        p["explicit_inputs"]["child_cpi_rates"]=dict(value=[-.01]*5,unit="ratio/year",source_ref="합성 디플레이션 시나리오")
        e=estimate_routed_item(p)
        self.assertAlmostEqual(e.resolved_variables["benefit_per_recipient"].value[0],99000)
        self.assertLess(e.resolved_variables["benefit_per_recipient"].value[-1],99000)
        self.assertNotEqual(sum(e.annual_amounts_thousand),29480826640)
        p["explicit_inputs"]["child_cpi_rates"]["value"]=[-1]*5
        with self.assertRaisesRegex(ValueError,"invalid support operand"):
            estimate_routed_item(p)

    def test_monthly_unit_and_age_subset_enforced(self):
        p=self.payload();p["explicit_inputs"]["under8_population"]=dict(value=999999999,unit="person",source_ref="test")
        with self.assertRaisesRegex(ValueError,"inconsistent child age cohorts"):
            estimate_routed_item(p)
        p=self.payload();p["explicit_inputs"]["existing_benefit_per_recipient"]["unit"]="KRW/person/year"
        with self.assertRaisesRegex(ValueError,"KRW/person/month"):
            estimate_routed_item(p)
