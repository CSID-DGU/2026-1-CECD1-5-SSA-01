from __future__ import annotations

import unittest

from backend.erce_web.research_service_unit_cost_registry import (
    get_research_service_benchmark,
    research_service_formula_inputs,
)


class ResearchServiceUnitCostRegistryTest(unittest.TestCase):
    def test_future_benchmark_cannot_leak_into_historical_target(self) -> None:
        with self.assertRaises(KeyError):
            get_research_service_benchmark(
                "research_plan", "교육부", as_of_date="2024-07-24"
            )

    def test_education_ministry_plan_and_survey_inputs(self) -> None:
        plan = research_service_formula_inputs(
            "research_plan", "교육부", as_of_date="2024-07-25"
        )
        survey = research_service_formula_inputs(
            "research_survey", "교육부", as_of_date="2024-07-25"
        )
        self.assertEqual(plan["plan_unit_cost"]["value"], 32_000_000)
        self.assertEqual(plan["recurrence_interval_years"]["value"], 5)
        self.assertEqual(survey["survey_unit_cost"]["value"], 22_000_000)


if __name__ == "__main__":
    unittest.main()
