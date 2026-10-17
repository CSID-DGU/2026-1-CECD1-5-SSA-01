import unittest
from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_social_worker_survey_phase import run_regression


class ResearchHistoricalPhaseTests(unittest.TestCase):
    def payload(self, last=2023):
        return dict(route_key="research_survey", bill_no="SYNTHETIC_PHASE", cutoff_date="2026-10-10", start_year=2025, years=5,
                    explicit_inputs={"survey_unit_cost": dict(value=1000000, unit="KRW/survey", source_ref="합성 단가"),
                                     "recurrence_interval_years": dict(value=3, unit="year", source_ref="합성 주기"),
                                     "last_occurrence_year": dict(value=last, unit="year", source_ref="합성 실시이력")})

    def test_historical_phase_not_first_year_and_arbitrary_periods(self):
        self.assertEqual(estimate_routed_item(self.payload()).annual_amounts_thousand, (0, 1000, 0, 0, 1000))
        p = self.payload(2020)
        p["start_year"] = 2024
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand, (0, 0, 1000, 0, 0))

    def test_confirmed_offset_priority_and_invalid_history(self):
        p = self.payload()
        p["explicit_inputs"]["first_occurrence_offset_years"] = dict(value=0, unit="year", source_ref="확정된 개정 첫실시")
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand, (1000, 0, 0, 1000, 0))
        for last in (True, 2025, 2023.5):
            with self.subTest(last=last), self.assertRaises(ValueError):
                estimate_routed_item(self.payload(last))

    def test_regression_preserves_negative_increment(self):
        r = run_regression()
        self.assertTrue(r["official_scope_complete"])
        self.assertEqual(r["annual_thousand"], [228000, -178000, 228000, 0, 50000])
        self.assertEqual(r["total_won"], 328000000)
