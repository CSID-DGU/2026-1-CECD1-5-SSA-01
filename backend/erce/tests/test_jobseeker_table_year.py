import unittest
from backend.erce.scripts.check_jobseeker_table_year import table_payload,run_regression
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


class TableYearTests(unittest.TestCase):
    def test_table_reproduction_keeps_statutory_scenario_separate(self):
        r=run_regression()
        self.assertLess(r["error_percent"],.002)
        self.assertAlmostEqual(r["statutory_previous_year_eok"],19799.93882)

    def test_unresolved_offset_cannot_spread_to_web_or_other_bills(self):
        p=table_payload()
        for change in ({"bill_no":"OTHER_BILL"},{"source_year_discrepancy_note":""},
                       {"evidence_mode":"holdout"},{"historical_table_year_offset":True}):
            with self.subTest(change=change),self.assertRaises(ValueError):estimate_routed_item({**p,**change})
        with self.assertRaises(ValueError):calculate_erce_web_item(p)
