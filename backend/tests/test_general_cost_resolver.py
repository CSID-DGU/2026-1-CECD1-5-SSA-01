from __future__ import annotations

import unittest

from backend.erce_web.economic_forecast_registry import growth_input_from_series
from backend.erce_web.general_cost_resolver import request_from_dict, resolve_general_cost


class GeneralCostResolverTest(unittest.TestCase):
    def test_periodic_research_plan_and_annual_survey_formulas(self) -> None:
        plan = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "research_plan",
            "formula_key": "PERIODIC_RESEARCH_PLAN_V1",
            "years": 5,
            "start_year": 2025,
            "inputs": {
                "plan_unit_cost": {"value": 32_000_000, "unit": "KRW/plan", "source": "official"},
                "recurrence_interval_years": {"value": 5, "unit": "year", "source": "official"},
            },
        }))
        survey = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "research_survey",
            "formula_key": "ANNUAL_RESEARCH_SURVEY_V1",
            "years": 5,
            "start_year": 2025,
            "inputs": {
                "survey_unit_cost": {"value": 22_000_000, "unit": "KRW/survey/year", "source": "official"},
            },
        }))
        self.assertEqual(plan.annual_amounts_thousand, [32_000, 0, 0, 0, 0])
        self.assertEqual(survey.annual_amounts_thousand, [22_000] * 5)
        self.assertEqual(
            sum(plan.annual_amounts_thousand) + sum(survey.annual_amounts_thousand),
            142_000,
        )
    def test_personnel_average_formula_is_connected(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "personnel",
            "component": "salary",
            "formula_key": "PERSONNEL_AVERAGE_V1",
            "years": 2,
            "inputs": {
                "headcount": {"value": 10, "unit": "person", "source": "target_document"},
                "salary_per_person": {
                    "value": 50_000_000,
                    "unit": "KRW/person/year",
                    "source": "official_standard",
                },
            },
        }))
        self.assertEqual(result.annual_amounts_thousand, [500_000, 500_000])

    def test_personnel_derived_costs_accept_annual_salary_and_rate_series(self) -> None:
        inputs = {
            "annual_salary_amount": {"value": [100_000_000, 120_000_000],
                                     "unit": "KRW/year", "source": "calculated_salary"},
        }
        for formula_key, rate_key, rate, expected in (
            ("PERSONNEL_EMPLOYER_CONTRIBUTION_V1", "employer_contribution_rate",
             [0.13, 0.14], [13_000, 16_800]),
            ("PERSONNEL_BASIC_EXPENSE_V1", "basic_expense_ratio",
             0.06, [6_000, 7_200]),
        ):
            with self.subTest(formula_key=formula_key):
                result = resolve_general_cost(request_from_dict({
                    "cost_nature": "personnel", "component": "derived_staff_cost",
                    "formula_key": formula_key, "years": 2,
                    "inputs": {**inputs, rate_key: {"value": rate, "unit": "ratio",
                                                  "source": "precedent"}},
                }))
                self.assertEqual(result.status, "computed_review")
                self.assertEqual(result.annual_amounts_thousand, expected)

    def test_direct_annual_amount(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "formula_key": "DIRECT_ANNUAL_AMOUNT_V1",
            "years": 3,
            "start_year": 2027,
            "inputs": {
                "annual_amount": {"value": 185000000, "unit": "KRW/year", "source": "precedent"}
            },
        }))
        self.assertEqual(result.status, "computed_review")
        self.assertEqual(result.year_labels, ["2027", "2028", "2029"])
        self.assertEqual(result.annual_amounts_thousand, [185000, 185000, 185000])

    def test_information_system_operation_formula_applies_growth(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "information_system",
            "formula_key": "INFORMATION_SYSTEM_OPERATION_V1",
            "years": 3,
            "inputs": {
                "annual_operating_amount": {
                    "value": 298_000_000,
                    "unit": "KRW/year",
                    "source": "precedent",
                },
                "growth_rate": {
                    "value": 0.02,
                    "unit": "ratio/year",
                    "source": "official_forecast",
                },
            },
        }))
        self.assertEqual(result.annual_amounts_thousand, [298_000, 303_960, 310_039])

    def test_information_system_operation_staff_formula(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "information_system",
            "formula_key": "INFORMATION_SYSTEM_OPERATION_STAFF_V1",
            "years": 2,
            "inputs": {
                "operation_headcount": {
                    "value": 3,
                    "unit": "person",
                    "source": "target_or_comparable_precedent",
                },
                "annual_labor_cost_per_person": {
                    "value": 99_333_333,
                    "unit": "KRW/person/year",
                    "source": "official_labor_rate",
                },
                "growth_rate": {
                    "value": 0.02,
                    "unit": "ratio/year",
                    "source": "official_forecast",
                },
            },
        }))
        self.assertEqual(result.annual_amounts_thousand, [298_000, 303_960])

    def test_existing_system_uses_total_actual_cost_and_yearly_wage_forecast(self) -> None:
        forecast_inputs = growth_input_from_series(
            "nabo_nominal_wage_2025_07",
            base_year=2025,
            start_year=2027,
            years=5,
        )
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "information_system",
            "formula_key": "INFORMATION_SYSTEM_OPERATION_V1",
            "years": 5,
            "start_year": 2027,
            "inputs": {
                "annual_operating_amount": {
                    "value": 297_600_000,
                    "unit": "KRW/year",
                    "source": "existing_system_actual_cost",
                },
                **forecast_inputs,
            },
        }))
        self.assertEqual(result.status, "computed_review")
        self.assertEqual(
            result.annual_amounts_thousand,
            [320_956, 333_153, 345_812, 358_953, 372_593],
        )

    def test_yearly_forecast_rejects_a_missing_calendar_year(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "information_system",
            "formula_key": "INFORMATION_SYSTEM_OPERATION_V1",
            "years": 2,
            "start_year": 2027,
            "inputs": {
                "annual_operating_amount": {
                    "value": 298_000_000,
                    "unit": "KRW/year",
                    "source": "official_budget",
                },
                "base_year": {"value": 2025, "unit": "year", "source": "budget"},
                "growth_rates_by_year": {
                    "value": {"2026": 0.039, "2028": 0.038},
                    "unit": "ratio/year",
                    "source": "official_forecast",
                },
            },
        }))
        self.assertEqual(result.status, "needs_evidence")
        self.assertEqual(result.missing_variables, ["growth_rates_by_year:2027"])

    def test_missing_required_input_is_not_invented(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "transfers",
            "component": "cash_benefit",
            "formula_key": "TRANSFER_RECIPIENT_V1",
            "inputs": {
                "recipient_count": {"value": 100, "unit": "person", "source": "bill"}
            },
        }))
        self.assertEqual(result.status, "needs_evidence")
        self.assertEqual(result.missing_variables, ["benefit_per_recipient"])

    def test_committee_formula_supports_fixed_and_yearly_event_counts(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "formula_key": "COMMITTEE_MEETING_ALLOWANCE_V1",
            "years": 5,
            "start_year": 2027,
            "inputs": {
                "committee_components": {
                    "value": [{
                        "paid_members": 4,
                        "meetings_per_instance": 1,
                        "instances_per_year": [2, 1, 2, 5, 1],
                        "meeting_unit_price": 350_000,
                    }],
                    "unit": "component_bundle",
                    "source": "target_and_official_evidence",
                }
            },
        }))
        self.assertEqual(result.status, "computed_review")
        self.assertEqual(result.annual_amounts_thousand, [2_800, 1_400, 2_800, 7_000, 1_400])

    def test_committee_formula_sums_multiple_groups(self) -> None:
        result = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "formula_key": "COMMITTEE_MEETING_ALLOWANCE_V1",
            "years": 1,
            "inputs": {
                "committee_components": {
                    "value": [
                        {"paid_members": 8, "annual_meetings": 9, "meeting_unit_price": 300_000},
                        {"paid_members": 2, "annual_meetings": 4, "meeting_unit_price": 300_000},
                    ],
                    "unit": "component_bundle",
                    "source": "target_and_official_evidence",
                }
            },
        }))
        self.assertEqual(result.annual_amounts_thousand, [24_000])


if __name__ == "__main__":
    unittest.main()
