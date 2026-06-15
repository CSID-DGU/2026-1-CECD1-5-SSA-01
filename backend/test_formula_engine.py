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

    def test_transitional_provision_marks_existing_center_as_no_incremental_cost(self) -> None:
        articles = [{
            "no": "제32조(지원센터의 설치 및 운영)",
            "text": "장관은 지역별 지원센터를 설치·운영할 수 있다.",
            "cost_trigger": True,
            "trigger_type": "조직설치",
            "cost_candidate_strength": "medium",
        }]
        document = (
            "부칙 제5조(지원센터에 관한 경과조치) 이 법 시행 당시 종전의 법률에 따라 "
            "설치·운영 중인 취업교육센터는 이 법 제32조에 따른 지원센터로 본다."
        )
        result = apply_validated_case_policy(articles, document_text=document)
        self.assertEqual(result[0]["estimate_feasibility"], "no_incremental_cost")
        self.assertEqual(result[0]["incremental_cost_status"], "existing_program_continuation")

    def test_deleted_legacy_provision_with_same_title_is_treated_as_transfer(self) -> None:
        articles = [{
            "no": "제16조(교육전담인력)",
            "text": "국가는 교육전담인력 운영에 필요한 비용을 지원할 수 있다.",
            "cost_trigger": True,
            "trigger_type": "직접지원",
            "cost_candidate_strength": "medium",
            "similar_refs": [{
                "bill_no": "2200000",
                "content": "제41조의2(교육전담인력) ① 기관에는 교육전담인력을 두어야 한다.",
            }],
        }]
        result = apply_validated_case_policy(
            articles,
            document_text="다른 법률의 개정 법률 제12345호 제41조의2를 삭제한다.",
        )
        self.assertEqual(result[0]["estimate_feasibility"], "no_incremental_cost")
        self.assertEqual(result[0]["incremental_cost_status"], "transferred_existing_provision")

    def test_linked_plan_and_survey_are_absorbed_by_existing_admin_framework(self) -> None:
        articles = [
            {
                "no": "제10조(종합계획)",
                "text": "장관은 현행 보건계획과 연계하여 종합계획을 수립하여야 한다.",
                "cost_trigger": True,
                "trigger_type": "의무부과",
                "cost_candidate_strength": "medium",
            },
            {
                "no": "제11조(시행계획)",
                "text": "장관은 종합계획에 따라 매년 시행계획을 수립하여야 한다.",
                "cost_trigger": True,
                "trigger_type": "의무부과",
                "cost_candidate_strength": "medium",
            },
            {
                "no": "제12조(실태조사)",
                "text": "장관은 실태조사를 실시하고 그 결과를 종합계획과 시행계획에 반영하여야 한다.",
                "cost_trigger": True,
                "trigger_type": "의무부과",
                "cost_candidate_strength": "medium",
            },
        ]
        result = apply_validated_case_policy(articles)
        self.assertTrue(all(row["cost_candidate_strength"] == "weak" for row in result))
        self.assertTrue(all(row["estimate_feasibility"] == "no_incremental_cost" for row in result))

    def test_unquantified_discretionary_subsidy_is_not_auto_calculated(self) -> None:
        articles = [{
            "no": "제20조(경비 보조)",
            "text": "장관은 필요하다고 인정할 때 관련 단체의 운영 경비를 보조할 수 있다.",
            "cost_trigger": True,
            "trigger_type": "직접지원",
            "cost_candidate_strength": "medium",
        }]
        result = apply_validated_case_policy(articles)
        self.assertEqual(result[0]["cost_candidate_strength"], "weak")
        self.assertEqual(result[0]["incremental_cost_status"], "discretionary_unquantified")

    def test_declarative_government_duty_is_review_only(self) -> None:
        articles = [{
            "no": "제3조(국가 및 지방자치단체의 책무)",
            "text": "국가와 지방자치단체는 재정지원 등 필요한 시책을 마련하여야 한다.",
            "cost_trigger": True,
            "trigger_type": "의무부과",
            "cost_candidate_strength": "medium",
        }]
        result = apply_validated_case_policy(articles)
        self.assertEqual(result[0]["cost_candidate_strength"], "weak")
        self.assertEqual(result[0]["incremental_cost_status"], "declarative_unquantified")

    def test_existing_referenced_service_is_not_treated_as_new_program(self) -> None:
        articles = [{
            "no": "제27조(통합서비스 등의 제공 등)",
            "text": "국가는 의료법 제4조의2에 따른 통합서비스 확대를 지원하여야 한다.",
            "cost_trigger": True,
            "trigger_type": "의무부과",
            "cost_candidate_strength": "medium",
            "similar_refs": [{
                "bill_no": "2200000",
                "content": "제4조의2(통합서비스 제공 등) 기존 통합서비스를 제공한다.",
            }],
        }]
        document = "부칙 다른 법령에서 종전의 의료법 규정을 인용한 경우 이 법의 해당 규정으로 갈음한다."
        result = apply_validated_case_policy(articles, document_text=document)
        self.assertEqual(result[0]["estimate_feasibility"], "no_incremental_cost")
        self.assertEqual(result[0]["incremental_cost_status"], "referenced_existing_program")

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
