from __future__ import annotations

import unittest

from backend.sw_labor_rate_registry import (
    annual_labor_cost_input,
    get_sw_labor_rate,
    resolve_role_key,
)


class SWLaborRateRegistryTest(unittest.TestCase):
    def test_2025_information_system_operator_rate(self) -> None:
        table, rate = get_sw_labor_rate(
            "정보시스템운용자",
            application_year=2025,
            as_of_date="2026-01-19",
        )
        self.assertEqual(table.published_at, "2024-12-03")
        self.assertEqual(rate.monthly_won, 10_154_626)
        self.assertEqual(rate.daily_won, 492_943)

    def test_2026_rate_is_versioned_separately(self) -> None:
        _, rate = get_sw_labor_rate(
            "information_system_operator",
            application_year=2026,
            as_of_date="2026-01-19",
        )
        self.assertEqual(rate.monthly_won, 10_649_117)

    def test_future_table_is_blocked_by_as_of_date(self) -> None:
        with self.assertRaises(ValueError):
            get_sw_labor_rate(
                "정보시스템운용자",
                application_year=2026,
                as_of_date="2025-11-01",
            )

    def test_obsolete_grade_does_not_silently_map_to_a_role(self) -> None:
        with self.assertRaisesRegex(ValueError, "현행 KOSA 직무명이 아니므로"):
            resolve_role_key("중급기술자")

    def test_annual_operand_keeps_source_trace(self) -> None:
        result = annual_labor_cost_input(
            "정보시스템운용자",
            application_year=2025,
            as_of_date="2026-01-19",
        )["annual_labor_cost_per_person"]
        self.assertEqual(result["value"], 121_855_512)
        self.assertIn("월 10,154,626원 × 12개월", result["source_ref"])
        self.assertEqual(
            result["evidence_keys"],
            ["kosa_sw_wage:2025:information_system_operator:monthly"],
        )


if __name__ == "__main__":
    unittest.main()
