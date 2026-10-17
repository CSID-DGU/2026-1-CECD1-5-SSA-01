import tempfile
import unittest
from pathlib import Path
from backend.erce.government_employment_levy import government_levy_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_government_levy import levy_payload, scope_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


class GovernmentLevyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(government_levy_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2200209"], self.db)

    def payload(self):
        return {**levy_payload(False), "bill_no": "NEW_GOVERNMENT_LEVY", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_bands_and_statutory_lag_no_revenue_netting(self):
        r = self.calculate(self.payload()); t = r["derivationTrace"][0]
        self.assertEqual(t["liability_year"], 2025)
        self.assertEqual(t["price_reference_year"], 2025)
        self.assertEqual(t["civil_won_by_band"]["5"], 0)
        self.assertFalse(t["netted_with_receipts"])
        self.assertAlmostEqual(t["non_civil_won"], t["civil_won"] * .064)
        for change in [{"fiscal_reporting": "net_receipts"}, {"levy_payer_scope": "fund_receipts"},
                       {"reviewed_table_year_offset": 1}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})

    def test_own_table_replay_annual_display(self):
        r = estimate_routed_item({**levy_payload(), "variable_db_path": str(self.db)})
        self.assertEqual([round(v / 100000) for v in r.annual_amounts_thousand], [386, 399, 412, 425, 438])
        self.assertAlmostEqual(sum(r.annual_amounts_thousand) / 100000, 2059.57326)

    def test_mis_scope_not_zero_and_requires_separate_payer_review(self):
        p = {**scope_payload("levy_receipts"), "bill_no": "NEW_GOVERNMENT_LEVY", "evidence_mode": "holdout"}
        r = validate_non_estimation_review(p, db_path=self.db)
        self.assertEqual(r["decision"], "out_of_scope")
        self.assertEqual(r["source_decision_label"], "미대상")
        self.assertIsNone(r["amount"])
        p["decision_facts"]["government_employer_expense_separately_reviewed"] = False
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p, db_path=self.db)

    def test_confirmation_and_missing_bands(self):
        r = self.calculate({**self.payload(), "government_levy_scenario_confirmed": False})
        self.assertIn("government_levy_confirmation", r["missingDerivationVariables"])
        p = self.payload(); p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "unfilled_by_band" not in k]
        self.assertIn("government_unfilled_by_band", self.calculate(p)["missingDerivationVariables"])
