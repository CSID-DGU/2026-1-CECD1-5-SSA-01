import tempfile
import unittest
from pathlib import Path
from backend.erce.government_employment_levy import government_levy_rows, government_double_levy_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_government_double_levy import double_levy_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class GovernmentDoubleLevyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name)/"test.sqlite3"
        save_variable_rows(government_levy_rows()+government_double_levy_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] in {"2200209","2207081"}],self.db)

    def web(self, **updates):
        p = {**double_levy_payload(False),"bill_no":"NEW_DOUBLE_LEVY","evidence_mode":"holdout",**updates}
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_double_zero_band_and_statutory_price_year(self):
        r = self.web(); t = r["derivationTrace"][0]
        self.assertEqual(t["new_band_shares"]["5"],2)
        self.assertEqual(t["new_band_shares"]["1"],1)
        self.assertGreater(t["civil_won_by_band"]["5"],0)
        self.assertEqual(t["price_reference_year"],2025)
        self.assertEqual(t["minimum_base_year"],2025)
        self.assertFalse(t["netted_with_receipts"])

    def test_gold_replay_error_not_claimed_exact(self):
        r = run_regression(self.db)
        self.assertLess(r["error_percent"],.12)
        self.assertGreater(r["error_percent"],0)
        self.assertEqual(r["annual_display_matches"],0)
        self.assertAlmostEqual(r["replay_total_eok"],6570.13733)

    def test_model_and_price_year_replay_cannot_leak_to_new_bill(self):
        for changes in ({"levy_band_model":"floor_eighty_zero_one"}, {"reviewed_table_year_offset":1}, {"fiscal_reporting":"net_receipts"}):
            with self.assertRaises(ValueError):
                self.web(**changes)

    def test_missing_counts_and_law_values_not_invented(self):
        p = double_levy_payload(False)
        keys = [k for k in p["selected_evidence_keys"] if "unfilled_by_band" not in k]
        self.assertIn("government_unfilled_by_band",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.web(explicit_inputs={"levy_zero_employment_share":dict(value=1,unit="multiplier",source_ref="다른 원문 무고용100%")})
