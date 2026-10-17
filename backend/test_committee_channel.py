from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from backend.committee_channel import (
    _build_committee,
    _calculate_committee,
    _entity_from_body,
    _extract_explicit_amendment_articles,
    _formula_family,
    _ground_llm_committee_groups,
    _group_committee_articles,
    _group_committee_articles_hybrid,
    _meeting_count_from_document,
    _member_delta_from_document,
    _mode_or_median,
    _normalise_allowance,
    _paid_members_from_document,
    _rag_case_assumption_candidates,
    _replication_factor,
    _representative_value,
    _select_variable_evidence_with_llm,
    _select_formula_with_llm,
    _suggest_from_tag,
    _token_overlap,
    recompute_committee_result,
)


def _tag_candidate(key: str, value: float, bill_no: str, source_text: str, unit: str) -> dict:
    return {
        "assumption_key": key,
        "value": value,
        "unit": unit,
        "bill_no": bill_no,
        "bill_name": f"유사의안 {bill_no}",
        "item_name": "정책심의위원회 운영",
        "source_text": source_text,
        "score": 0.9,
    }


class ReplicationTest(unittest.TestCase):
    """복제(×N) 스케일 감지·적용 검증."""

    def _committee(self, name: str, text: str) -> dict:
        return {
            "name": name,
            "articles": [{"no": "제12조", "text": text}],
            "variables": {
                "meeting_count": {"value": 4, "confirmed": True},
                "paid_members": {"value": 10, "confirmed": True},
                "allowance_won": {"value": 200000, "confirmed": True},
            },
        }

    def test_central_committee_no_replication(self) -> None:
        factor, _, confident = _replication_factor("장관 소속으로 위원회를 둔다", "중앙정책위원회")
        self.assertEqual(factor, 1)
        self.assertTrue(confident)

    def test_sido_applies_17(self) -> None:
        factor, _, confident = _replication_factor("시·도지사는 지역위원회를 둔다", "시ㆍ도위원회")
        self.assertEqual(factor, 17)
        self.assertFalse(confident)  # 적용하되 확인 필요

    def test_explicit_count_applied(self) -> None:
        factor, _, confident = _replication_factor("8개 광역지방자치단체에 각각 설치한다", "센터")
        self.assertEqual(factor, 8)
        self.assertTrue(confident)

    def test_sigungu_mandatory_applies_229(self) -> None:
        # 의무설치("둔다") + 아래아(ㆍ) 구분자 → 기초자치단체 229개 상수 적용.
        factor, basis, confident = _replication_factor("각 시·군·구에 위원회를 둔다", "시ㆍ군ㆍ구위원회")
        self.assertEqual(factor, 229)
        self.assertFalse(confident)  # 적용하되 확인 필요
        self.assertIn("확인", basis)

    def test_sigungu_optional_not_multiplied(self) -> None:
        # 임의설치("둘 수 있다") → 전수 곱하지 않고 확인필요.
        factor, basis, confident = _replication_factor("시·군·구에 위원회를 둘 수 있다", "시ㆍ군ㆍ구위원회")
        self.assertEqual(factor, 1)
        self.assertFalse(confident)
        self.assertIn("확인", basis)

    def test_passing_mention_not_replicated(self) -> None:
        # 본문에 '시·도지사와 협의'처럼 단순 언급만 있으면 복제로 보면 안 된다(오탐 방지).
        factor, _, confident = _replication_factor(
            "위원회는 필요하면 시·도지사와 협의하고 장관 소속으로 위원회를 둔다", "중앙심의위원회"
        )
        self.assertEqual(factor, 1)
        self.assertTrue(confident)

    def test_calculate_applies_factor_and_flags(self) -> None:
        c = self._committee("시ㆍ도위원회", "시·도지사는 지역위원회를 둔다")
        _calculate_committee(c)
        # 단위 8,000천 × 17 = 136,000천/년
        self.assertEqual(c["replication"]["factor"], 17)
        self.assertEqual(c["annual_amount_thousand"], 136000)
        self.assertEqual(c["status"], "review_required")

    def test_calculate_central_stays_computed(self) -> None:
        c = self._committee("중앙위원회", "장관 소속으로 위원회를 둔다")
        _calculate_committee(c)
        self.assertEqual(c["replication"]["factor"], 1)
        self.assertEqual(c["annual_amount_thousand"], 8000)
        self.assertEqual(c["status"], "computed")


class CommitteeChannelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.articles = [
            {
                "no": "제십조(정책심의위원회)",
                "text": "정책을 심의하기 위하여 정책심의위원회를 둔다.",
                "change_type": "신설",
            },
            {
                "no": "제십일조(위원회의 구성)",
                "text": "위원회는 위원장 1명을 포함하여 15명 이내로 구성하며 위촉위원은 8명으로 한다.",
                "change_type": "신설",
            },
            {
                "no": "제십이의조(위원회의 회의)",
                "text": "위원회는 분기별 1회 회의를 개최한다.",
                "change_type": "신설",
            },
        ]

    def test_articles_are_grouped_by_named_committee(self) -> None:
        groups = _group_committee_articles(self.articles)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["entity"], "정책심의위원회")
        self.assertEqual(len(groups[0]["articles"]), 3)

    def test_private_association_committee_and_cross_reference_are_not_candidates(self) -> None:
        articles = [
            {
                "no": "제17조(중앙회)",
                "text": (
                    "중앙회의 지부 설치는 보건복지부장관의 승인을 받아야 한다. "
                    "간호사중앙회는 내부 징계를 심의하기 위하여 윤리위원회를 둔다."
                ),
                "change_type": "신설",
            },
            {
                "no": "제19조(징계)",
                "text": "제17조에 따른 윤리위원회의 심의를 거쳐 장관에게 요구할 수 있다.",
                "change_type": "신설",
            },
            *self.articles,
        ]
        groups = _group_committee_articles(articles)
        self.assertEqual([group["entity"] for group in groups], ["정책심의위원회"])

    def test_existing_public_committee_with_new_required_review_is_grouped(self) -> None:
        articles = [{
            "no": "제5조(사용승인)",
            "text": (
                "시장은 건축법 제4조에 따라 해당 지방자치단체에 두는 "
                "건축위원회의 심의를 거쳐 사용승인서를 내주어야 한다."
            ),
            "change_type": "제정",
        }]
        self.assertEqual(_entity_from_body(articles[0]["text"]), "건축위원회")
        groups = _group_committee_articles(articles)
        self.assertEqual([group["entity"] for group in groups], ["건축위원회"])

    def test_loose_reference_to_another_committee_is_not_grouped(self) -> None:
        articles = [{
            "no": "제20조(기능)",
            "text": "기금운용심의회에서 심의하여야 할 사항을 논의한다.",
            "change_type": "제정",
        }]
        self.assertEqual(_group_committee_articles(articles), [])

    def test_body_entity_removes_clause_prefix_and_unnamed_pointer(self) -> None:
        self.assertEqual(
            _entity_from_body(
                "도지사는 필요한 때에는 광역생활권위원회의 심의를 거쳐야 한다."
            ),
            "광역생활권위원회",
        )
        self.assertEqual(
            _entity_from_body(
                "제5항에 따른 외국교육기관설립운영심의위원회의 심의를 마쳐야 하며, "
                "도지사는 각각에 소속되는 위원회를 둔다."
            ),
            "외국교육기관설립운영심의위원회",
        )

    def test_generic_pointer_is_attached_not_created_as_an_entity(self) -> None:
        articles = [
            {
                "no": "제6조(국가데이터진흥위원회의 설치)",
                "text": "장관 소속으로 국가데이터진흥위원회를 둔다.",
                "change_type": "제정",
            },
            {
                "no": "제7조(위원회의 구성 및 운영)",
                "text": (
                    "위원회는 위원장 1명을 포함한 20명 이내의 위원으로 구성한다. "
                    "그 밖에 위원회의 운영에 필요한 사항은 대통령령으로 정한다."
                ),
                "change_type": "제정",
            },
        ]
        groups = _group_committee_articles(articles)
        self.assertEqual([group["entity"] for group in groups], ["국가데이터진흥위원회"])
        self.assertEqual(len(groups[0]["articles"]), 2)

    @patch("backend.committee_channel._gemini_raw_json")
    def test_llm_groups_definition_and_generic_followup_articles(self, llm_mock) -> None:
        articles = [
            {
                "no": "제18조(국립대학병원발전위원회)",
                "text": (
                    "중요한 사항을 논의하기 위하여 보건복지부장관 소속하에 "
                    "국립대학병원발전위원회(이하 위원회라 한다)를 둔다."
                ),
                "change_type": "제정",
            },
            {
                "no": "제19조(위원회의 구성)",
                "text": "위원회는 공동위원장 2명을 포함한 25명 이내의 위원으로 구성한다.",
                "change_type": "제정",
            },
            {
                "no": "제20조(위원회의 기능)",
                "text": (
                    "위원회는 발전계획을 심의한다. 또한 기금운용심의회에서 "
                    "심의하여야 할 사항을 논의한다."
                ),
                "change_type": "제정",
            },
        ]
        llm_mock.return_value = {"groups": [{
            "entity": "국립대학병원발전위원회",
            "definition_article": "제18조",
            "definition_evidence": "국립대학병원발전위원회(이하 위원회라 한다)를 둔다",
            "related_articles": ["제18조", "제19조", "제20조"],
        }]}
        groups, diagnostics = _group_committee_articles_hybrid(articles)
        self.assertEqual([group["entity"] for group in groups], ["국립대학병원발전위원회"])
        self.assertEqual(len(groups[0]["articles"]), 3)
        self.assertEqual(diagnostics["method"], "llm_semantic_plus_grounding")

    def test_llm_reference_without_installation_evidence_is_rejected(self) -> None:
        articles = [{
            "no": "제20조(위원회의 기능)",
            "text": "기금운용심의회에서 심의하여야 할 사항을 논의한다.",
            "change_type": "제정",
        }]
        groups, rejected = _ground_llm_committee_groups(articles, [{
            "entity": "기금운용심의회",
            "definition_article": "제20조",
            "definition_evidence": "기금운용심의회에서 심의하여야 할 사항",
            "related_articles": ["제20조"],
        }])
        self.assertEqual(groups, [])
        self.assertTrue(rejected)

    @patch("backend.committee_channel._gemini_raw_json")
    def test_llm_precedent_ranking_can_only_select_grounded_candidates(self, llm_mock) -> None:
        def candidate(key: str, bill_no: str, value: int) -> dict:
            return {
                "assumption_key": key,
                "bill_no": bill_no,
                "bill_name": f"선례 {bill_no}",
                "value": value,
                "unit": "원" if key == "committee_allowance_unit" else "명",
                "matched_by_rag": True,
                "source_context": "공식 비용추계서의 선례 근거",
                "structural_score": 0.8,
            }

        ranked = {
            "meeting_count": [
                candidate("committee_meeting_count", "2210001", 4),
                candidate("committee_meeting_count", "2210004", 4),
            ],
            "paid_members": [candidate("committee_paid_member_count", "2210002", 10)],
            "allowance_won": [candidate("committee_allowance_unit", "2210003", 200_000)],
        }
        llm_mock.return_value = {
            "meeting_count": {
                "bill_nos": ["2210001", "2210004", "2299999"],
                "reason": "기능이 유사함",
            },
            "paid_members": {"bill_nos": ["2210002"], "reason": "구성이 유사함"},
            "allowance_won": {"bill_nos": ["2210003"], "reason": "같은 연도 지침"},
        }
        selected, _reasons, diagnostics = _select_variable_evidence_with_llm(
            group={"entity": "정책심의위원회"},
            article_text="장관 소속으로 정책심의위원회를 둔다.",
            total_members=15,
            propose_date="2025-01-01",
            ranked_by_variable=ranked,
        )
        self.assertEqual(selected["meeting_count"], ["2210001", "2210004"])
        self.assertIn("meeting_count:2299999", diagnostics["rejected"])

    def test_explicit_amendment_recovers_optional_committee_article(self) -> None:
        text = """
        정책기본법 일부를 다음\n과 같이 개정한다.
        제62조의7을 다음과 같이 신설한다.
        제62조의7(보호심의위원회) ① 위원회는 신고자 보호에 관한 사항을
        심의하기 위하여 보호심의위원회를 둘 수 있다.
        ② 보호심의위원회는 위원장 1명을 포함하여 7명의 위원으로 구성한다.
        부 칙
        """
        articles = _extract_explicit_amendment_articles(text)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["no"], "제62조의7(보호심의위원회)")
        groups = _group_committee_articles(articles)
        self.assertEqual([group["entity"] for group in groups], ["보호심의위원회"])

    def test_document_frequency_and_existing_delta_are_deterministic(self) -> None:
        self.assertEqual(_meeting_count_from_document("분기별 1회 개최"), (4, "분기별1회"))
        self.assertEqual(_member_delta_from_document("민간위원을 10명에서 18명으로 증원"), (8, "민간위원을10명에서18명으로"))

    def test_allowance_uses_source_prose_to_reject_decimal_shift(self) -> None:
        candidate = {"value": 4_000_000, "unit": "원", "source_text": "회의당 수당은 총 40만원으로 지급"}
        self.assertEqual(_normalise_allowance(candidate), 400_000)

    def test_explicit_appointee_count_is_used_before_peer_prior(self) -> None:
        value, _matched, exact = _paid_members_from_document(
            "위원회 소속 공무원 1명과 위원장이 위촉하는 사람 5명으로 구성한다."
        )
        self.assertEqual(value, 5)
        self.assertTrue(exact)

    def test_peer_prior_prefers_mode_and_uses_median_without_consensus(self) -> None:
        self.assertEqual(_mode_or_median([2, 2, 3, 4]), 2)
        self.assertEqual(_mode_or_median([1, 3, 5]), 3)
        self.assertEqual(_representative_value([2, 2, 4, 4]), (3.0, "median"))
        self.assertEqual(
            _representative_value([2, 2, 3, 4, 5, 6]),
            (3.5, "median"),
        )
        self.assertEqual(
            _representative_value([2, 2, 2, 4, 6]),
            (2, "clear_mode"),
        )

    def test_formula_text_is_normalised_into_auditable_families(self) -> None:
        self.assertEqual(
            _formula_family("민간위원 수 × 회의 횟수 × 회의참석수당 단가"),
            "meeting_allowance",
        )
        self.assertEqual(
            _formula_family("위원 수 × 회의 횟수 × 회의참석 및 안건검토수당"),
            "meeting_and_review_allowance",
        )

    def test_recompute_does_not_overwrite_untouched_verified_package(self) -> None:
        result = {
            "channel": "committee",
            "committees": [{
                "id": "verified-1",
                "status": "computed",
                "calculation_mode": "verified_package",
                "annual_amount_thousand": 3_707_739,
                "total_amount_thousand": 3_707_739,
                "variables": {
                    "meeting_count": {"value": 4, "confirmed": False},
                    "paid_members": {"value": 10, "confirmed": False},
                    "allowance_won": {"value": 200_000, "confirmed": False},
                },
                "out_of_scope": [],
            }],
        }
        updated = recompute_committee_result(copy.deepcopy(result), [])
        committee = updated["committees"][0]
        self.assertEqual(committee["annual_amount_thousand"], 3_707_739)
        self.assertEqual(committee["total_amount_thousand"], 3_707_739)
        self.assertEqual(committee["calculation_mode"], "verified_package")
        self.assertEqual(
            _formula_family("전체회의 연간 비용 + 분과위원회 연간 비용"),
            "main_and_subcommittee",
        )
        self.assertEqual(
            _formula_family("시·도 위원회 수 × 민간위원 수 × 회의 횟수 × 회의수당"),
            "multi_body_meeting_allowance",
        )

    @patch("backend.committee_channel._gemini_raw_json")
    def test_llm_formula_selection_is_restricted_to_grounded_candidates(self, llm_mock) -> None:
        candidates = [
            {
                "candidate_id": "base",
                "bill_no": "2210001",
                "bill_name": "기본위원회법안",
                "item_name": "위원회 회의수당",
                "formula_text": "위원 수 × 회의 횟수 × 참석수당",
                "family": "meeting_allowance",
                "family_label": "회의참석수당",
                "supported": True,
                "similarity": 0.8,
            },
            {
                "candidate_id": "review",
                "bill_no": "2210002",
                "bill_name": "심사위원회법안",
                "item_name": "심사위원회 회의비",
                "formula_text": "위원 수 × 회의 횟수 × 회의참석 및 안건검토수당",
                "family": "meeting_and_review_allowance",
                "family_label": "회의참석·안건검토수당",
                "supported": True,
                "similarity": 0.9,
            },
        ]
        llm_mock.return_value = {
            "candidate_id": "review",
            "confidence": 0.87,
            "reason": "안건 심사 기능과 수당 구성이 유사함",
        }
        selected = _select_formula_with_llm(
            group={"entity": "정책심사위원회"},
            article_text="정책 안건을 사전에 검토하고 심의한다.",
            change_type="new",
            candidates=candidates,
        )
        self.assertEqual(selected["family"], "meeting_and_review_allowance")
        self.assertEqual(selected["source"]["bill_no"], "2210002")
        self.assertEqual(selected["method"], "llm_formula_rerank_plus_allowlist_grounding")

    def test_paid_member_prior_uses_median_of_target_normalised_ratios(self) -> None:
        candidates = [
            {
                **_tag_candidate(
                    "committee_paid_member_count",
                    value,
                    bill_no,
                    f"총 {total}명 중 위촉위원 {value}명",
                    "명",
                ),
                "candidate_total_members": total,
            }
            for value, total, bill_no in (
                (4, 10, "2210001"),
                (10, 20, "2210002"),
                (15, 30, "2210003"),
            )
        ]
        value, basis, evidence = _suggest_from_tag(
            "paid_members",
            candidates,
            total_members=20,
        )
        self.assertEqual(value, 10)
        self.assertIn("중앙값", basis)
        self.assertEqual(len(evidence), 3)

    def test_allowance_evidence_must_match_the_selected_formula(self) -> None:
        attendance_only = {
            **_tag_candidate(
                "committee_allowance_unit",
                200_000,
                "2210001",
                "회의 참석수당은 1인당 20만원",
                "원",
            ),
            "matched_by_rag": True,
            "rag_similarity": 0.8,
        }
        with_review = {
            **_tag_candidate(
                "committee_allowance_unit",
                300_000,
                "2210002",
                "회의참석 사례금은 안건 검토비 등을 포함하여 1인당 30만원",
                "원",
            ),
            "matched_by_rag": True,
            "rag_similarity": 0.9,
        }
        simple_value, _basis, simple_evidence = _suggest_from_tag(
            "allowance_won",
            [with_review, attendance_only],
            formula_family="meeting_allowance",
            require_rag_match=True,
        )
        review_value, _basis, review_evidence = _suggest_from_tag(
            "allowance_won",
            [with_review, attendance_only],
            formula_family="meeting_and_review_allowance",
            require_rag_match=True,
        )
        self.assertEqual(simple_value, 200_000)
        self.assertEqual([row["bill_no"] for row in simple_evidence], ["2210001"])
        self.assertEqual(review_value, 300_000)
        self.assertEqual([row["bill_no"] for row in review_evidence], ["2210002"])

    def test_korean_retrieval_is_robust_to_pdf_spacing(self) -> None:
        query = "국가인공지능데이터센터진흥위원회의설치및구성"
        same_subject = "국가 인공지능 데이터센터 진흥 전문위원회 설치와 운영"
        generic_other = "화장품 안전 심의위원회 설치와 운영"
        self.assertGreater(
            _token_overlap(query, same_subject),
            _token_overlap(query, generic_other),
        )

    @patch("backend.committee_channel._committee_documents_by_bill")
    def test_missing_tag_values_are_recovered_from_all_rag_cases(self, documents_mock) -> None:
        documents_mock.return_value = {
            "2210001": "민간위원은 6명으로 하고 회의는 연 3회 개최하며 참석수당 단가는 20만원으로 한다."
        }
        rows = _rag_case_assumption_candidates([{
            "bill_no": "2210001", "bill_name": "유사위원회법안", "similarity": 0.8,
        }])
        values = {row["assumption_key"]: row["value"] for row in rows}
        self.assertEqual(values["committee_meeting_count"], 3)
        self.assertEqual(values["committee_paid_member_count"], 6)
        self.assertEqual(values["committee_allowance_unit"], 200_000)

    @patch("backend.committee_channel._committee_documents_by_bill")
    def test_recovered_operands_bind_to_the_nearest_target_committee(self, documents_mock) -> None:
        documents_mock.return_value = {
            "2210002": (
                "유사한 기존 위원회는 위원장을 포함하여 25명 이내의 위원으로 구성된다. "
                "제안된 위원회는 연 2회 개최한다. "
                "위원회 정원을 15명으로 하며, 수당 지급의 대상이 되는 위촉 위원은 10명으로 가정한다. "
                "(회의 수당) 기획재정부의 해당 연도 세부지침을 준용하여 1회 20만원으로 한다."
            )
        }
        rows = _rag_case_assumption_candidates([{
            "bill_no": "2210002", "bill_name": "같은 기능의 위원회법안", "similarity": 0.9,
        }])
        values = {row["assumption_key"]: row for row in rows}
        self.assertEqual(values["committee_meeting_count"]["value"], 2)
        self.assertEqual(values["committee_paid_member_count"]["value"], 10)
        self.assertEqual(values["committee_paid_member_count"]["candidate_total_members"], 15)
        self.assertEqual(values["committee_allowance_unit"]["value"], 200_000)

    @patch("backend.committee_channel._hybrid_rag_search")
    @patch("backend.committee_channel.find_assumption_candidates")
    def test_new_committee_calculates_preview_but_requires_tag_confirmation(
        self,
        assumption_mock,
        rag_mock,
    ) -> None:
        rag_mock.return_value = [{
            "bill_no": "2210001", "bill_name": "유사의안", "content": "위원회 수당", "similarity": 0.8,
        }]
        assumption_mock.return_value = [
            _tag_candidate("committee_allowance_unit", 200_000, "2210001", "회의수당 20만원", "원"),
            _tag_candidate("committee_allowance_unit", 300_000, "2210002", "총 30만원", "원"),
            _tag_candidate("committee_allowance_unit", 300_000, "2210003", "총 30만원", "원"),
        ]
        group = _group_committee_articles(self.articles)[0]
        committee = _build_committee(
            group,
            bill_name="정책기본법안",
            bill_no="2299999",
            doc_type="제정안",
            index=1,
        )
        self.assertEqual(committee["variables"]["meeting_count"]["value"], 4)
        self.assertEqual(committee["variables"]["paid_members"]["value"], 8)
        # The variable-specific closest official case leads; the value still
        # remains unconfirmed until a user accepts it.
        self.assertEqual(committee["variables"]["allowance_won"]["value"], 200_000)
        self.assertEqual(committee["annual_amount_thousand"], 6_400)
        self.assertEqual(committee["total_amount_thousand"], 32_000)
        self.assertEqual(committee["status"], "review_required")
        assumption_mock.assert_called_once()
        self.assertEqual(assumption_mock.call_args.kwargs["exclude_bill_nos"], {"2299999"})

        result = {"channel": "committee", "committees": [committee]}
        inputs = [
            {"committeeId": committee["id"], "variable": key, "value": variable["value"]}
            for key, variable in committee["variables"].items()
            if variable["value"] is not None
        ]
        recomputed = recompute_committee_result(copy.deepcopy(result), inputs)
        self.assertEqual(recomputed["committees"][0]["status"], "computed")
        self.assertEqual(recomputed["summary"]["computed"], 1)

    def test_optional_incumbent_baseline_recalculates_net_paid_members(self) -> None:
        committee = {
            "id": "committee-1",
            "name": "보수위원회",
            "articles": [{"no": "제3조", "text": "위원회를 둔다."}],
            "variables": {
                "meeting_count": {"value": 4, "confirmed": True},
                "paid_members": {"value": 18, "confirmed": True},
                "incumbent_paid_members": {
                    "value": None,
                    "confirmed": False,
                    "blocking": False,
                },
                "allowance_won": {"value": 350_000, "confirmed": True},
            },
        }
        result = {"channel": "committee", "committees": [committee]}
        recomputed = recompute_committee_result(
            result,
            [
                {
                    "committeeId": "committee-1",
                    "variable": "incumbent_paid_members",
                    "value": 10,
                }
            ],
        )
        row = recomputed["committees"][0]
        self.assertEqual(row["paid_member_adjustment"]["net_paid_members"], 8)
        self.assertEqual(row["annual_amount_thousand"], 11_200)
        self.assertEqual(row["total_amount_thousand"], 56_000)

    @patch("backend.committee_channel._hybrid_rag_search", return_value=[])
    @patch("backend.committee_channel.find_assumption_candidates", return_value=[])
    def test_existing_committee_without_current_baseline_is_blocked(self, *_mocks) -> None:
        articles = copy.deepcopy(self.articles)
        for article in articles:
            article["change_type"] = "개정"
        group = _group_committee_articles(articles)[0]
        committee = _build_committee(
            group,
            bill_name="정책기본법 일부개정법안",
            bill_no="2299998",
            doc_type="일부개정안",
            index=1,
        )
        self.assertIsNone(committee["variables"]["paid_members"]["value"])
        self.assertEqual(committee["status"], "blocked_missing_variables")

    @patch("backend.committee_channel._hybrid_rag_search", return_value=[])
    @patch("backend.committee_channel.find_assumption_candidates", return_value=[])
    def test_secretariat_cost_is_explicitly_out_of_scope(self, *_mocks) -> None:
        articles = copy.deepcopy(self.articles)
        articles.append({
            "no": "제십삼조(사무국)",
            "text": "위원회의 사무를 처리하기 위하여 사무국과 지원 5명을 둔다.",
            "change_type": "신설",
        })
        group = _group_committee_articles(articles)[0]
        committee = _build_committee(
            group, bill_name="정책기본법안", bill_no=None, doc_type="제정안", index=1,
        )
        self.assertIn("사무처·사무국 및 인력", committee["out_of_scope"])


if __name__ == "__main__":
    unittest.main()
