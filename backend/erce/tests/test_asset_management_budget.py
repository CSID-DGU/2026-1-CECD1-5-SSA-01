import tempfile
import unittest
from pathlib import Path
from backend.erce.asset_management_budget_evidence import asset_management_budget_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_asset_management_budget import asset_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class AssetBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"evidence.sqlite3"
        save_variable_rows(asset_management_budget_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207509"],self.db)

    def payload(self):
        return {**asset_payload(),"bill_no":"NEW_ASSET_INTERFACE"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_display_and_web_reuse(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["displayed_total_million"],2442)
        self.assertEqual(r["reusable_web_interface_result"]["status"],"computed_review")
        self.assertFalse(r["independent_evaluation"])

    def test_no_staffing_confirmation_blocks_proxy(self):
        p = self.payload()
        p["asset_existing_agency_no_expansion"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_missing_price_timing_or_future_rates_needs_input(self):
        p = self.payload()
        p["explicit_inputs"] = {}
        self.assertIn("asset_price_adjustment_first_year",self.calculate(p)["missingDerivationVariables"])
        p = self.payload()
        p["years"] = 6
        self.assertIn("asset_budget_cpi_year_coverage",self.calculate(p)["missingDerivationVariables"])

    def test_duplicate_staffing_rejected_and_scope_change_requires_confirmation(self):
        p = self.payload()
        p["explicit_inputs"] = {**p["explicit_inputs"],
            "headcount":dict(value=10,unit="person",source_ref="인력 입력 테스트")}
        with self.assertRaises(ValueError):
            self.calculate(p)
        p = self.payload()
        p["asset_budget_proxy_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")
