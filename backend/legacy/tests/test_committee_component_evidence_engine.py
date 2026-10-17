import unittest

from unittest.mock import patch

from backend.legacy.committee.committee_component_evidence_engine import (
    _kind,
    _price_value,
    _subject_matches_profile,
    recommend,
)


class CommitteeComponentEvidenceEngineTests(unittest.TestCase):
    def test_whole_meeting_operating_cost_is_not_unit_price(self) -> None:
        atom = {
            "normalized_value": 3_000_000,
            "source_text": "회의당 운영비용은 민간위원 10명과 회의비 30만원으로 300만원이다.",
        }
        self.assertIsNone(_price_value(atom))

    def test_annual_operating_budget_is_not_unit_price(self) -> None:
        atom = {
            "normalized_value": 14_000_000,
            "source_text": "2023년도 행정기관위원회 현황의 연간 운영비 1,400만원",
        }
        self.assertIsNone(_price_value(atom))

    def test_scale_error_is_repaired_from_evidence_sentence(self) -> None:
        atom = {
            "normalized_value": 4_000_000,
            "source_text": "민간위원 수당단가는 1인당 1회 40만원으로 가정",
        }
        self.assertEqual(_price_value(atom), 400_000)

    def test_clear_per_person_allowance_is_kept(self) -> None:
        atom = {
            "normalized_value": 250_000,
            "source_text": "민간위원 1인당 회의참석수당은 1회당 25만원",
        }
        self.assertEqual(_price_value(atom), 250_000)

    def test_assumption_with_actual_words_is_not_reported_actual(self) -> None:
        atom = {
            "derivation_type": "assumption",
            "source_text": "기존 위원회 운영 현황을 고려하여 매월 연 12회로 가정",
        }
        self.assertEqual(_kind(atom), "weak_prior")

    def test_comparator_actual_does_not_match_target_profile(self) -> None:
        atom = {
            "profile_key": "P",
            "source_text": "통계자료제공심의회는 최근 3년간 연 16회 개최되었다.",
        }
        profile = {"P": {"normalized_name": "통계간행물선정심의회"}}
        with patch(
            "backend.legacy.committee.committee_component_evidence_engine._profile_index",
            return_value=profile,
        ):
            self.assertFalse(_subject_matches_profile(atom))

    def test_engine_never_emits_total(self) -> None:
        case = {
            "bill_no": "TEST",
            "bill_name": "정책위원회법안",
            "propose_date": "2026-01-01",
            "cutoff_date": "2026-01-01",
            "target_terms": ["정책위원회"],
            "target_passages": [
                "위원장 1명을 포함한 15명 이내의 정책위원회를 둔다. "
                "민간전문가가 전체 위원의 과반수가 되어야 한다."
            ],
        }
        rows = recommend(case)
        self.assertTrue(rows)
        self.assertIn("total_members_cap", {row.role for row in rows[0].target_operands})
        self.assertTrue(all(row.point_amount_won is None for row in rows))
        self.assertTrue(all(row.amount_range_won is None for row in rows))


if __name__ == "__main__":
    unittest.main()
