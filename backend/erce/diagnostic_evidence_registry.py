"""Precedent diagnostic support amounts, not official national tariffs."""
from typing import Any


DIAGNOSTIC_BENCHMARKS = ({
    "key": "borderline_intelligence_diagnostic_2024_10_22",
    "agency": "보건복지부", "policy_domain": "경계선지능인",
    "available_at": "2024-10-22", "source_bill_no": "2203298",
    "service_function": "경계선지능 정밀검사비 지원",
    "target_population": "6~11세 아동",
    "scale_basis": "정답은 시도별 6~11세 인구의 1% 지원 가정; 법정 고정 비율 아님",
    "comparables": [
        {"agency": "대구교육청", "year": 2024, "recipients": 300, "unit_cost": 200000},
        {"agency": "인천교육청", "year": 2024, "recipients": 500, "unit_cost": 200000},
        {"agency": "전북교육청", "year": 2024, "recipients": 40, "unit_cost": 300000},
    ],
    "source_ref": "의안 2203298, 24C3255, 비용추계서 PDF p.7~8; 지방교육청 2024년 사업 준용",
    "inputs": {"test_unit_cost": {"value": 200000, "unit": "KRW/person"}},
},)


def diagnostic_formula_inputs(
    *, agency: str, policy_domain: str, cutoff_date: str, target_bill_no: str = "",
) -> tuple[str, dict[str, dict[str, Any]]]:
    rows = [row for row in DIAGNOSTIC_BENCHMARKS
            if row["agency"] == agency and row["policy_domain"] == policy_domain
            and row["available_at"] <= cutoff_date and row["source_bill_no"] != target_bill_no]
    if not rows:
        raise KeyError("no matching diagnostic support precedent")
    row = max(rows, key=lambda item: item["available_at"])
    return row["key"], {key: {**value, "source_ref": row["source_ref"]}
                        for key, value in row["inputs"].items()}
