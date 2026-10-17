import tempfile
import unittest
from pathlib import Path
from backend.erce.education_training_budget_evidence import education_training_budget_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_child_asset_training import training_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class ChildAssetTrainingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(education_training_budget_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2209738"],self.db)

    def payload(self):
        return {**training_payload(),"bill_no":"NEW_TRAINING_INTERFACE"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_whole_result_and_preserved_primary(self):
        r = run_regression(self.db)
        self.assertTrue(r["primary_payload_unchanged"])
        self.assertEqual(r["education_total_eok"],35)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(round(r["total_eok"]),267705)
        self.assertEqual(r["reusable_web_interface_result"]["status"],"computed_review")
        self.assertFalse(r["independent_evaluation"])

    def test_unconfirmed_scope_or_freeze_needs_input(self):
        p = self.payload()
        p["training_package_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")
        p = self.payload()
        p["training_price_mode"] = "apply_cpi"
        self.assertEqual(self.calculate(p)["status"],"needs_input")

    def test_missing_budget_needs_input(self):
        p = self.payload()
        p["selected_evidence_keys"] = []
        self.assertIn("education_training_annual_budget",self.calculate(p)["missingDerivationVariables"])

    def test_duplicate_cpi_rejected(self):
        p = self.payload()
        p["explicit_inputs"] = {"growth_rate":dict(value=.02,unit="ratio",source_ref="시험입력")}
        with self.assertRaises(ValueError):
            self.calculate(p)
