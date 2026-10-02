from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.information_system_evidence import sports_information_system_rows
from backend.erce.variable_evidence_store import save_variable_rows


class InformationSystemStagedBuildTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "evidence.sqlite3"
        save_variable_rows(sports_information_system_rows(), self.db_path)
        self.common = dict(
            bill_no="2211999", cutoff_date="2025-08-08", start_year=2027,
            years=5, evidence_mode="development_review",
            variable_db_path=str(self.db_path), agency="문화체육관광부",
            policy_domain="스포츠지능정보화")

    def test_staged_build_uses_only_the_specified_years(self):
        result = estimate_routed_item(dict(
            route_path=["물건비", "정보시스템", "구축견적", "기간지정연간사업비"],
            start_year=2027, years=5, explicit_inputs={
                "annual_phase_cost": 1_000_000_000,
                "phase_start_offset_years": 3, "phase_duration_years": 2}))
        self.assertEqual(result.formula_key, "INFORMATION_SYSTEM_STAGED_BUILD_V1")
        self.assertEqual(result.annual_amounts_thousand, (0, 0, 0, 1_000_000, 1_000_000))

    def test_post_answer_case_reconstructs_two_distinct_components(self):
        plan = estimate_routed_item({**self.common,
            "route_path": ["물건비", "연구용역", "기본계획"],
            "selected_evidence_keys": ["2211999:first_plan_unit_cost:2027",
                                       "2211999:repeat_plan_unit_cost:2030"],
            "explicit_inputs": {"recurrence_interval_years": 3}})
        build = estimate_routed_item({**self.common,
            "route_path": ["물건비", "정보시스템", "구축견적", "기간지정연간사업비"],
            "system_kind": "disaster_recovery",
            "selected_evidence_keys": [
                "2211999:disaster_recovery_annual_phase_cost:2030-2031",
                "2211999:disaster_recovery_start_offset:2027-2031",
                "2211999:disaster_recovery_duration:2027-2031"]})
        self.assertEqual(plan.annual_amounts_thousand, (220_000, 0, 0, 110_000, 0))
        self.assertEqual(build.annual_amounts_thousand, (0, 0, 0, 1_000_000, 1_000_000))
        self.assertEqual(sum(plan.annual_amounts_thousand) + sum(build.annual_amounts_thousand),
                         2_330_000)

    def test_target_answer_cannot_be_used_as_holdout(self):
        with self.assertRaisesRegex(ValueError, "target answer"):
            estimate_routed_item({**self.common, "evidence_mode": "holdout",
                "route_path": ["물건비", "연구용역", "기본계획"],
                "selected_evidence_keys": ["2211999:first_plan_unit_cost:2027"],
                "explicit_inputs": {"recurrence_interval_years": 3}})

    def test_cross_bill_reuse_requires_date_kind_and_reason(self):
        key = "2211999:disaster_recovery_annual_phase_cost:2030-2031"
        payload = {**self.common, "bill_no": "NEW_DR", "evidence_mode": "holdout",
            "route_path": ["물건비", "정보시스템", "구축견적", "기간지정연간사업비"],
            "system_kind": "disaster_recovery", "selected_evidence_keys": [key],
            "explicit_inputs": {"phase_start_offset_years": 1,
                                "phase_duration_years": 2}}
        with self.assertRaisesRegex(ValueError, "future"):
            estimate_routed_item({**payload, "cutoff_date": "2025-08-05"})
        with self.assertRaisesRegex(ValueError, "applicability reason"):
            estimate_routed_item(payload)
        with self.assertRaisesRegex(ValueError, "system_kind mismatch"):
            estimate_routed_item({**payload, "system_kind": "general_it",
                "evidence_selection_reasons": {key: "비교 범위 검토"}})
        valid = estimate_routed_item({**payload,
            "evidence_selection_reasons": {key:
                "같은 재해복구 체계이며 대상 데이터·복구 범위·사업 규모를 비교한 가정"}})
        self.assertEqual(valid.annual_amounts_thousand,
                         (0, 1_000_000, 1_000_000, 0, 0))
        with self.assertRaisesRegex(ValueError, "different target"):
            estimate_routed_item({**payload,
                "selected_evidence_keys": ["2211999:disaster_recovery_start_offset:2027-2031"],
                "evidence_selection_reasons": {
                    "2211999:disaster_recovery_start_offset:2027-2031": "동일 일정이라고 가정"}})

    def test_invalid_schedule_is_rejected(self):
        base = dict(route_key="information_system_staged_build", years=5,
                    explicit_inputs={"annual_phase_cost": 1_000_000_000,
                                     "phase_start_offset_years": 1,
                                     "phase_duration_years": 2})
        for changes in ({"phase_start_offset_years": -1},
                        {"phase_start_offset_years": 1.5},
                        {"phase_duration_years": 0},
                        {"annual_phase_cost": -1}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "invalid ERCE formula variables"):
                estimate_routed_item({**base, "explicit_inputs": {
                    **base["explicit_inputs"], **changes}})

    def test_invalid_repeat_plan_unit_cost_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid ERCE research variables"):
            estimate_routed_item({
                **self.common,
                "route_path": ["물건비", "연구용역", "기본계획"],
                "explicit_inputs": {
                    "plan_unit_cost": 220_000_000,
                    "recurrence_interval_years": 3,
                    "repeat_plan_unit_cost": -1,
                },
            })


if __name__ == "__main__":
    unittest.main()
