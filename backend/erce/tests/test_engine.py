from __future__ import annotations

import unittest

from backend.erce.engine import estimate_routed_item
from backend.erce.evidence_registry import select_committee_pack
from backend.erce.formula_registry import formula_for_route
from backend.erce.formula_registry import ERCE_FORMULA_ROUTES, DIRECT_FORMULA_ROUTE_KEYS
from backend.erce.route_tree import formula_leaf_routes, route_for_path
from backend.general_cost_resolver import FORMULAS


class ERCEEngineTest(unittest.TestCase):
    def test_fee_revenue_average_and_channel_shift_use_fixed_formulas(self) -> None:
        base = {"bill_no": "2215482", "start_year": 2027, "years": 5,
                "explicit_inputs": {"exemption_rate": 1},
                "actual_inputs": {"historical_annual_fee_revenues": {
                    "value": [74014000000,78829000000,72665000000,73226000000,73973000000],
                    "source_ref": "정답 표2 재현 전용, 독립 검증 아님"}}}
        baseline = estimate_routed_item({**base, "route_path": ["세외수입감소", "수수료면제", "기존수입평균"]})
        self.assertEqual(baseline.annual_amounts_thousand, (74541400,) * 5)
        shifted = estimate_routed_item({**base, "route_path": ["세외수입감소", "수수료면제", "무료채널전환반영"],
            "actual_inputs": {**base["actual_inputs"], "other_channel_base_revenue": 6077000000,
                              "other_channel_base_year": 2024},
            "explicit_inputs": {"exemption_rate": 1, "other_channel_growth_rate": -.074, "channel_shift_rate": .5}})
        self.assertGreater(sum(shifted.annual_amounts_thousand), sum(baseline.annual_amounts_thousand))
        self.assertTrue(all(a > b for a,b in zip(shifted.annual_amounts_thousand, shifted.annual_amounts_thousand[1:])))
        # Synthetic test independent of the answer: average 1500 + .5*200*.9^2 = 1581.
        simple = estimate_routed_item({"route_key": "non_tax_fee_channel_shift", "start_year": 2026, "years": 1,
            "explicit_inputs": {"historical_annual_fee_revenues": [1000000,2000000],
                "exemption_rate": 1, "other_channel_base_revenue": 200000,
                "other_channel_base_year": 2024, "other_channel_growth_rate": -.1, "channel_shift_rate": .5}})
        self.assertEqual(simple.annual_amounts_thousand, (1581,))
        for invalid in (-.1, 1.1, float("nan")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                estimate_routed_item({**base, "route_key": "non_tax_fee_revenue_average",
                                      "explicit_inputs": {"exemption_rate": invalid}})
        with self.assertRaises(ValueError):
            estimate_routed_item({**base, "route_key": "non_tax_fee_revenue_average", "actual_inputs": {}})

    def test_ai_selected_variable_inputs_without_formula_search(self) -> None:
        from backend.erce.service_industry_variable_registry import SERVICE_INDUSTRY_VARIABLES
        from unittest.mock import patch
        base = {"bill_no": "2216475", "cutoff_date": "2026-01-30", "start_year": 2027, "years": 5}
        with patch("backend.erce.engine.research_service_formula_inputs", side_effect=KeyError("no preset")):
            plan = estimate_routed_item({
                **base, "route_key": "research_plan",
                "explicit_inputs": {"recurrence_interval_years": 5},
                "selected_variable_inputs": {"plan_unit_cost": SERVICE_INDUSTRY_VARIABLES["plan_unit_cost"]},
            })
        committee = estimate_routed_item({
            **base, "route_key": "committee_components",
            "selected_variable_inputs": {"committee_components": SERVICE_INDUSTRY_VARIABLES["committee_components"]},
        })
        self.assertEqual(sum(plan.annual_amounts_thousand) + sum(committee.annual_amounts_thousand), 230000)
        self.assertEqual(plan.resolved_variables["plan_unit_cost"].source_class, "precedent_assumption")
        self.assertEqual(committee.resolved_variables["committee_components"].source_class, "precedent_assumption")
        for changes in ({"bill_no": "2214690"}, {"cutoff_date": "2025-12-16"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                estimate_routed_item({**base, **changes, "route_key": "committee_components",
                    "selected_variable_inputs": {"committee_components": SERVICE_INDUSTRY_VARIABLES["committee_components"]}})
        override = estimate_routed_item({
            **base, "route_key": "committee_components",
            "selected_variable_inputs": {"committee_components": SERVICE_INDUSTRY_VARIABLES["committee_components"]},
            "explicit_inputs": {"committee_components": {"value": [
                {"paid_members": 2, "annual_meetings": 1, "meeting_unit_price": 200000},
            ]}},
        })
        self.assertEqual(override.annual_amounts_thousand, (400,) * 5)

    def test_service_industry_gold_reproduction_separate_from_first_run(self) -> None:
        from backend.erce.meeting_allowance_rules import MEETING_ALLOWANCE_RULES
        rule = MEETING_ALLOWANCE_RULES[0]
        self.assertEqual(rule["value_kind"], "upper_limit")
        self.assertEqual(rule["base_limit_won"] + rule["additional_limit_won"], 300000)
        base = {"bill_no": "2216475", "cutoff_date": "2026-01-30", "start_year": 2026, "years": 5}
        plan = estimate_routed_item({**base, "route_key": "research_plan",
            "explicit_inputs": {"recurrence_interval_years": 5},
            "actual_inputs": {"plan_unit_cost": {"value": 130000000,
                "source_ref": "정답 재현 전용"}}})
        committee = estimate_routed_item({**base, "route_key": "committee_components",
            "actual_inputs": {"committee_components": {"value": [
                {"paid_members": 20, "annual_meetings": [2,4,4,4,4], "meeting_unit_price": 300000},
            ], "source_ref": "정답 표4 재현 전용"}}})
        self.assertEqual(committee.annual_amounts_thousand, (12000,24000,24000,24000,24000))
        self.assertEqual(sum(plan.annual_amounts_thousand) + sum(committee.annual_amounts_thousand), 238000)

    def test_all_existing_formulas_connected_and_tree_covers_routes(self) -> None:
        self.assertEqual({row.formula_key for row in ERCE_FORMULA_ROUTES.values()}, set(FORMULAS))
        leaves = formula_leaf_routes()
        self.assertEqual(set(leaves), set(ERCE_FORMULA_ROUTES))
        self.assertEqual(len(leaves), len(set(leaves)))

    def test_every_direct_route_dispatches_without_precedent_search(self) -> None:
        from unittest.mock import patch
        structured = {"headcount_by_grade": {"A": 2}, "salary_by_grade": {"A": 1000000},
                      "historical_annual_fee_revenues": [1000000, 2000000],
                      "other_channel_base_year": 2024, "other_channel_growth_rate": 0,
                      "committee_components": [{"paid_members": 2, "annual_meetings": 3,
                                                "meeting_unit_price": 100000}]}
        with patch("backend.erce.engine.select_committee_pack", side_effect=AssertionError("no search")), \
             patch("backend.erce.engine.research_service_formula_inputs", side_effect=AssertionError("no search")):
            for route, (key, _) in DIRECT_FORMULA_ROUTE_KEYS.items():
                values = {name: {"value": structured.get(name, 1), "source_ref": "synthetic connection test"}
                          for name in FORMULAS[key]["required"]}
                with self.subTest(route=route):
                    result = estimate_routed_item({"route_key": route, "years": 2, "start_year": 2027,
                                                  "explicit_inputs": values})
                    self.assertEqual(result.formula_key, key)
                    self.assertNotIn(None, result.annual_amounts_thousand)
                    with self.assertRaisesRegex(ValueError, "missing ERCE"):
                        estimate_routed_item({"route_key": route})

    def test_system_operation_tree_path_and_evidence_priority(self) -> None:
        path = ["물건비", "정보시스템", "운영", "연간총액기반"]
        self.assertEqual(route_for_path(path), "information_system_operation")
        result = estimate_routed_item({
            "route_path": path, "years": 3,
            "actual_inputs": {"annual_operating_amount": 298000000},
            "official_inputs": {"annual_operating_amount": 100000000, "growth_rate": .02},
        })
        self.assertEqual(result.annual_amounts_thousand, (298000, 303960, 310039))
        self.assertEqual(result.resolved_variables["annual_operating_amount"].source_class, "target_current_actual")
        for invalid_path in (["物건비"], ["물건비", "정보시스템"],
                             ["물건비", "정보시스템", "구축견적"]):
            with self.subTest(path=invalid_path), self.assertRaises((KeyError, ValueError)):
                estimate_routed_item({"route_path": invalid_path})
        with self.assertRaisesRegex(ValueError, "disagrees"):
            estimate_routed_item({"route_path": path, "route_key": "capital_area"})

    def test_position_difference_formula_handles_yearly_difference(self) -> None:
        result = estimate_routed_item({
            "route_path": ["인건비", "보수", "직급·직위변경차액"],
            "start_year": 2025,
            "years": 3,
            "explicit_inputs": {
                "headcount": {"value": 1, "source_ref": "법안에 명시된 겸임자 1명"},
                "annual_salary_difference": {
                    "value": [5_520_000, 5_652_480, 5_788_139.52],
                    "source_ref": "부총리와 장관의 연도별 보수 차액 예시",
                },
            },
        })
        self.assertEqual(result.formula_key, "PERSONNEL_POSITION_DIFFERENCE_V1")
        self.assertEqual(result.annual_amounts_thousand, (5520, 5652, 5788))

    def test_project_plan_reproduction_requires_target_plan(self) -> None:
        base = {
            "route_key": "information_system_project_plan", "bill_no": "2200093",
            "start_year": 2025, "budget_start_year": 2025, "years": 5,
            "actual_inputs": {"annual_project_budget": {
                "value": [5326000000, 5737000000, 4324000000, 3724000000, 0],
                "unit": "KRW/year", "source_ref": "2200093 정답 표2 재현 전용; ISP 원본 독립 검증 전",
            }},
        }
        result = estimate_routed_item(base)
        self.assertEqual(result.annual_amounts_thousand, (5326000, 5737000, 4324000, 3724000, 0))
        self.assertEqual(sum(result.annual_amounts_thousand), 19111000)
        self.assertFalse(result.resolved_variables["annual_project_budget"].is_assumption)
        for changes in ({"actual_inputs": {}}, {"start_year": 2026},
                        {"budget_start_year": 2024}, {"years": 4}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                estimate_routed_item({**base, **changes})
        for value in (100, [1, -1, 1, 1, 1], [1, float("nan"), 1, 1, 1]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                estimate_routed_item({**base, "actual_inputs": {"annual_project_budget": {
                    "value": value, "unit": "KRW/year", "source_ref": "test plan",
                }}})
        with self.assertRaises(ValueError):
            estimate_routed_item({**base, "actual_inputs": {"annual_project_budget": {
                "value": [1] * 5, "unit": "KRW/year", "source_ref": "",
            }}})

    def test_borderline_support_regression_and_periodic_phase(self) -> None:
        base = {"agency": "보건복지부", "policy_domain": "경계선지능인",
                "cutoff_date": "2024-10-22", "start_year": 2026, "years": 5}
        plan = estimate_routed_item({**base, "route_key": "research_plan",
                                    "explicit_inputs": {"recurrence_interval_years": 5}})
        survey = estimate_routed_item({
            **base, "route_key": "research_survey",
            "explicit_inputs": {"recurrence_interval_years": 3},
            "actual_inputs": {"first_occurrence_offset_years": {
                "value": 1, "unit": "year", "source_ref": "2024년 기존 조사, 다음 2027년; 정답 재현",
            }},
        })
        self.assertEqual(plan.annual_amounts_thousand, (70000, 0, 0, 0, 0))
        self.assertEqual(survey.annual_amounts_thousand, (0, 300000, 0, 0, 300000))
        diagnostic = estimate_routed_item({
            **base, "route_key": "diagnostic_test_subsidy",
            "actual_inputs": {
                "annual_recipients": {"value": [22035, 20360, 18659, 17250, 16067],
                                      "source_ref": "정답 표4 재현 전용"},
                "existing_annual_cost": {"value": 172000000,
                                         "source_ref": "기존 3개 교육청 사업; 정답 재현 전용"},
            },
        })
        self.assertEqual(diagnostic.annual_amounts_thousand,
                         (4235000, 3900000, 3559800, 3278000, 3041400))
        total = sum(plan.annual_amounts_thousand) + sum(survey.annual_amounts_thousand) + sum(diagnostic.annual_amounts_thousand)
        self.assertEqual(total, 18684200)
        for changes in ({"bill_no": "2203298"}, {"cutoff_date": "2024-08-28"},
                        {"policy_domain": "다른 검사"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                estimate_routed_item({**base, **changes, "route_key": "diagnostic_test_subsidy",
                                      "actual_inputs": {"annual_recipients": 100,
                                                        "existing_annual_cost": 0}})
        with self.assertRaisesRegex(ValueError, "annual_recipients"):
            estimate_routed_item({**base, "route_key": "diagnostic_test_subsidy"})

    def test_diagnostic_official_override_and_net_cost(self) -> None:
        base = {"route_key": "diagnostic_test_subsidy", "start_year": 2026, "years": 2,
                "explicit_inputs": {"annual_recipients": [100, 200]},
                "actual_inputs": {"existing_annual_cost": 1000000},
                "official_inputs": {"test_unit_cost": 250000}}
        result = estimate_routed_item(base)
        self.assertEqual(result.annual_amounts_thousand, (24000, 49000))
        self.assertEqual(result.resolved_variables["test_unit_cost"].source_class, "official_standard")
        with self.assertRaisesRegex(ValueError, "existing_annual_cost"):
            estimate_routed_item({**base, "actual_inputs": {}})
        with self.assertRaises(ValueError):
            estimate_routed_item({**base, "explicit_inputs": {"annual_recipients": [-1, 2]}})

    def test_notification_regression_and_target_volume_required(self) -> None:
        payload = {
            "route_key": "legal_notification", "agency": "대법원",
            "policy_domain": "친밀관계폭력", "cutoff_date": "2025-10-24",
            "start_year": 2027, "years": 5,
            # Gold-derived volume is regression-only, not a reusable assumption.
            "actual_inputs": {"annual_case_count": {
                "value": [21701, 25152, 29151, 33786, 39158],
                "unit": "case/year", "source_ref": "2212780 정답 표4 재현 전용",
            }},
        }
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand,
                         (242460, 286645, 338860, 400642, 473583))
        self.assertEqual(sum(result.annual_amounts_thousand), 1742190)
        self.assertEqual(result.resolved_variables["notice_unit_price"].source_class,
                         "precedent_assumption")
        for change in ({"actual_inputs": {}}, {"bill_no": "2212780"},
                       {"cutoff_date": "2025-09-08"}, {"start_year": 2028},
                       {"policy_domain": "선거"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                estimate_routed_item({**payload, **change})

    def test_notification_official_override_and_invalid_operands(self) -> None:
        payload = {
            "route_key": "legal_notification", "bill_no": "2212780",
            "start_year": 2027, "years": 2,
            "explicit_inputs": {"annual_case_count": [100, 200], "action_rate": .5,
                                "notices_per_case": 2},
            "official_inputs": {"notice_unit_price": {
                "value": 6000, "unit": "KRW/notification", "source_ref": "test official evidence",
            }},
        }
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand, (600, 1200))
        self.assertEqual(result.resolved_variables["notice_unit_price"].source_class,
                         "official_standard")
        for invalid in (-.1, 1.1, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                estimate_routed_item({**payload, "explicit_inputs": {
                    **payload["explicit_inputs"], "action_rate": invalid,
                }})
        with self.assertRaises(ValueError):
            estimate_routed_item({**payload, "explicit_inputs": {
                **payload["explicit_inputs"], "annual_case_count": [100],
            }})

    def test_evaluation_initial_study_and_central_local_panel_cost(self) -> None:
        payload = {
            "route_key": "evaluation_panel_with_initial_study",
            "agency": "중앙선거관리위원회",
            "policy_domain": "선거여론조사",
            "cutoff_date": "2026-04-09",
            "start_year": 2028,
            "years": 5,
        }
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand, (909_000, 855_000, 855_000, 855_000, 855_000))
        self.assertEqual(sum(result.annual_amounts_thousand), 4_329_000)
        actual = estimate_routed_item({
            **payload, "actual_inputs": {"initial_study_cost": 60_000_000},
        })
        self.assertEqual(actual.annual_amounts_thousand[0], 915_000)
        for changes in ({"cutoff_date": "2026-02-10"}, {"bill_no": "2216710"},
                        {"policy_domain": "도서관"}, {"start_year": 2029}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                estimate_routed_item({**payload, **changes})

    def test_circular_economy_committee_uses_its_own_scope_and_rate(self) -> None:
        payload = {
            "route_key": "committee_operation",
            "subtype": "regulatory_special_zone",
            "agency": "기후에너지환경부",
            "policy_domain": "순환경제",
            "cutoff_date": "2026-05-13",
            "start_year": 2027,
            "years": 5,
            "explicit_inputs": {"committee_instances": 1},
        }
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand, (9600,) * 5)
        self.assertEqual(result.resolved_variables["meeting_unit_price"].value, 200_000)
        self.assertEqual(result.resolved_variables["committee_instances"].source_class, "target_explicit")
        for changes in (
            {"cutoff_date": "2026-04-24"},
            {"bill_no": "2218618"},
            {"policy_domain": "원자력"},
        ):
            with self.subTest(changes=changes), self.assertRaises(KeyError):
                estimate_routed_item({**payload, **changes})

    def test_library_survey_recurrence_and_explicit_frequency_override(self) -> None:
        payload = {
            "route_key": "research_survey",
            "agency": "문화체육관광부",
            "policy_domain": "도서관",
            "cutoff_date": "2026-04-03",
            "years": 5,
            "start_year": 2027,
        }
        result = estimate_routed_item(payload)
        self.assertEqual(result.formula_key, "PERIODIC_RESEARCH_SURVEY_V1")
        self.assertEqual(result.annual_amounts_thousand, (210_000, 0, 0, 210_000, 0))
        annual = estimate_routed_item({
            **payload,
            "explicit_inputs": {"recurrence_interval_years": {
                "value": 1, "unit": "year", "source_ref": "대상 조문: 매년 실시",
            }},
        })
        self.assertEqual(annual.annual_amounts_thousand, (210_000,) * 5)
        self.assertFalse(annual.resolved_variables["recurrence_interval_years"].is_assumption)

    def test_library_benchmark_rejects_future_self_and_unrelated_domain(self) -> None:
        common = {
            "route_key": "research_survey",
            "agency": "문화체육관광부",
            "policy_domain": "도서관",
            "cutoff_date": "2026-04-03",
            "start_year": 2027,
        }
        for change in (
            {"cutoff_date": "2026-03-11"},
            {"bill_no": "2217373"},
            {"policy_domain": "무용"},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "missing ERCE"):
                estimate_routed_item({**common, **change})

    def test_ai_route_determines_one_fixed_committee_formula(self) -> None:
        route = formula_for_route("committee_operation")
        self.assertEqual(route.formula_key, "COMMITTEE_MEETING_ALLOWANCE_V1")

    def test_cutoff_selects_only_then_available_assumption_pack(self) -> None:
        old, _ = select_committee_pack(
            agency="기획재정부",
            subtype="main_committee",
            as_of_date="2024-11-14",
        )
        new, _ = select_committee_pack(
            agency="기획재정부",
            subtype="main_committee",
            as_of_date="2025-02-10",
        )
        self.assertEqual(old.source_bill_no, "2124586")
        self.assertEqual(new.source_bill_no, "2205576")

    def test_main_and_advisory_items_use_same_formula_but_different_evidence(self) -> None:
        common = {
            "route_key": "committee_operation",
            "agency": "기획재정부",
            "cutoff_date": "2025-02-10",
            "years": 5,
            "start_year": 2025,
            "first_year_fraction": 0.5,
        }
        main = estimate_routed_item({**common, "subtype": "main_committee"})
        advisory = estimate_routed_item({**common, "subtype": "advisory_body"})
        self.assertEqual(main.formula_key, advisory.formula_key)
        self.assertEqual(main.annual_amounts_thousand, (37_125, 74_250, 75_735, 77_250, 78_795))
        self.assertEqual(advisory.annual_amounts_thousand, (5_250, 10_500, 10_710, 10_924, 11_143))
        self.assertNotEqual(main.evidence_key, advisory.evidence_key)

    def test_explicit_and_actual_values_override_precedent_assumptions(self) -> None:
        result = estimate_routed_item({
            "route_key": "committee_operation",
            "subtype": "main_committee",
            "agency": "기획재정부",
            "cutoff_date": "2025-02-10",
            "years": 1,
            "start_year": 2025,
            "explicit_inputs": {
                "paid_members": {
                    "value": 30,
                    "unit": "person/committee",
                    "source_ref": "대상 법안에 30명으로 명시",
                }
            },
            "actual_inputs": {
                "annual_meetings": {
                    "value": 12,
                    "unit": "meeting/year",
                    "source_ref": "대상 기관 최근 개최실적",
                }
            },
        })
        self.assertEqual(result.annual_amounts_thousand, (90_000,))
        self.assertEqual(result.resolved_variables["paid_members"].source_class, "target_explicit")
        self.assertEqual(
            result.resolved_variables["annual_meetings"].source_class,
            "target_current_actual",
        )
        self.assertEqual(
            result.resolved_variables["meeting_unit_price"].source_class,
            "official_standard",
        )


if __name__ == "__main__":
    unittest.main()
