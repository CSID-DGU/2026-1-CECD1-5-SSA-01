"""Net-staffing candidate methods never copy another bill's final headcount."""
from __future__ import annotations

import unittest

from backend.erce.net_staffing import (
    court_upgrade_precedent_inputs, net_staffing_scenarios,
)
from backend.erce.web_bridge import calculate_erce_web_item


def fact(value: int, unit: str = "person", source: str = "검토된 입력") -> dict:
    return {"value": value, "unit": unit, "source_ref": source}


class NetStaffingTests(unittest.TestCase):
    def test_suggests_methods_without_inventing_a_count(self) -> None:
        rows = net_staffing_scenarios()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["netStaff"] is None for row in rows))
        self.assertIn("existing_staff_total", rows[0]["missingInputs"])

    def test_confirmed_plan_subtracts_existing_and_transfers(self) -> None:
        rows = net_staffing_scenarios({
            "planned_staff_total": fact(200),
            "existing_staff_total": fact(150),
            "incoming_staff_total": fact(20),
        }, cutoff_date="2025-11-06", target_bill_no="2213969")
        self.assertEqual(rows[0]["grossStaff"], 200)
        self.assertEqual(rows[0]["netStaff"], 30)
        self.assertEqual(rows[0]["status"], "ready_for_grade_breakdown")
        self.assertIn("직급별", rows[0]["nextStep"])

    def test_grade_rows_produce_a_salary_ready_candidate(self) -> None:
        rows = net_staffing_scenarios({
            "planned_staff_by_grade": {"value": {"5급": 4, "6급": 8},
                                       "unit": "person/grade", "source_ref": "계획 정원표"},
            "existing_staff_by_grade": {"value": {"5급": 2, "6급": 5},
                                        "unit": "person/grade", "source_ref": "기존 정원표"},
            "incoming_staff_by_grade": {"value": {"5급": 1, "6급": 1},
                                        "unit": "person/grade", "source_ref": "전입 계획"},
        }, cutoff_date="2025-11-06")
        self.assertEqual(rows[3]["netStaffByGrade"], {"5급": 1, "6급": 2})
        self.assertEqual(rows[3]["netStaff"], 3)
        self.assertEqual(rows[3]["status"], "ready_for_salary_calculation")
        calculation = calculate_erce_web_item({
            "route_key": "personnel_grade", "years": 1,
            "explicit_inputs": {
                "headcount_by_grade": {
                    "value": rows[3]["netStaffByGrade"], "unit": "person/grade",
                    "source_ref": "검토된 직급별 정원 산정",
                },
                "salary_by_grade": {
                    "value": {"5급": 100_000_000, "6급": 80_000_000},
                    "unit": "KRW/person/year", "source_ref": "검토된 직급별 보수 단가",
                },
            },
        })
        self.assertEqual(calculation["annualAmountsThousand"], [260_000])

    def test_earlier_court_precedent_supplies_partial_candidates_only(self) -> None:
        prior = court_upgrade_precedent_inputs(
            cutoff_date="2025-11-06", parent_court="수원지방법원")
        rows = net_staffing_scenarios({
            **prior,
            "target_population": {
                **fact(1_400_000, source="2213969 의안원문 2쪽, 약 140만 명"),
                "source_bill_no": "2213969", "source_kind": "bill_text",
            },
        }, cutoff_date="2025-11-06", target_bill_no="2213969")
        self.assertEqual(rows[1]["grossStaff"], 216)
        self.assertEqual(rows[2]["grossStaff"], 301)
        self.assertIsNone(rows[1]["netStaff"])
        self.assertEqual(rows[1]["missingInputs"], ["existing_staff_total", "incoming_staff_total"])
        self.assertEqual(court_upgrade_precedent_inputs(cutoff_date="2025-09-11"), {})

    def test_target_answer_and_future_precedent_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "정답 추계서"):
            net_staffing_scenarios({"planned_staff_total": {
                **fact(205), "source_bill_no": "2213969",
                "source_kind": "cost_estimate_answer", "available_at": "2025-11-12",
            }}, cutoff_date="2025-11-13", target_bill_no="2213969")
        with self.assertRaisesRegex(ValueError, "기준일 이후"):
            net_staffing_scenarios({"planned_staff_total": {
                **fact(205), "source_bill_no": "2219999",
                "available_at": "2025-11-12",
            }}, cutoff_date="2025-11-06", target_bill_no="2213969")

    def test_bridge_returns_staffing_scenarios_without_using_them_as_answer(self) -> None:
        output = calculate_erce_web_item({
            "route_key": "personnel_grade", "bill_no": "2213969",
            "cutoff_date": "2025-11-06", "staffing_context": {
                "court_upgrade": True, "parent_court": "수원지방법원",
            },
            "staffing_inputs": {"target_population": fact(1_400_000, source="의안원문 2쪽, 약 140만 명")},
        })
        self.assertEqual(output["status"], "needs_input")
        self.assertEqual(output["staffingScenarios"][1]["grossStaff"], 216)
        self.assertIsNone(output["staffingScenarios"][1]["netStaff"])
        self.assertIn("headcount_by_grade", output["missingVariables"])


if __name__ == "__main__":
    unittest.main()
