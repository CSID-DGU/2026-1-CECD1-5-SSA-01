from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.erce_web.assembly_formula_engine import (
    apply_formula_source_strategy,
    apply_reasonable_default_amounts,
    apply_tag_formula_evidence,
    build_generalized_estimate,
    classify_estimation_status,
)
from backend.erce_web.assembly_analogy_engine import build_analogical_committee_estimate
from backend.erce_web.assembly_case_policy import apply_validated_case_policy
from backend.erce_web.calculator import compute_year_estimates
from backend.erce_web.form_renderer import render_form


class AssemblyFormulaEngineTest(unittest.TestCase):
    def test_split_bill_title_is_reconstructed(self) -> None:
        from backend.erce_web.analyzer_v2 import _extract_bill_name

        text = (
            "친환경농어업육성및유기식품등의관리ㆍ지원에관한\n"
            "법률일부개정법률안\n"
            "(송옥주의원대표발의)"
        )
        self.assertEqual(
            _extract_bill_name(text, "uploaded.pdf"),
            "친환경농어업육성및유기식품등의관리ㆍ지원에관한법률일부개정법률안",
        )

    def test_current_bill_number_is_reconstructed_for_rag_holdout(self) -> None:
        from backend.erce_web.analyzer_v2 import _extract_current_bill_no

        text = """
        의안 번호 14559
        발의연월일: 2025. 11. 26.
        친환경농어업 육성법 일부개정법률안
        """
        self.assertEqual(_extract_current_bill_no(text, "uploaded.pdf"), "2214559")
        self.assertEqual(_extract_current_bill_no(text, "2214559_의안원문.pdf"), "2214559")

    def test_vector_search_excludes_current_bill_and_refills_results(self) -> None:
        from backend.erce_web.analyzer_v2 import vector_search

        returned = [
            {"bill_no": "2214559", "chunk_id": "target:1"},
            {"bill_no": "2214559", "chunk_id": "target:2"},
            {"bill_no": "2216569", "chunk_id": "other:1"},
            {"bill_no": "2213486", "chunk_id": "other:2"},
        ]
        with patch("backend.erce_web.analyzer_v2._post", return_value=returned) as post:
            matches = vector_search(
                [0.0, 0.1],
                source="national_assembly",
                doc_type="cost_estimate",
                k=2,
                exclude_bill_nos={"2214559"},
            )

        self.assertEqual([row["bill_no"] for row in matches], ["2216569", "2213486"])
        self.assertEqual(post.call_args.args[2]["match_count"], 20)

    def test_korean_person_counter_is_parsed_for_committee_size(self) -> None:
        from backend.erce_web.analyzer_v2 import _extract_committee_total_members, _rule_cost_trigger

        article = "위원장과 부위원장 각 1인을 포함한 25인 이내의 위원으로 구성한다."
        self.assertEqual(_extract_committee_total_members(article), 25)
        rule = _rule_cost_trigger(
            "제18조의2(녹색산업발전위원회) 정책을 심의하기 위하여 장관 소속으로 위원회를 둔다. "
            "위원장과 부위원장 각 1인을 포함한 25인 이내의 위원으로 구성한다. "
            "운영에 필요한 사항은 대통령령으로 정한다."
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["rule"], "committee_or_body_operation")
        self.assertEqual(rule["estimate_feasibility"], "formula_ready")

    def test_non_estimable_llm_item_is_removed_before_defaults(self) -> None:
        from backend.erce_web.analyzer_v2 import _exclude_non_estimable_items

        estimate = {
            "items": [
                {"name": "민간단체 지원 소요", "trigger_ref": "안 제3조"},
                {"name": "발전위원회 운영비", "trigger_ref": "안 제18조의2"},
            ]
        }
        articles = [
            {
                "no": "제3조(국가와 지방자치단체의 책무)",
                "cost_candidate_strength": "weak",
                "estimate_feasibility": "non_attachment_review",
                "reason": "지원 대상과 단가가 정해지지 않음",
            },
            {
                "no": "제18조의2(친환경농어업발전위원회)",
                "cost_candidate_strength": "strong",
                "estimate_feasibility": "formula_ready",
            },
        ]
        self.assertEqual(_exclude_non_estimable_items(estimate, articles), 1)
        self.assertEqual([item["name"] for item in estimate["items"]], ["발전위원회 운영비"])
        self.assertEqual(estimate["excluded_items"][0]["trigger_ref"], "안 제3조")

    def test_ungrounded_llm_cost_claim_is_removed(self) -> None:
        from backend.erce_web.analyzer_v2 import _exclude_non_estimable_items

        estimate = {
            "items": [{
                "name": "직원 임면 관련 조세·부담금 감면",
                "trigger_ref": "제15조",
                "formula": "감면 대상 인원 × 1인당 감면액",
            }]
        }
        articles = [{
            "no": "제15조(직원의 임면)",
            "text": "병원장은 정관으로 정하는 바에 따라 직원을 임면한다.",
            "cost_candidate_strength": "medium",
            "estimate_feasibility": "external_data_needed",
        }]

        self.assertEqual(_exclude_non_estimable_items(estimate, articles), 1)
        self.assertEqual(estimate["items"], [])
        self.assertEqual(estimate["excluded_items"][0]["case_policy"], "ungrounded_cost_claim")
        self.assertIn("조세·부담금", estimate["excluded_items"][0]["reason"])

    def test_missing_evidence_creates_targeted_human_input_requests(self) -> None:
        from backend.erce_web.analyzer_v2 import _build_human_input_requests

        estimate = {
            "items": [{
                "name": "신규 지원사업",
                "formula_family": "transfer_payment",
                "variables_needed": ["지원 대상자 수", "1인당 지급액"],
                "assumptions": [
                    {
                        "name": "지원 대상자 수",
                        "value": None,
                        "unit": "명",
                        "source_type": "external_data",
                        "needs_user_confirm": True,
                    },
                    {
                        "name": "1인당 지급액",
                        "value": None,
                        "unit": "천원/명",
                        "source_type": "policy_input",
                        "needs_user_confirm": True,
                    },
                ],
                "calculation": {"base_amount_thousand": None},
            }]
        }
        apply_formula_source_strategy(estimate, [])

        human_input = _build_human_input_requests(estimate)

        self.assertEqual(human_input["status"], "required")
        self.assertEqual(human_input["blocking_count"], 2)
        self.assertEqual(
            [row["variable"] for row in human_input["requests"]],
            ["지원 대상자 수", "1인당 지급액"],
        )

    def test_missing_net_staff_shows_sourced_staffing_candidate(self) -> None:
        from backend.erce_web.analyzer_v2 import _build_human_input_requests

        estimate = {"items": [{
            "name": "지방법원 신설 인건비",
            "calculation": {"base_amount_thousand": None},
            "assumption_strategy": [{"variable": "순증 인원", "unit": "명",
                                     "status": "missing", "basis": "기존 정원과 전입 인원 미확인"}],
            "assumption_candidates": [{
                "assumption_key": "staffing_count", "label": "소요인력",
                "value": 28, "unit": "명", "bill_no": "2213969",
                "source_text": "안양지방법원 법원공무원 순증인원 28명",
            }],
        }]}
        request = _build_human_input_requests(estimate)["requests"][0]
        self.assertEqual(request["suggested_values"][0]["bill_no"], "2213969")
        self.assertTrue(request["blocking"])

    def test_committee_without_evidence_does_not_receive_flat_default(self) -> None:
        articles = [{
            "no": "제10조(새로운위원회)",
            "text": "장관은 새로운위원회를 설치하여야 한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "조직설치",
            "rule_cost_trigger": {"rule": "committee_or_body_operation"},
        }]
        estimate = build_generalized_estimate(articles)

        self.assertIsNotNone(estimate)
        self.assertEqual(apply_reasonable_default_amounts(estimate), 0)
        self.assertIsNone(estimate["items"][0]["calculation"]["base_amount_thousand"])
        calculated, _ = compute_year_estimates(estimate, tag_patterns=[], allow_estimated=False)
        self.assertIsNone(calculated)

    def test_human_inputs_recompute_transfer_formula_without_hidden_default(self) -> None:
        from backend.erce_web.analyzer_v2 import recompute_with_user_inputs

        articles = [{
            "no": "제4조(지원금의 지급)",
            "text": "국가는 지원대상자에게 지원금을 매월 지급하여야 한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "직접지원",
            "rule_cost_trigger": {"rule": "payment_or_subsidy"},
        }]
        estimate = build_generalized_estimate(articles)
        updated = recompute_with_user_inputs(
            estimate,
            [{
                "item_index": 0,
                "variables": {
                    "지원 대상자 수": 1_000,
                    "1인당 지급액": 50,
                    "지급 횟수": 12,
                    "집행률": 90,
                },
            }],
        )

        self.assertEqual(updated["items"][0]["calculation"]["base_amount_thousand"], 540_000)
        self.assertEqual([row["amount_thousand"] for row in updated["year_estimates"]], [540_000] * 5)
        self.assertEqual(updated["calculation_status"], "computed_by_python")
        self.assertNotIn("human_input", updated)

    def test_human_inputs_keep_initial_and_maintenance_costs_separate(self) -> None:
        from backend.erce_web.analyzer_v2 import recompute_with_user_inputs

        estimate = {
            "items": [{
                "name": "정보시스템 구축·운영비",
                "formula_family": "facility_system",
                "variables_needed": ["초기 구축비", "연간 유지관리비"],
                "assumptions": [
                    {"name": "초기 구축비", "value": None, "unit": "천원", "source_type": "external_data", "needs_user_confirm": True},
                    {"name": "연간 유지관리비", "value": None, "unit": "천원/년", "source_type": "external_data", "needs_user_confirm": True},
                ],
                "calculation": {"base_amount_thousand": None, "recurrence": "annual", "start_year": 1, "end_year": 5},
            }],
        }
        updated = recompute_with_user_inputs(
            estimate,
            [{
                "item_index": 0,
                "variables": {"초기 구축비": 500_000, "연간 유지관리비": 50_000},
            }],
        )

        self.assertEqual(
            [row["amount_thousand"] for row in updated["year_estimates"]],
            [550_000, 50_000, 50_000, 50_000, 50_000],
        )
        self.assertEqual(updated["calculation_status"], "computed_by_python")

    def test_committee_assumptions_transfer_ratio_and_use_robust_unit_cost(self) -> None:
        from backend.erce_web.analyzer_v2 import _enhance_committee_meeting_formulas

        item = {
            "name": "녹색산업발전위원회 운영비",
            "category": "운영비",
            "formula": "회의수당 단가 × 회의횟수 × 수당지급대상 인원",
            "variables_needed": ["회의수당 단가", "회의횟수", "수당지급대상 인원"],
            "trigger_ref": "제18조의2(녹색산업발전위원회)",
            "calculation": {"base_amount_thousand": 28_800},
            "assumption_candidates": [
                {
                    "assumption_key": "committee_meeting_count",
                    "value": 4,
                    "bill_no": "2200100",
                    "bill_name": "녹색산업법 일부개정법률안",
                    "source_text": "회의개최 횟수는 연간 4회로 가정",
                    "score": 1.4,
                },
                {
                    "assumption_key": "committee_meeting_count",
                    "value": 1,
                    "bill_no": "2200200",
                    "bill_name": "다른 분야 법률안",
                    "source_text": "회의는 연 1회로 가정",
                    "score": 0.7,
                },
                {
                    "assumption_key": "committee_paid_member_count",
                    "value": 24,
                    "bill_no": "2200100",
                    "bill_name": "녹색산업법 일부개정법률안",
                    "source_text": "위원회 정원 30명 중 민간위원 수는 24명으로 가정",
                    "score": 1.3,
                },
                {
                    "assumption_key": "committee_allowance_unit",
                    "value": 200_000,
                    "bill_no": "2200300",
                    "bill_name": "유사 위원회 법률안",
                    "source_text": "회의수당 단가는 20만원",
                    "score": 0.8,
                },
                {
                    "assumption_key": "committee_allowance_unit",
                    "value": 300_000,
                    "bill_no": "2200400",
                    "bill_name": "유사 심의회 법률안",
                    "source_text": "회의참석 사례금은 30만원",
                    "score": 0.79,
                },
            ],
        }
        articles = [{
            "no": "제18조의2(녹색산업발전위원회)",
            "text": "위원장과 부위원장 각 1인을 포함한 25인 이내의 위원으로 구성한다.",
        }]
        estimate = {"items": [item]}

        self.assertEqual(_enhance_committee_meeting_formulas(estimate, articles), 1)
        formula = item["committee_formula"]
        self.assertEqual(formula["meeting_count"], 4)
        self.assertEqual(formula["paid_members"], 20)
        self.assertEqual(formula["allowance_won"], 250_000)
        self.assertEqual(formula["amount_thousand"], 20_000)
        self.assertEqual(item["calculation"]["base_amount_thousand"], 20_000)
        self.assertTrue(formula["calculation_invariant"]["replaced_previous_base"])
        self.assertEqual(
            formula["calculation_invariant"]["previous_base_amount_thousand"],
            28_800,
        )
        self.assertEqual(
            formula["evidence_trace"]["paid_members"]["method"],
            "top_similar_case_ratio",
        )

    def test_generic_committee_candidates_use_target_excluded_corpus_mode(self) -> None:
        from backend.erce_web.analyzer_v2 import _extract_committee_meetings

        corpus = {
            "n": 119,
            "min": 1,
            "max": 12,
            "median": 4,
            "mode": 4,
            "mode_count": 49,
            "excluded_bill_nos": ["2199999"],
        }
        candidates = [
            {
                "assumption_key": "committee_meeting_count",
                "value": 1,
                "source_text": "회의횟수(연 1회)",
                "score": 0.96,
                "corpus_distribution": corpus,
            },
            {
                "assumption_key": "committee_meeting_count",
                "value": 3,
                "source_text": "연 3회 회의를 개최",
                "score": 0.95,
                "corpus_distribution": corpus,
            },
        ]

        value, _, _, trace = _extract_committee_meetings("", candidates)

        self.assertEqual(value, 4)
        self.assertEqual(trace["method"], "target_excluded_corpus_mode")
        self.assertEqual(trace["corpus_distribution"]["excluded_bill_nos"], ["2199999"])

    def test_subject_matched_committee_candidates_beat_corpus_mode(self) -> None:
        from backend.erce_web.analyzer_v2 import _extract_committee_meetings

        corpus = {"n": 100, "mode": 4, "mode_count": 40}
        candidates = [
            {
                "assumption_key": "committee_meeting_count",
                "value": 3,
                "source_text": "연간 3회의 회의",
                "score": 1.31,
                "corpus_distribution": corpus,
            },
            {
                "assumption_key": "committee_meeting_count",
                "value": 4,
                "source_text": "회의를 연 4회 개최",
                "score": 1.30,
                "corpus_distribution": corpus,
            },
        ]

        value, _, _, trace = _extract_committee_meetings("", candidates)

        self.assertEqual(value, 3)
        self.assertEqual(trace["method"], "tag_candidates_median")

    def test_generalized_merge_deduplicates_same_article_and_cost_family(self) -> None:
        from backend.erce_web.assembly_formula_engine import merge_generalized_estimate

        current = {
            "items": [
                {
                    "name": "정책위원회 운영",
                    "trigger_ref": "제18조, 제19조",
                    "category": "운영비",
                    "formula": "위원 수 × 회의 수당 + 행정지원 비용",
                },
                {
                    "name": "평가 결과 지원 비용",
                    "trigger_ref": "제32조",
                    "category": "지원금",
                    "formula": "지원 대상 × 지원 단가",
                },
            ]
        }
        generated = {
            "items": [
                {
                    "name": "정책위원회 운영비",
                    "trigger_ref": "제18조(정책위원회)",
                    "formula_family": "committee_operation",
                    "formula": "회의수당 단가 × 회의횟수 × 수당지급대상 인원",
                },
                {
                    "name": "평가 지원 소요",
                    "trigger_ref": "제32조(평가)",
                    "formula_family": "transfer_payment",
                    "formula": "지원 대상자 수 × 1인당 지급액",
                },
            ]
        }

        merged = merge_generalized_estimate(current, generated)

        self.assertEqual(len(merged["items"]), 2)
        self.assertTrue(all(item.get("merged_llm_drafts") for item in merged["items"]))

    def test_plan_draft_merges_into_research_service_item(self) -> None:
        from backend.erce_web.assembly_formula_engine import merge_generalized_estimate

        current = {"items": [{
            "name": "발전종합계획 수립",
            "trigger_ref": "제21조",
            "category": "사업비",
            "formula": "회당 계획수립 비용",
            "calculation": {"base_amount_thousand": 89_000},
        }]}
        generated = {"items": [{
            "name": "발전종합계획 연구용역비",
            "trigger_ref": "제21조(발전종합계획)",
            "category": "위탁비",
            "formula_family": "research_service",
            "formula": "용역 단가 × 5년마다 1회",
        }]}

        merged = merge_generalized_estimate(current, generated)

        self.assertEqual(len(merged["items"]), 1)
        self.assertEqual(merged["items"][0]["formula_family"], "research_service")
        self.assertEqual(merged["items"][0]["merged_llm_drafts"][0]["name"], "발전종합계획 수립")

    def test_committee_creation_and_composition_articles_are_one_cost_item(self) -> None:
        from backend.erce_web.analyzer_v2 import _enhance_committee_meeting_formulas

        articles = [
            {
                "no": "제18조(국립병원발전위원회)",
                "text": "장관 소속으로 국립병원발전위원회를 둔다.",
                "cost_trigger": True,
                "cost_candidate_strength": "medium",
                "trigger_type": "조직설치",
                "rule_cost_trigger": {"rule": "committee_or_body_operation"},
            },
            {
                "no": "제19조(위원회의 구성)",
                "text": "위원회는 공동위원장 2명을 포함한 25명 이내의 위원으로 구성한다.",
                "cost_trigger": True,
                "cost_candidate_strength": "strong",
                "trigger_type": "조직설치",
                "rule_cost_trigger": {"rule": "committee_or_body_operation"},
            },
        ]

        estimate = build_generalized_estimate(articles)

        self.assertEqual(len(estimate["items"]), 1)
        self.assertEqual(_enhance_committee_meeting_formulas(estimate, articles), 1)
        self.assertEqual(estimate["items"][0]["committee_formula"]["paid_members"], 12)

    def test_explicit_five_year_plan_is_formula_ready_and_periodic(self) -> None:
        from backend.erce_web.analyzer_v2 import _rule_cost_trigger

        text = (
            "제21조(발전종합계획) 장관은 사업의 발전을 위한 "
            "종합계획을 5년마다 수립하여야 한다."
        )
        rule = _rule_cost_trigger(text)
        self.assertEqual(rule["rule"], "survey_or_plan_service")
        self.assertEqual(rule["candidate_strength"], "strong")
        self.assertEqual(rule["estimate_feasibility"], "formula_ready")

        articles = [{
            "no": "제21조(발전종합계획)",
            "text": text,
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "의무부과",
            "rule_cost_trigger": rule,
        }]
        estimate = build_generalized_estimate(articles)
        item = estimate["items"][0]
        self.assertEqual(item["calculation"]["recurrence"], "periodic")
        self.assertEqual(item["calculation"]["interval_years"], 5)
        item["calculation"]["base_amount_thousand"] = 100_000
        calculated, issues = compute_year_estimates(estimate, allow_estimated=False)
        self.assertFalse(issues)
        self.assertEqual([row["amount_thousand"] for row in calculated], [100_000, 0, 0, 0, 0])

    def test_differential_allocation_does_not_create_new_support_total(self) -> None:
        articles = [{
            "no": "제32조(평가)",
            "text": (
                "장관은 사업실적을 매년 평가하고 그 결과를 반영하여 "
                "기존 출연금을 교부할 경우 차등지원할 수 있다."
            ),
            "cost_trigger": True,
            "trigger_type": "직접지원",
            "cost_candidate_strength": "medium",
        }]

        result = apply_validated_case_policy(articles)

        self.assertEqual(result[0]["estimate_feasibility"], "no_incremental_cost")
        self.assertEqual(result[0]["case_policy"], "differential_allocation_only")

    def test_appointment_article_is_not_misread_as_tax_exemption_at_text_boundary(self) -> None:
        articles = [{
            "no": "제15조(직원 등의 임면)",
            "text": "제15조(직원 등의 임면) 기관의 직원은 정관으로 정하는 바에 따라 임면한다.",
            "cost_trigger": True,
            "trigger_type": "조직설치",
            "cost_candidate_strength": "medium",
        }]

        result = apply_validated_case_policy(articles)

        self.assertFalse(result[0]["cost_trigger"])
        self.assertEqual(result[0]["case_policy"], "unverified_ai_candidate_suppressed")

    def test_non_committee_organization_label_does_not_create_committee_formula(self) -> None:
        articles = [{
            "no": "제15조(직원 등의 임면)",
            "text": "기관의 직원은 정관으로 정하는 바에 따라 임면한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "조직설치",
        }]

        self.assertIsNone(build_generalized_estimate(articles))

    def test_assembly_form_uses_final_article_exclusion_reason(self) -> None:
        result = {
            "billName": "보건인력지원법안",
            "docType": "제정안",
            "verdict": {"type": "비용추계서 작성 대상"},
            "articles": [{
                "no": "제16조(교육전담간호사)",
                "text": "교육전담간호사를 지원할 수 있다.",
                "cost_trigger": True,
                "cost_candidate_strength": "weak",
                "estimate_feasibility": "no_incremental_cost",
                "case_policy": "transferred_existing_provision",
                "reason": "종전 법률의 동일 제도를 옮긴 것으로 기존 사업의 계속 수행에 해당합니다.",
            }],
            "estimate": {
                "items": [{
                    "name": "간호정책심의위원회 운영비",
                    "trigger_ref": "제26조(간호정책심의위원회)",
                    "year_amounts_thousand": [4000] * 5,
                }],
                "year_estimates": [
                    {"year": year, "amount_thousand": 4000}
                    for year in range(1, 6)
                ],
            },
        }

        html = render_form(result, format="assembly")

        self.assertIn("기시행 사업으로 추가 비용을 수반하지 않음", html)
        self.assertIn(">×<", html)
        self.assertNotIn("계획·조사·행정절차 성격이 강해", html)

    def test_ai_only_routine_administration_is_not_a_cost_factor(self) -> None:
        articles = [
            {
                "no": "제8조(국가시험)",
                "text": "장관은 국가시험 관리를 위탁하고 필요한 예산을 지원할 수 있다.",
                "cost_trigger": True,
                "trigger_type": "위탁대행",
                "case_policy": "transferred_existing_provision",
                "reason": "기존 국가시험 제도를 이전함",
            },
            {
                "no": "제10조(면허 또는 자격의 등록과 조건)",
                "text": "보건복지부장관은 면허등록대장을 작성하고 면허증을 발급하여야 한다.",
                "cost_trigger": True,
                "trigger_type": "의무부과",
                "reason": "행정 비용이 발생할 수 있음",
            },
            {
                "no": "제31조(일·가정 양립 지원)",
                "text": "의료기관의 장은 대체인력 채용 등 필요한 조치를 강구하여야 한다.",
                "cost_trigger": True,
                "trigger_type": "의무부과",
                "reason": "채용 비용이 발생할 수 있음",
            },
        ]

        result = apply_validated_case_policy(articles)

        self.assertFalse(result[0]["cost_trigger"])
        self.assertFalse(result[1]["cost_trigger"])
        self.assertFalse(result[2]["cost_trigger"])
        self.assertEqual(result[0]["case_policy"], "unverified_ai_candidate_suppressed")

    def test_rule_confirmed_public_support_survives_ai_candidate_filter(self) -> None:
        articles = [{
            "no": "제20조(운영비 지원)",
            "text": "국가는 센터 운영에 필요한 비용의 전부 또는 일부를 지원할 수 있다.",
            "cost_trigger": True,
            "trigger_type": "직접지원",
            "rule_cost_trigger": {
                "rule": "payment_or_subsidy",
                "force_cost": True,
            },
        }]

        result = apply_validated_case_policy(articles)

        self.assertTrue(result[0]["cost_trigger"])

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
        self.assertEqual(apply_formula_source_strategy(estimate, patterns), 1)
        item = estimate["items"][0]
        self.assertEqual(item["selected_formula"]["source_type"], "tag_similar_formula")
        self.assertEqual(item["tag_formula_candidate"]["formula"], "용역 단가 × 연 1회")
        self.assertTrue(any(row["variable"] == "용역 단가" for row in item["assumption_strategy"]))
        calculated, issues = compute_year_estimates(
            estimate,
            tag_patterns=patterns,
            allow_estimated=False,
        )
        self.assertFalse(issues)
        self.assertEqual([row["amount_thousand"] for row in calculated], [190_000] * 5)
        self.assertEqual(classify_estimation_status(estimate)["code"], "computed_with_estimates")

    def test_committee_without_meeting_evidence_waits_for_human_input(self) -> None:
        articles = [{
            "no": "제26조(정책심의위원회)",
            "text": "정책을 심의하기 위하여 정책심의위원회를 둔다. 위원회는 위원장 1명을 포함한 15명 이내의 위원으로 구성한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "조직설치",
            "rule_cost_trigger": {"rule": "committee_or_body_operation"},
        }]
        estimate = build_generalized_estimate(articles)
        self.assertIsNotNone(estimate)

        from backend.erce_web.analyzer_v2 import _enhance_committee_meeting_formulas

        self.assertEqual(_enhance_committee_meeting_formulas(estimate, articles), 1)
        patterns = [{
            "bill_no": "2299999",
            "bill_name": "고액 위원회 운영 사례",
            "items": [{
                "category": "운영비",
                "name": "정책심의위원회 운영비",
                "variables": [],
                "amounts": [
                    {"amount_thousand": 99_000, "formula": "유사 위원회 연간 운영비", "is_total": False},
                ],
            }],
        }]

        self.assertEqual(apply_tag_formula_evidence(estimate, patterns), 0)
        self.assertEqual(apply_formula_source_strategy(estimate, patterns), 1)
        item = estimate["items"][0]
        self.assertIsNone(item["calculation"]["base_amount_thousand"])
        self.assertIsNone(item["committee_formula"]["amount_thousand"])
        self.assertEqual(item["committee_formula"]["evidence_trace"]["meeting_count"]["method"], "missing_evidence")
        meeting_strategy = next(
            row for row in item["assumption_strategy"] if row["variable"] == "회의횟수"
        )
        self.assertEqual(meeting_strategy["status"], "missing")
        self.assertEqual(item["selected_formula"]["source_type"], "standard_structured_formula")

    def test_scale_dependent_item_cannot_use_hidden_tag_fallback(self) -> None:
        estimate = {
            "items": [{
                "name": "정보시스템 구축비",
                "category": "시설구축비",
                "formula_family": "facility_system",
                "calculation": {"base_amount_thousand": None, "recurrence": "annual"},
            }],
        }
        patterns = [{
            "bill_no": "2200999",
            "bill_name": "유사 시스템 법률안",
            "items": [{
                "category": "시설구축비",
                "name": "정보시스템 구축비",
                "amounts": [{"amount_thousand": 500_000, "is_total": False}],
            }],
        }]

        calculated, issues = compute_year_estimates(estimate, tag_patterns=patterns, allow_estimated=True)

        self.assertIsNone(calculated)
        self.assertIsNone(estimate["items"][0]["calculation"]["base_amount_thousand"])
        self.assertTrue(any(issue.get("level") == "error" for issue in issues))

    def test_tag_formula_candidate_is_kept_when_variables_are_missing(self) -> None:
        articles = [{
            "no": "제12조(정책연구)",
            "text": "장관은 정책연구를 실시할 수 있다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "의무부과",
            "rule_cost_trigger": {"rule": "survey_or_plan_service"},
        }]
        estimate = build_generalized_estimate(articles)
        self.assertIsNotNone(estimate)
        patterns = [{
            "bill_no": "2200100",
            "bill_name": "정책연구 법률안",
            "items": [{
                "category": "위탁비",
                "name": "정책연구 연구용역비",
                "variables": [
                    {"name": "용역 단가", "value": "120000", "unit": "천원/회"},
                    {"name": "수행 횟수", "value": "1", "unit": "회/년"},
                ],
                "amounts": [
                    {"amount_thousand": 120_000, "formula": "용역 단가 × 수행 횟수", "is_total": False},
                ],
            }],
        }]

        self.assertEqual(apply_formula_source_strategy(estimate, patterns), 1)

        item = estimate["items"][0]
        self.assertEqual(item["selected_formula"]["source_type"], "tag_similar_formula_candidate")
        self.assertEqual(item["tag_formula_candidate"]["formula"], "용역 단가 × 수행 횟수")
        self.assertEqual(item["assumption_strategy"][0]["source_type"], "tag_similar_case")
        self.assertTrue(item["assumption_strategy"][0]["requires_review"])

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

    def test_tax_reduction_overrides_direct_support_classification(self) -> None:
        articles = [{
            "no": "제10조(세액공제)",
            "text": "법인세 세액공제의 적용기한을 연장한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "직접지원",
            "rule_cost_trigger": {"rule": "payment_or_subsidy"},
        }]

        result = apply_validated_case_policy(articles)

        self.assertEqual(result[0]["trigger_type"], "세수감소")
        self.assertEqual(result[0]["formula_family"], "revenue_loss")

    def test_revenue_loss_rule_is_general_but_tax_specific(self) -> None:
        articles = [
            {
                "no": "제10조(법인세 세액공제)",
                "text": "법인세 세액공제의 적용기한을 3년 연장한다.",
                "cost_trigger": True,
                "cost_candidate_strength": "medium",
                "trigger_type": "직접지원",
            },
            {
                "no": "제20조(입장료 감면)",
                "text": "시설 이용자의 입장료를 감면할 수 있다.",
                "cost_trigger": True,
                "cost_candidate_strength": "medium",
                "trigger_type": "직접지원",
                "rule_cost_trigger": {"rule": "payment_or_subsidy"},
            },
        ]

        result = apply_validated_case_policy(articles)

        self.assertEqual(result[0]["trigger_type"], "세수감소")
        self.assertEqual(result[1]["trigger_type"], "직접지원")
        self.assertNotIn("formula_family", result[1])

    def test_revenue_loss_uses_negative_tag_amount(self) -> None:
        articles = [{
            "no": "제10조(세액공제)",
            "text": "연구개발비 법인세 세액공제의 적용기한을 연장한다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "세수감소",
        }]
        estimate = build_generalized_estimate(articles)
        patterns = [{
            "bill_no": "2299998",
            "bill_name": "조세특례제한법 일부개정법률안",
            "items": [{
                "category": "지원금",
                "name": "연구개발비 법인세 세액공제",
                "variables": [{
                    "name": "연평균 감면액",
                    "value": 10,
                    "unit": "천원",
                }],
                "amounts": [
                    {
                        "amount_thousand": -10_000,
                        "formula": "최근 5년 연평균 감면실적",
                        "is_total": False,
                    },
                    {
                        "amount_thousand": -50_000,
                        "formula": "연평균 감면실적 × 5년",
                        "is_total": True,
                    },
                ],
            }],
        }]

        self.assertIsNotNone(estimate)
        self.assertEqual(estimate["items"][0]["formula_family"], "revenue_loss")
        self.assertEqual(apply_tag_formula_evidence(estimate, patterns), 1)
        calculated, issues = compute_year_estimates(
            estimate,
            tag_patterns=patterns,
            allow_estimated=False,
        )

        self.assertFalse(issues)
        self.assertEqual(
            [row["amount_thousand"] for row in calculated],
            [-10_000] * 5,
        )

    def test_scale_dependent_facility_does_not_receive_flat_default(self) -> None:
        articles = [{
            "no": "제20조(센터 설치)",
            "text": "장관은 센터를 설치하고 필요한 시스템을 구축하여 운영할 수 있다.",
            "cost_trigger": True,
            "cost_candidate_strength": "medium",
            "trigger_type": "시설구축",
            "rule_cost_trigger": {"rule": "facility_or_system"},
        }]
        estimate = build_generalized_estimate(articles)

        self.assertIsNotNone(estimate)
        self.assertEqual(apply_reasonable_default_amounts(estimate), 0)
        item = estimate["items"][0]
        self.assertIsNone(item["calculation"]["base_amount_thousand"])
        calculated, issues = compute_year_estimates(estimate, tag_patterns=[], allow_estimated=True)
        self.assertIsNone(calculated)
        self.assertTrue([issue for issue in issues if issue.get("level") == "error"])

    def test_high_court_establishment_uses_judicial_institution_template(self) -> None:
        from backend.erce_web.analyzer_v2 import _build_public_organization_establishment_estimate

        text = (
            "각급 법원의 설치와 관할구역에 관한 법률 일부개정법률안 "
            "별표1의 서울고등법원란 다음에 인천고등법원란을 신설한다. "
            "부칙 이 법은 2029년 3월 1일부터 시행한다."
        )
        articles = [{
            "no": "안 [별표1], [별표3] 및 [별표5]",
            "text": "인천광역시와 부천시·김포시를 관할하는 인천고등법원을 설치함",
            "cost_trigger": True,
            "cost_candidate_strength": "strong",
            "trigger_type": "조직설치",
        }]

        estimate = _build_public_organization_establishment_estimate(
            text,
            articles,
            form_type="assembly",
        )

        self.assertIsNotNone(estimate)
        self.assertEqual(estimate["template_key"], "public_organization_establishment.judicial_high_court")
        self.assertEqual([row["amount_thousand"] for row in estimate["year_estimates"]], [6_698_000, 7_837_000, 7_987_000, 8_141_000, 8_296_000])
        self.assertEqual(estimate["total_amount_thousand"], 38_959_000)
        self.assertEqual([item["name"] for item in estimate["items"]], ["인천고등법원 운영비용", "인천고등검찰청 운영비용"])

    def test_tag_full_structure_is_promoted_to_estimate(self) -> None:
        from backend.erce_web.analyzer_v2 import _build_estimate_from_tag_pattern

        pattern = {
            "bill_no": "2126648",
            "bill_name": "각급 법원의 설치와 관할구역에 관한 법률 일부개정법률안",
            "items": [
                {
                    "category": "운영비",
                    "name": "인천고등법원 신설 비용",
                    "trigger_ref": "안 [별표1], [별표3], [별표5]",
                    "variables": [{"name": "신규 충원 공무원 수", "value": 24, "unit": "명"}],
                    "amounts": [
                        {"year_label": "2029", "year_offset": 1, "amount_thousand": 2_687_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2030", "year_offset": 2, "amount_thousand": 3_131_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2031", "year_offset": 3, "amount_thousand": 3_191_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2032", "year_offset": 4, "amount_thousand": 3_253_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2033", "year_offset": 5, "amount_thousand": 3_315_000, "formula": "TAG 산식", "is_total": False},
                    ],
                },
                {
                    "category": "운영비",
                    "name": "인천고등검찰청 신설 비용",
                    "trigger_ref": "검찰청법 제3조",
                    "variables": [{"name": "신규 충원 공무원 수", "value": 31, "unit": "명"}],
                    "amounts": [
                        {"year_label": "2029", "year_offset": 1, "amount_thousand": 4_011_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2030", "year_offset": 2, "amount_thousand": 4_706_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2031", "year_offset": 3, "amount_thousand": 4_796_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2032", "year_offset": 4, "amount_thousand": 4_888_000, "formula": "TAG 산식", "is_total": False},
                        {"year_label": "2033", "year_offset": 5, "amount_thousand": 4_981_000, "formula": "TAG 산식", "is_total": False},
                    ],
                },
            ],
        }

        estimate = _build_estimate_from_tag_pattern(pattern, similarity=0.93)

        self.assertIsNotNone(estimate)
        self.assertEqual(estimate["template_key"], "tag_full_structure")
        self.assertEqual(estimate["calculation_status"], "computed_with_tag_structure")
        self.assertEqual([row["amount_thousand"] for row in estimate["year_estimates"]], [6_698_000, 7_837_000, 7_987_000, 8_141_000, 8_296_000])
        self.assertEqual(estimate["total_amount_thousand"], 38_959_000)

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
