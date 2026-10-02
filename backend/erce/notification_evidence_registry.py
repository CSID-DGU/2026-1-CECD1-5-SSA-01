"""Notification assumptions, never a substitute for target case-volume evidence."""
from __future__ import annotations

from typing import Any


NOTIFICATION_BENCHMARKS = ({
    "key": "intimate_violence_notification_2025_10_24",
    "agency": "대법원",
    "policy_domain": "친밀관계폭력",
    "available_at": "2025-10-24",
    "source_bill_no": "2212780",
    "price_years": (2027, 2028, 2029, 2030, 2031),
    "service_function": "임시조치 결정의 우편송달",
    "target_population": "기존 가정폭력 제외, 새로 포함되는 교제폭력 사건",
    "scale_basis": "가정폭력 임시조치 시행비율 2021~2024년 평균; 사건당 통지 평균",
    "source_ref": "의안 2212780, 25D4901, 비용추계서 PDF p.5~6",
    "inputs": {
        "action_rate": {"value": 0.226, "unit": "ratio"},
        "notices_per_case": {"value": 9, "unit": "notification/case"},
        "notice_unit_price": {
            "value": [5493, 5603, 5715, 5830, 5946], "unit": "KRW/notification",
        },
    },
    "price_provenance": (
        "대법원 제공 2025년 적용액 5,280원 및 NABO 2025.4 전망 적용 표. "
        "공식 요금표 웹검증 전이며 이 레지스트리에서는 선례 적용액으로 취급"
    ),
},)


def notification_formula_inputs(
    *, agency: str, policy_domain: str, cutoff_date: str,
    start_year: int, years: int, target_bill_no: str = "",
) -> tuple[str, dict[str, dict[str, Any]]]:
    matching = [row for row in NOTIFICATION_BENCHMARKS
                if row["agency"] == agency and row["policy_domain"] == policy_domain
                and row["available_at"] <= cutoff_date
                and row["source_bill_no"] != target_bill_no
                and tuple(range(start_year, start_year + years)) == row["price_years"]]
    if not matching:
        raise KeyError("no matching notification benchmark for target years")
    row = max(matching, key=lambda item: item["available_at"])
    return row["key"], {
        key: {**value, "source_ref": row["source_ref"]}
        for key, value in row["inputs"].items()
    }
