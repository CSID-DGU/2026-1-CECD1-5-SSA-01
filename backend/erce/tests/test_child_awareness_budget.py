import tempfile
import unittest
from pathlib import Path
from backend.erce.child_awareness_budget_evidence import child_awareness_budget_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_child_awareness_budget import awareness_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class ChildAwarenessBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(child_awareness_budget_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2208744"],self.db)

    def payload(self):
        return {**awareness_payload(),"bill_no":"NEW_CHILD_AWARENESS_INTERFACE"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_self_regression_and_other_bill_interface(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["reusable_web_interface_result"]["status"],"computed_review")
        self.assertFalse(r["independent_evaluation"])

    def test_scope_confirmation_and_missing_budget(self):
        p = self.payload()
        p["child_awareness_package_confirmed"] = False
        self.assertEqual(self.calculate(p)["status"],"needs_input")
        p = self.payload()
        p["selected_evidence_keys"] = p["selected_evidence_keys"][1:]
        self.assertIn("child_awareness_annual_budget",self.calculate(p)["missingDerivationVariables"])

    def test_missing_future_cpi_not_automatically_extended(self):
        p = self.payload()
        p["years"] = 6
        self.assertIn("child_awareness_cpi_year_coverage",self.calculate(p)["missingDerivationVariables"])

    def test_duplicate_frequency_rejected(self):
        p = self.payload()
        p["explicit_inputs"] = {"frequency_per_year":dict(value=12,unit="times/year",source_ref="시험입력")}
        with self.assertRaises(ValueError):
            self.calculate(p)
