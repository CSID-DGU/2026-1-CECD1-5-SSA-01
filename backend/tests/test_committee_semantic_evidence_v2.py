import unittest

from backend.legacy.scripts.build_committee_semantic_evidence_v2 import (
    _guideline_price,
    _meeting_actual,
)


class CommitteeSemanticEvidenceV2Tests(unittest.TestCase):
    def test_explicit_comparator_actual_recovers_subject(self) -> None:
        atom = {
            "profile_key": "P",
            "derivation_type": "reported_actual",
            "normalized_value": 4,
            "source_text": "한국가스공사의 배관시설이용심의위원회의 회의 개최 실적(연 4회)",
        }
        subject, observation = _meeting_actual(
            atom,
            {"normalized_name": "가스배관위원회"},
        )
        self.assertEqual(subject["normalized_name"], "배관시설이용심의위원회")
        self.assertEqual(observation["normalized_value"], 4)
        self.assertEqual(observation["transfer_policy"], "same_subject_only")

    def test_recent_modes_become_one_explicit_total(self) -> None:
        atom = {
            "profile_key": "P",
            "derivation_type": "direct_statement",
            "normalized_value": 12,
            "source_text": (
                "통계자료제공심의회의 최근 3년간 회의 개최횟수는 "
                "대면 4회·서면 12회 등 총 16회 개최되었음"
            ),
        }
        _, observation = _meeting_actual(
            atom,
            {"normalized_name": "통계간행물선정심의회"},
        )
        self.assertEqual(observation["normalized_value"], 16)

    def test_plain_assumption_is_not_promoted_to_actual(self) -> None:
        atom = {
            "derivation_type": "assumption",
            "source_text": "위원회는 연간 4회 개최하는 것으로 가정",
        }
        self.assertIsNone(_meeting_actual(atom, {"normalized_name": "정책위원회"}))

    def test_guideline_price_has_per_person_scope(self) -> None:
        atom = {
            "normalized_value": 250000,
            "source_text": (
                "2024년도 예산 및 기금운용계획 집행지침을 준용하여 "
                "회의수당을 1인당 1회 25만원"
            ),
        }
        _, observation = _guideline_price(atom)
        self.assertEqual(observation["measurement_scope"], "per_person_per_meeting")
        self.assertEqual(observation["basis_year"], 2024)


if __name__ == "__main__":
    unittest.main()
