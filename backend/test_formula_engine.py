from __future__ import annotations

import unittest

from backend.assembly_formula_engine import (
    apply_tag_formula_evidence,
    build_generalized_estimate,
    classify_estimation_status,
)
from backend.assembly_analogy_engine import build_analogical_committee_estimate
from backend.assembly_case_policy import apply_validated_case_policy
from backend.calculator import compute_year_estimates


class AssemblyFormulaEngineTest(unittest.TestCase):
    def test_special_committee_uses_analogous_official_case(self) -> None:
        articles = [{
            "no": "제45조의2(헌법특별위원회)",
            "text": "헌법개정 방향을 심사하기 위하여 헌법특별위원회를 두고 위원 수는 30명으로 한다.",
            "cost_trigger": True,
        }]
        estimate = build_analogical_committee_estimate(
            text="국회법 일부를 다음과 같이 개정한다.",
            articles=articles,
        )
        self.assertIsNotNone(estimate)
        self.assertNotEqual(estimate["analogy_selection"]["bill_no"], "2126636")
        self.assertTrue(estimate["analogy_selection"]["requires_review"])
        calculated, issues = compute_year_estimates(estimate, allow_estimated=False)
        self.assertFalse(issues)
        self.assertEqual(len(calculated), 5)
        self.assertGreater(calculated[0]["amount_thousand"], 0)

    def test_general_committee_does_not_use_legislative_special_case(self) -> None:
        articles = [{
            "no": "제10조(정책심의위원회)",
            "text": "장관 소속으로 정책심의위원회를 둔다.",
            "cost_trigger": True,
        }]
        estimate = build_analogical_committee_estimate(
            text="정책지원법을 제정한다.",
            articles=articles,
        )
        self.assertIsNone(estimate)

    def test_existing_program_notice_is_not_promoted_to_large_cost(self) -> None:
        articles = [{
            "no": "제58조",
            "text": "정부와 지방자치단체는 자립지원사업에 관하여 적극적으로 안내하여야 한다.",
            "cost_trigger": True,
            "trigger_type": "의무부과",
            "cost_candidate_strength": "medium",
            "estimate_feasibility": "needs_assumptions",
        }]
        result = apply_validated_case_policy(articles)
        self.assertEqual(result[0]["cost_candidate_strength"], "weak")
        self.assertEqual(result[0]["estimate_feasibility"], "minor_or_absorbable")

    def test_target_definition_change_without_payment_is_weak(self) -> None:
        articles = [{
            "no": "제38조",
            "text": "적용 대상 시설에 장애인거주시설을 추가한다.",
            "cost_trigger": True,
            "trigger_type": "대상확대",
            "cost_candidate_strength": "medium",
        }]
        result = apply_validated_case_policy(articles)
        self.assertEqual(result[0]["cost_candidate_strength"], "weak")

    def test_research_service_uses_compatible_tag_amount(self) -> None:
        articles = [{
            "no": "제10조의4(발생 및 사용 실태조사)",
            "text": "장관은 포장폐기물 발생 및 사용 실태를 연 1회 조사하여야 한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "의무부과",
            "rule_cost_trigger": {"rule": "survey_or_plan_service"},
        }]
        estimate = build_generalized_estimate(articles)
        self.assertIsNotNone(estimate)
        patterns = [{
            "bill_no": "2200001",
            "bill_name": "유사 실태조사 법률안",
            "items": [{
                "category": "위탁비",
                "name": "폐기물 발생 실태조사 연구용역",
                "variables": [],
                "amounts": [
                    {"amount_thousand": 190_000, "formula": "용역 단가 × 연 1회", "is_total": False},
                    {"amount_thousand": 950_000, "formula": "연간 비용 × 5년", "is_total": True},
                ],
            }],
        }]
        self.assertEqual(apply_tag_formula_evidence(estimate, patterns), 1)
        calculated, issues = compute_year_estimates(
            estimate,
            tag_patterns=patterns,
            allow_estimated=False,
        )
        self.assertFalse(issues)
        self.assertEqual([row["amount_thousand"] for row in calculated], [190_000] * 5)
        self.assertEqual(classify_estimation_status(estimate)["code"], "computed_with_estimates")

    def test_research_service_rejects_different_subtype_amount(self) -> None:
        articles = [{
            "no": "제10조의4(발생 및 사용 실태조사)",
            "text": "장관은 포장폐기물 발생 및 사용 실태를 연 1회 조사하여야 한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "의무부과",
            "rule_cost_trigger": {"rule": "survey_or_plan_service"},
        }]
        estimate = build_generalized_estimate(articles)
        patterns = [{
            "bill_no": "2200002",
            "bill_name": "폐기물 기본계획 법률안",
            "items": [{
                "category": "위탁비",
                "name": "폐기물처리시설 기본계획 수립 연구용역",
                "variables": [],
                "amounts": [
                    {"amount_thousand": 305_000, "formula": "유사 연구용역 비용", "is_total": False},
                ],
            }],
        }]
        self.assertEqual(apply_tag_formula_evidence(estimate, patterns), 0)

    def test_transfer_payment_requires_external_data_not_technical_failure(self) -> None:
        articles = [{
            "no": "제4조(급여의 지급)",
            "text": "국가는 2세 미만 아동에게 급여를 매월 추가로 지급하여야 한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "직접지원",
            "rule_cost_trigger": {"rule": "payment_or_subsidy"},
        }]
        estimate = build_generalized_estimate(articles)
        status = classify_estimation_status(estimate)
        self.assertEqual(status["code"], "needs_external_data")
        self.assertNotEqual(status["code"], "technically_infeasible")
        self.assertIn("지원 대상자 수", status["missing"]["external_data"]["급여의 지급 지원 소요"])

    def test_institution_is_split_into_composite_costs(self) -> None:
        articles = [
            {
                "no": "제1조(목적)",
                "text": "국립전문대학원을 설립하여 교육과 연구를 수행한다.",
                "cost_trigger": True,
                "cost_candidate_strength": "medium",
                "trigger_type": "조직설치",
            },
            {
                "no": "제20조(국가의 재정지원)",
                "text": "국가는 설립에 드는 비용을 지원하여야 하며 매년 인건비, 경상적 경비, 시설확충비를 보조하여야 한다.",
                "cost_trigger": True,
                "cost_candidate_strength": "strong",
                "trigger_type": "직접지원",
            },
        ]
        estimate = build_generalized_estimate(articles)
        families = {item["formula_family"] for item in estimate["items"]}
        self.assertEqual(
            families,
            {"institution_establishment", "personnel_compensation", "institution_operation"},
        )
        self.assertEqual(classify_estimation_status(estimate)["code"], "needs_external_data")

    def test_broad_system_policy_without_concrete_action_has_no_formula(self) -> None:
        articles = [{
            "no": "제21조의2(위험관리)",
            "text": "장관은 위험을 관리하기 위한 체계적 방안을 마련하여야 하며 구체적인 사항은 장관이 정한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "시설구축",
            "rule_cost_trigger": {"rule": "facility_or_system"},
        }]
        self.assertIsNone(build_generalized_estimate(articles))
        status = classify_estimation_status(None, technical_reason="사업 범위와 수행 방식이 정해지지 않음")
        self.assertEqual(status["code"], "technically_infeasible")


if __name__ == "__main__":
    unittest.main()
