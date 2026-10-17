import unittest
from unittest.mock import patch

import backend.erce_web.committee_component_recommender as recommender
from backend.erce_web.committee_component_recommender import (
    StructuralCandidate,
    _bounded_governance_articles,
    _build_target,
    _instance_count,
    _recommend_target,
)


def _candidate(
    bill_no: str,
    *,
    paid: float = 10,
    meetings: float = 4,
    price: float = 250_000,
) -> StructuralCandidate:
    return StructuralCandidate(
        profile_key=f"P-{bill_no}",
        bill_no=bill_no,
        bill_name=f"선례 {bill_no}",
        committee_name=f"구조선례위원회{bill_no}",
        function_class="standing_strategy",
        total_members=20,
        paid_members=paid,
        annual_meetings=meetings,
        meeting_unit_price=price,
        committee_instances=1,
        parent_authority="국무총리",
        has_subcommittee=False,
        has_secretariat=False,
        available_date="2024-01-01",
        score=12,
        score_breakdown=(
            ("function", 3),
            ("member_scale", 3),
            ("institution_scope", 2),
            ("subcommittee", 1),
            ("secretariat", 1),
            ("formula_completeness", 3),
        ),
        source_texts=("민간위원 10명, 연 4회, 회당 25만원",),
    )


class CommitteeComponentRecommenderTests(unittest.TestCase):
    def test_unrelated_following_article_cannot_supply_meeting_frequency(self) -> None:
        articles = [
            {
                "no": "제10조(정책위원회)",
                "title": "정책위원회",
                "text": "정책을 심의하기 위하여 정책위원회를 둔다. 20명 이내로 구성한다.",
            },
            {
                "no": "제11조(실태조사)",
                "title": "실태조사",
                "text": "장관은 정책 실태를 연 1회 이상 조사한다.",
            },
        ]
        selected = _bounded_governance_articles(
            articles, anchor=0, name="정책위원회", other_names=["정책위원회"]
        )
        self.assertEqual(len(selected), 1)
        target = _build_target(
            "정책위원회",
            " ".join(str(row["text"]) for row in selected),
        )
        self.assertIsNone(target.meetings_exact)

    def test_contiguous_generic_governance_articles_are_retained(self) -> None:
        articles = [
            {
                "no": "제10조(정책위원회)",
                "title": "정책위원회",
                "text": "정책을 심의하기 위하여 정책위원회를 둔다.",
            },
            {
                "no": "제11조(위원회의 구성)",
                "title": "위원회의 구성",
                "text": "위원회는 20명 이내로 구성한다.",
            },
            {
                "no": "제12조(회의)",
                "title": "회의",
                "text": "위원회는 연 4회 회의를 개최한다.",
            },
            {
                "no": "제13조(실태조사)",
                "title": "실태조사",
                "text": "장관은 매년 실태를 조사한다.",
            },
        ]
        selected = _bounded_governance_articles(
            articles, anchor=0, name="정책위원회", other_names=["정책위원회"]
        )
        self.assertEqual(len(selected), 3)

    def test_strict_majority_becomes_legal_floor_not_exact_count(self) -> None:
        target = _build_target(
            "기념사업위원회",
            "위원장 1명을 포함한 15명 이내의 위원으로 구성한다. "
            "위원의 과반수를 경험이 풍부한 민간전문가로 한다.",
        )
        self.assertEqual(target.total_high, 15)
        self.assertEqual(target.paid_floor, 8)
        self.assertIsNone(target.paid_exact)

    def test_half_or_more_uses_ceiling_at_legal_upper_scenario(self) -> None:
        target = _build_target(
            "규제위원회",
            "위원장 1명을 포함한 20명 이상 25명 이내로 구성한다. "
            "민간위원의 수는 위원 수의 2분의 1 이상이어야 한다.",
        )
        self.assertEqual(target.total_high, 25)
        self.assertEqual(target.paid_floor, 13)

    def test_nonpublic_chair_is_exact_only_without_private_cohort(self) -> None:
        exact = _build_target(
            "건강심의위원회",
            "위원장은 공무원이 아닌 사람으로 한다. "
            "나머지 위원은 각 기관의 건강안전책임관으로 한다.",
        )
        self.assertEqual(exact.paid_exact, 1)

        lower_bound = _build_target(
            "기념위원회",
            "위원장은 위촉위원 중에서 호선한다. 위원장이 위촉하는 민간전문가를 둔다.",
        )
        self.assertIsNone(lower_bound.paid_exact)
        self.assertEqual(lower_bound.paid_floor, 1)

    def test_named_multi_institution_installation_is_counted(self) -> None:
        context = (
            "업무를 수행하기 위하여 국회ㆍ대법원ㆍ헌법재판소ㆍ"
            "중앙선거관리위원회 및 인사혁신처 소속으로 건강안전심의위원회를 둔다."
        )
        self.assertEqual(_instance_count("건강안전심의위원회", context), 5)

    def test_heavy_statutory_body_routes_to_organization_channel(self) -> None:
        target = _build_target(
            "독립위원회",
            "독립위원회를 둔다. 상임위원 3명을 두고 정무직으로 보한다. "
            "사무처에 사무처장과 필요한 직원을 둔다.",
        )
        self.assertTrue(target.heavy_organization)

    def test_ex_officio_political_appointee_is_not_committee_payroll(self) -> None:
        target = _build_target(
            "국가정책위원회",
            "위원은 대통령령으로 정하는 관계 중앙행정기관의 장 및 "
            "정무직공무원과 민간전문가 중 위촉하는 사람으로 구성한다.",
        )
        self.assertFalse(target.heavy_organization)

    def test_reference_to_parliamentary_standing_committee_is_not_payroll(self) -> None:
        target = _build_target(
            "돌봄정책위원회",
            "위원장 1명을 포함한 25명 이내의 위원으로 구성한다. "
            "추진실적은 국회 소관 상임위원회에 보고하여야 한다.",
        )
        self.assertFalse(target.heavy_organization)

    def test_missing_frequency_never_yields_point_amount(self) -> None:
        target = _build_target(
            "정책위원회",
            "정책을 심의하기 위하여 위원장 1명을 포함한 20명 이내의 정책위원회를 둔다.",
        )
        with patch.object(
            recommender,
            "_rank",
            return_value=[_candidate("A"), _candidate("B", paid=12)],
        ):
            result = _recommend_target({"bill_no": "T"}, target)
        self.assertEqual(result.decision, "needs_user_input")
        self.assertIsNone(result.point_amount_won)
        self.assertIsNone(result.amount_range_won)
        self.assertIn("연간 회의횟수", result.review_fields)

    def test_explicit_operands_can_yield_review_point(self) -> None:
        target = _build_target(
            "정책위원회",
            "정책위원회를 둔다. 위촉하는 사람 5명으로 구성하고 연 4회 회의를 개최한다.",
        )
        with patch.object(recommender, "_rank", return_value=[_candidate("A")]):
            result = _recommend_target({"bill_no": "T"}, target)
        self.assertEqual(result.decision, "component_recommendation")
        self.assertEqual(result.point_amount_won, 5_000_000)
        self.assertEqual(result.confidence, "review_only")

    def test_unstructured_ad_hoc_body_does_not_publish_range(self) -> None:
        target = _build_target(
            "위원회",
            "필요한 경우 민간전문가가 참여하는 협의체 또는 위원회를 구성ㆍ운영할 수 있다.",
        )
        with patch.object(recommender, "_rank", return_value=[_candidate("A")]):
            result = _recommend_target({"bill_no": "T"}, target)
        self.assertEqual(result.decision, "needs_user_input")
        self.assertIsNone(result.point_amount_won)
        self.assertIsNone(result.amount_range_won)

    def test_establishment_body_prefers_establishment_precedent_without_publishing_amount(self) -> None:
        case = {
            "bill_no": "2217531",
            "bill_name": "한국수산진흥공사법안",
            "propose_date": "2026-03-17",
            "cutoff_date": "2026-03-17",
            "source_pdf": (
                "backend/generated/committee_final_holdout_v2/2217531/package/"
                "2217531_의사국 의안과_의안원문.pdf"
            ),
            "target_terms": ["한국수산진흥공사설립위원회"],
        }
        result = recommender.recommend(case)[0]
        self.assertEqual(result.candidate_top5[0].bill_no, "2126319")
        self.assertEqual(result.candidate_top5[0].lifecycle, "establishment")
        self.assertNotEqual(result.candidate_top5[0].bill_no, case["bill_no"])
        self.assertEqual(result.decision, "needs_user_input")
        self.assertIsNone(result.point_amount_won)


if __name__ == "__main__":
    unittest.main()
