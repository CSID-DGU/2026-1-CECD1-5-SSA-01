import tempfile
import unittest
from pathlib import Path
from backend.erce.phased_couple_pension import phased_couple_rows
from backend.erce.scripts.check_phased_couple_pension import payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class PhasedCouplePensionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(phased_couple_rows(),self.db)
        self.p={**payload(),"bill_no":"SYNTHETIC_PHASED_PENSION","evidence_mode":"holdout"}
    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_actual_observations_and_schedule_are_used(self):
        r=self.calc(self.p)
        self.assertEqual(r["status"],"computed_review")
        trend=r["derivationTrace"][-1]
        self.assertEqual(trend["reduction_schedule"],[.1,.05,0,0,0])
        self.assertAlmostEqual(trend["historical_couple_share"][-1],2968660/6758487)
        self.assertNotEqual(trend["projected_couple_share"][0],trend["projected_couple_share"][-1])
        self.assertGreater(sum(r["annualAmountsThousand"]),0)

    def test_version_future_self_and_assumption_guards(self):
        for change in ({"bill_no":"2211669"},{"cutoff_date":"2025-07-23"},{"pension_standard_vintage":"2024_10"},
            {"pension_trend_model":"fit_gold"},{"couple_recovery_model":"exact"},{"couple_recovery_note":""},{"start_year":2025}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p,**change})

    def test_freeze_model_is_explicitly_separate(self):
        r=self.calc({**self.p,"pension_trend_model":"freeze_2021_2024"})
        values=r["derivationTrace"][-1]["projected_couple_share"]
        self.assertEqual(len(set(values)),1)
