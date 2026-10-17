import unittest
from backend.erce.scripts.diagnose_phased_couple_pension import diagnose


class PhasedPensionDiagnosticTests(unittest.TestCase):
    def test_conditional_check_does_not_become_fitted_variables(self):
        r=diagnose()
        self.assertTrue(r['diagnostic_only'])
        first=r['annual'][0]
        self.assertAlmostEqual(first['conditional_current_undiscounted_max'],32.615031406944)
        self.assertAlmostEqual(first['conditional_amended_undiscounted_max'],34.94467650744)
        self.assertTrue(first['current_exceeds_even_gold_display_rounding'])
        self.assertTrue(first['amended_exceeds_even_gold_display_rounding'])
        self.assertGreater(first['minimum_amended_uptake_for_gold_without_any_discount'],1)
        self.assertIn('bound_assumptions',r)
