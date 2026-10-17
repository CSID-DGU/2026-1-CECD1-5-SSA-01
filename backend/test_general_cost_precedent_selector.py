from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.general_cost_precedent_selector import (
    GeneralCostEvidenceStore,
    infer_mechanism,
    infer_priced_scopes,
    select_formula_key,
    select_precedent,
    target_from_dict,
)
from backend.scripts.build_general_cost_sidecar import parse_reply_date


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _profile(
    key: str,
    bill_no: str,
    item_name: str,
    *,
    available_date: str = "2025-11-07",
) -> dict:
    return {
        "profile_key": key,
        "bill_no": bill_no,
        "bill_name": f"{item_name} 관련 법률안",
        "item_name": item_name,
        "propose_date": "2025-08-07",
        "available_date": available_date,
        "committee": "농림축산식품해양수산위원회",
        "cost_nature": "goods_services",
        "component": "event_meeting",
        "review_status": "candidate",
    }


def _evidence(key: str, amount: int, text: str) -> dict:
    return {
        "profile_key": key,
        "canonical_key": "annual_goods_amount",
        "normalized_value": amount,
        "source_text": text,
    }


def _amounts(key: str, amount_won: int) -> list[dict]:
    return [
        {
            "profile_key": key,
            "year_label": str(2027 + offset),
            "year_offset": offset,
            "amount_thousand": amount_won // 1_000,
            "is_total": False,
        }
        for offset in range(5)
    ]


def _target() -> dict:
    return {
        "bill_no": "TARGET",
        "bill_name": "양봉산업의 육성 및 지원에 관한 법률 일부개정법률안",
        "propose_date": "2026-07-14",
        "cutoff_date": "2026-07-14",
        "committee": "농림축산식품해양수산위원회",
        "cost_nature": "goods_services",
        "component": "event_meeting",
        "item_name": "양봉인의 날 기념행사",
        "mechanism": "commemorative_event",
        "estimated_scopes": ["event"],
        "non_estimable_scopes": ["education", "publicity"],
        "implementing_agencies": ["산림청"],
        "policy_domains": ["양봉", "산림", "임업"],
        "years": 5,
        "start_year": 2027,
    }


class GeneralCostPrecedentSelectorTest(unittest.TestCase):
    def test_information_system_subtypes_are_separated(self) -> None:
        self.assertEqual(
            infer_mechanism("통합빈집정보시스템 운영비 지원"),
            "information_system_operation",
        )
        self.assertEqual(
            infer_mechanism("지방세 체납정보 통합관리시스템 구축"),
            "information_system_build",
        )
        self.assertEqual(
            infer_mechanism("지하안전정보시스템 저장용량 확대 및 기능개선"),
            "information_system_upgrade",
        )
        self.assertEqual(
            infer_mechanism("아동건강정보시스템 구축 및 운영"),
            "information_system_mixed",
        )
        self.assertEqual(
            infer_mechanism("정보시스템 운영 인력 3명"),
            "information_system_operation_staff",
        )

    def test_research_plan_and_survey_are_separate_routes(self) -> None:
        self.assertEqual(
            infer_mechanism("교원의 교육활동 지원계획 수립"),
            "research_plan",
        )
        self.assertEqual(
            infer_mechanism("교원의 교육활동 실태조사 실시"),
            "research_survey",
        )
        plan = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "item_name": "교원의 교육활동 지원계획 수립",
            "mechanism": "research_survey",
            "estimated_scopes": [],
        })
        self.assertEqual(plan.mechanism, "research_plan")
        self.assertEqual(
            select_formula_key(plan),
            ("PERIODIC_RESEARCH_PLAN_V1", "fixed_mechanism_route"),
        )

    def test_available_official_research_benchmark_bypasses_weak_precedents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = target_from_dict({
                **_target(),
                "bill_no": "FUTURE",
                "propose_date": "2024-08-01",
                "cutoff_date": "2024-08-01",
                "committee": "교육위원회",
                "cost_nature": "goods_services",
                "component": "research_survey",
                "item_name": "교원 실태조사 실시",
                "mechanism": "research_survey",
                "estimated_scopes": [],
                "implementing_agencies": ["교육부"],
                "policy_domains": ["교육"],
                "start_year": 2025,
            })
            result = select_precedent(
                target,
                store=GeneralCostEvidenceStore(Path(temp)),
            )
        self.assertEqual(result.decision, "official_benchmark")
        self.assertEqual(result.formula_key, "ANNUAL_RESEARCH_SURVEY_V1")
        self.assertEqual(
            result.resolver_request["inputs"]["survey_unit_cost"]["value"],
            22_000_000,
        )

    def test_legacy_information_system_target_is_refined(self) -> None:
        target = target_from_dict({
            **_target(),
            "item_name": "통합빈집정보시스템 운영비 지원",
            "component": "information_system",
            "mechanism": "information_system",
        })
        self.assertEqual(target.mechanism, "information_system_operation")

    def test_reply_date_parser(self) -> None:
        self.assertEqual(parse_reply_date("회답일\n2025.11.7."), "2025-11-07")
        self.assertEqual(parse_reply_date("회답일 2026년 3월 25일"), "2026-03-25")
        self.assertIsNone(parse_reply_date("회답일 미상"))

    def test_same_agency_and_exact_scope_win(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles = [
                _profile("right", "P-RIGHT", "목재의 날 기념행사"),
                _profile("wrong-scope", "P-WRONG", "차의 날 기념행사 및 홍보"),
                _profile("no-date", "P-NODATE", "임업인의 날 기념행사", available_date=""),
            ]
            evidence = [
                _evidence("right", 100_000_000, "산림청 임업인의 날 행사비 각 1억원"),
                _evidence("wrong-scope", 185_000_000, "농림축산식품부 김치의 날 예산"),
                _evidence("no-date", 90_000_000, "산림청 임업인의 날 행사"),
            ]
            observations = (
                _amounts("right", 100_000_000)
                + _amounts("wrong-scope", 185_000_000)
                + _amounts("no-date", 90_000_000)
            )
            _write_jsonl(root / "item_profiles.jsonl", profiles)
            _write_jsonl(root / "variable_evidence.jsonl", evidence)
            _write_jsonl(root / "amount_observations.jsonl", observations)

            result = select_precedent(
                target_from_dict(_target()),
                store=GeneralCostEvidenceStore(root),
            )

            self.assertEqual(result.decision, "exact_precedent_candidate")
            self.assertIsNotNone(result.selected)
            self.assertEqual(result.selected.bill_no, "P-RIGHT")
            self.assertEqual(result.formula_key, "COMMON_QUANTITY_UNIT_V1")
            self.assertEqual(result.resolver_request["inputs"]["quantity"]["value"], 1)
            self.assertEqual(
                result.resolver_request["inputs"]["unit_cost"]["value"],
                100_000_000,
            )
            wrong = next(row for row in result.candidates if row.bill_no == "P-WRONG")
            self.assertIn("PRICED_SCOPE_EXTRA:publicity", wrong.blockers)
            no_date = next(row for row in result.candidates if row.bill_no == "P-NODATE")
            self.assertIn("OFFICIAL_AVAILABLE_DATE_MISSING", no_date.blockers)

    def test_all_seven_cost_natures_have_a_formula_route(self) -> None:
        cases = (
            ("personnel", "salary", "salary", "PERSONNEL_AVERAGE_V1"),
            ("goods_services", "event_meeting", "commemorative_event", "COMMON_QUANTITY_UNIT_V1"),
            ("transfers", "subsidy", "subsidy", "TRANSFER_RECIPIENT_V1"),
            ("capital", "equipment_asset", "equipment_asset", "CAPITAL_ASSET_V1"),
            ("tax_expenditure", "rate_reduction", "other_tax_expenditure", "TAX_RATE_CHANGE_V1"),
            ("non_tax_revenue_loss", "fee_reduction", "fee_reduction", "NON_TAX_FEE_CHANGE_V1"),
            ("equity_contribution", "equity_investment", "equity_investment", "EQUITY_PROJECT_SHARE_V1"),
        )
        for nature, component, mechanism, expected in cases:
            with self.subTest(nature=nature):
                target = target_from_dict({
                    **_target(),
                    "cost_nature": nature,
                    "component": component,
                    "mechanism": mechanism,
                    "estimated_scopes": [],
                })
                self.assertEqual(select_formula_key(target)[0], expected)

    def test_committee_route_has_one_fixed_formula(self) -> None:
        target = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "mechanism": "committee_operation",
            "estimated_scopes": ["meeting_allowance"],
        })
        self.assertEqual(
            select_formula_key(target),
            ("COMMITTEE_MEETING_ALLOWANCE_V1", "fixed_mechanism_route"),
        )

    def test_information_system_operation_has_one_fixed_formula(self) -> None:
        target = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "component": "information_system",
            "item_name": "통합빈집정보시스템 운영비 지원",
            "mechanism": "information_system",
            "estimated_scopes": [],
        })
        self.assertEqual(
            select_formula_key(target),
            ("INFORMATION_SYSTEM_OPERATION_V1", "fixed_mechanism_route"),
        )

    def test_information_system_operation_staff_has_one_fixed_formula(self) -> None:
        target = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "component": "information_system",
            "item_name": "정보시스템 운영 인력 3명",
            "mechanism": "information_system",
            "estimated_scopes": [],
        })
        self.assertEqual(
            select_formula_key(target),
            ("INFORMATION_SYSTEM_OPERATION_STAFF_V1", "fixed_mechanism_route"),
        )

    def test_operation_route_refines_to_staff_when_staff_evidence_is_found(self) -> None:
        target = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "component": "information_system",
            "item_name": "통합빈집정보시스템 운영비 지원",
            "mechanism": "information_system",
            "estimated_scopes": [],
            "formula_inputs": {
                "operation_headcount": {
                    "value": 3,
                    "unit": "person",
                    "source": "current_operation_plan",
                },
                "annual_labor_cost_per_person": {
                    "value": 120_000_000,
                    "unit": "KRW/person/year",
                    "source": "KOSA_official_average_wage",
                },
            },
        })
        self.assertEqual(
            select_formula_key(target),
            ("INFORMATION_SYSTEM_OPERATION_STAFF_V1", "available_operand_subroute"),
        )

    def test_existing_actual_operation_cost_beats_staff_unit_estimate(self) -> None:
        target = target_from_dict({
            **_target(),
            "cost_nature": "goods_services",
            "component": "information_system",
            "item_name": "통합빈집정보시스템 운영비 지원",
            "mechanism": "information_system",
            "estimated_scopes": [],
            "formula_inputs": {
                "annual_operating_amount": 298_000_000,
                "operation_headcount": 3,
                "annual_labor_cost_per_person": 120_000_000,
            },
        })
        self.assertEqual(
            select_formula_key(target),
            ("INFORMATION_SYSTEM_OPERATION_V1", "fixed_mechanism_route"),
        )

    def test_corporation_name_is_not_a_construction_scope(self) -> None:
        self.assertEqual(
            infer_priced_scopes("한미전략투자공사 자본금 출자", "equity_investment"),
            (),
        )

    def test_bill_title_cannot_reclassify_unrelated_item_as_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile("plan", "P-PLAN", "기본계획의 수립")
            profile["bill_name"] = "기념사업 지원에 관한 법률안"
            _write_jsonl(root / "item_profiles.jsonl", [profile])
            _write_jsonl(
                root / "variable_evidence.jsonl",
                [_evidence("plan", 100_000_000, "산림청 산림 임업 기본계획")],
            )
            _write_jsonl(
                root / "amount_observations.jsonl",
                _amounts("plan", 100_000_000),
            )

            result = select_precedent(
                target_from_dict(_target()),
                store=GeneralCostEvidenceStore(root),
            )

            self.assertEqual(result.decision, "abstain")
            self.assertIn("COST_MECHANISM_MISMATCH", result.candidates[0].blockers)

    def test_close_qualified_candidates_with_amount_conflict_require_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles = [
                _profile("first", "P-1", "목재의 날 기념행사"),
                _profile("second", "P-2", "임업인의 날 기념행사"),
            ]
            evidence = [
                _evidence("first", 100_000_000, "산림청 산림 임업 행사"),
                _evidence("second", 150_000_000, "산림청 산림 임업 행사"),
            ]
            _write_jsonl(root / "item_profiles.jsonl", profiles)
            _write_jsonl(root / "variable_evidence.jsonl", evidence)
            _write_jsonl(
                root / "amount_observations.jsonl",
                _amounts("first", 100_000_000) + _amounts("second", 150_000_000),
            )

            result = select_precedent(
                target_from_dict(_target()),
                store=GeneralCostEvidenceStore(root),
            )

            self.assertEqual(result.decision, "needs_review")
            self.assertIsNone(result.resolver_request)


if __name__ == "__main__":
    unittest.main()
