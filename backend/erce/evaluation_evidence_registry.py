"""Domain-specific evaluation assumptions, with source and temporal gates."""
from __future__ import annotations

from typing import Any


EVALUATION_BENCHMARKS: tuple[dict[str, Any], ...] = ({
    "key": "election_poll_quality_evaluation_2026_04_09",
    "agency": "중앙선거관리위원회",
    "policy_domain": "선거여론조사",
    "available_at": "2026-04-09",
    "source_bill_no": "2216710",
    "study_price_year": 2028,
    "source_ref": (
        "의안 2216710, 26D0795, 비용추계서 p.2~3; 개인정보보호위원회 "
        "공공·민간 개인정보 보호체계 평가사업 준용. 중앙 민간위원 30명, "
        "17개 시도 각 15명, 연 12회 가정. 회의수당 25만원 기간 중 동결. "
        "지표개발 용역 2024년 예산 5천만원을 NABO 2026.3 소비자물가 전망으로 "
        "2028년 가격 조정한 공식 적용액 5,400만원. 시도 위원 수·횟수는 선례 가정"
    ),
    "inputs": {
        "committee_components": {
            "value": [
                {"paid_members": 30, "meetings_per_instance": 12,
                 "instances_per_year": 1, "meeting_unit_price": 250_000},
                {"paid_members": 15, "meetings_per_instance": 12,
                 "instances_per_year": 17, "meeting_unit_price": 250_000},
            ],
            "unit": "component_bundle",
        },
        "initial_study_cost": {"value": 54_000_000, "unit": "KRW/initial_study"},
    },
},)


def evaluation_formula_inputs(
    *, agency: str, policy_domain: str, cutoff_date: str,
    start_year: int, target_bill_no: str = "",
) -> tuple[str, dict[str, dict[str, Any]]]:
    matches = [row for row in EVALUATION_BENCHMARKS
               if row["agency"] == agency and row["policy_domain"] == policy_domain
               and row["available_at"] <= cutoff_date
               and row["source_bill_no"] != target_bill_no
               and row["study_price_year"] == start_year]
    if not matches:
        raise KeyError("no matching evaluation benchmark; study price needs target-year evidence")
    row = max(matches, key=lambda candidate: candidate["available_at"])
    return row["key"], {
        key: {**value, "source_ref": row["source_ref"]}
        for key, value in row["inputs"].items()
    }


__all__ = ["EVALUATION_BENCHMARKS", "evaluation_formula_inputs"]
