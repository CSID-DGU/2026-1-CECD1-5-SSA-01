import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.housing_management_evidence import housing_management_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_housing_management import housing_payload
from backend.erce.web_bridge import calculate_erce_web_item


class HousingManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(housing_management_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207600"],self.db)

    def payload(self,scenario="arrears_shared"):
        return {**housing_payload(scenario),"bill_no":"SIMILAR_HOUSING","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_two_scopes_and_price_units_do_not_mix(self):
        a=self.calculate(self.payload());b=self.calculate(self.payload("all_tenants_flat"))
        self.assertEqual(a["status"],"computed_review");self.assertEqual(b["status"],"computed_review")
        self.assertAlmostEqual(sum(a["annualAmountsThousand"])/100000,3305.90525)
        self.assertAlmostEqual(sum(b["annualAmountsThousand"])/100000,28177.77641)
        self.assertEqual(a["derivationTrace"][0]["recipient_share"],.108)
        self.assertEqual(a["derivationTrace"][0]["public_share"],.5)
        self.assertEqual(b["derivationTrace"][0]["recipient_share"],1)
        self.assertEqual(b["derivationTrace"][0]["public_share"],1)
        self.assertAlmostEqual(a["derivationTrace"][0]["base_monthly_common_fee"],46801000000/734547)

    def test_missing_data_or_years_prompts_not_zero(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "tenant_households" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input");self.assertIn("tenant_households",r["missingDerivationVariables"])
        p=self.payload();p.pop("start_year")
        self.assertIn("start_year",self.calculate(p)["missingVariables"])
        p=self.payload();p["explicit_inputs"]={"management_cpi_forecast":{"value":{"2025":.021},"unit":"year_to_ratio","source_ref":"불완전한전망"}}
        self.assertIn("cpi_year_coverage",self.calculate(p)["missingDerivationVariables"])

    def test_version_and_scope_confirmations_are_mandatory(self):
        for change in ({"use_unmatched_source_as_reference":False},{"unmatched_source_reference_note":""},
                {"housing_income_cutoff":"all_households"},{"management_scope":"utilities_included"},
                {"bill_no":"2207600"},{"price_year_note":""},{"start_year":2027}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload()
        p["selected_method_keys"]=["2207600:management_fee:all_tenants_flat"]
        p["method_selection_reasons"]={p["selected_method_keys"][0]:"잘못된시나리오"}
        with self.assertRaises(ValueError):self.calculate(p)

    def test_duplicate_adjustment_and_explicit_actual_priority(self):
        p=self.payload();p["explicit_inputs"]={"subsidy_rate":{"value":.8361,"unit":"ratio","source_ref":"국고율중복"}}
        with self.assertRaises(ValueError):self.calculate(p)
        p=self.payload("all_tenants_flat")
        p["explicit_inputs"]={"tenant_households":{"value":[100]*5,"unit":"household","source_ref":"확인된별도대상100가구"}}
        r=self.calculate(p);self.assertEqual(r["derivationTrace"][0]["gross_households"],100)
