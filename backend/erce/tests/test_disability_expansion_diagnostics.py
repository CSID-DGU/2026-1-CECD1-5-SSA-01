import unittest
from backend.erce.disability_recipient_history import disability_recipient_history_rows
from backend.erce.scripts.diagnose_disability_expansion import diagnose


class DisabilityDiagnosticTests(unittest.TestCase):
    def test_historical_age_counts_are_reconciled_and_not_projected(self):
        rows=disability_recipient_history_rows()
        self.assertEqual(sum(r["value"] for r in rows),364712)
        for row in rows:
            self.assertEqual(sum(row["component_counts"].values()),row["value"])
            self.assertEqual(row["value_years"],[2018])

    def test_baseline_subtraction_explains_sign_of_total_gap(self):
        d=diagnose()
        self.assertAlmostEqual(d["current_cost_difference_eok"],-3141.502547,places=5)
        self.assertAlmostEqual(d["expanded_cost_difference_eok"],-693.253492,places=5)
        self.assertGreater(d["expanded_cost_difference_eok"]-d["current_cost_difference_eok"],2400)
