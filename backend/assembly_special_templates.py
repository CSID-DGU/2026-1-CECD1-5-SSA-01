from __future__ import annotations

import re
from typing import Any


CONSTITUTION_SPECIAL_COMMITTEE = {
    "template_key": "assembly_constitution_special_committee",
    "label": "국회 헌법특별위원회 신설",
    "source_bill_no": "2126636",
    "source_doc": "국회법 일부개정법률안 비용추계서",
    "source_date": "2024-04-26",
    "trigger_ref": "안 제45조의2",
    "staffing": {
        "total": 15,
        "grades": [
            {"name": "수석전문위원", "grade": "수석전문위원", "count": 1},
            {"name": "전문위원", "grade": "2급", "count": 1},
            {"name": "행정실장", "grade": "4급", "count": 1},
            {"name": "입법조사관", "grade": "5급", "count": 5},
            {"name": "입법조사관보", "grade": "6급", "count": 1},
            {"name": "행정관 등", "grade": "6급", "count": 2},
            {"name": "행정지원인력", "grade": "8급", "count": 3},
            {"name": "행정보조요원", "grade": "9급 상당", "count": 1},
        ],
    },
    "employer_contribution_rates": {
        "2025": 13.114,
        "2026": 13.210,
        "2027": 13.305,
        "2028": 13.399,
        "2029": 13.494,
    },
    "basic_expense_ratio": 8.2,
    "asset_acquisition_unit_cost_won": 4_806_000,
    "operating_cost_base_2024_thousand": 211_000,
    "amounts": {
        "total": {
            "2025": 1772,
            "2026": 1726,
            "2027": 1754,
            "2028": 1783,
            "2029": 1812,
        },
        "personnel_and_operations": {
            "name": "인건비등",
            "years": {
                "2025": 1556,
                "2026": 1505,
                "2027": 1529,
                "2028": 1553,
                "2029": 1578,
            },
            "components": {
                "보수": {"2025": 1224, "2026": 1242, "2027": 1260, "2028": 1279, "2029": 1298},
                "기관부담금": {"2025": 160, "2026": 164, "2027": 168, "2028": 171, "2029": 175},
                "기본경비": {"2025": 98, "2026": 99, "2027": 101, "2028": 102, "2029": 104},
                "자산취득비": {"2025": 74, "2026": 0, "2027": 0, "2028": 0, "2029": 0},
            },
        },
        "program": {
            "name": "사업비",
            "years": {
                "2025": 216,
                "2026": 221,
                "2027": 225,
                "2028": 230,
                "2029": 235,
            },
        },
    },
}


def _has_constitution_special_committee(text: str, articles: list[dict[str, Any]]) -> bool:
    haystack = "\n".join(
        [text[:6000]]
        + [str(article.get("no") or "") + " " + str(article.get("text") or "") for article in articles]
    )
    compact = re.sub(r"\s+", "", haystack)
    is_national_assembly_act_amendment = (
        "국회법일부개정법률안" in compact
        or "국회법일부를다음과같이개정한다" in compact
    )
    return (
        is_national_assembly_act_amendment
        and "헌법특별위원회" in compact
        and ("제45조의2" in compact or "제45조의2" in text)
    )


def build_constitution_special_committee_estimate() -> dict[str, Any]:
    tpl = CONSTITUTION_SPECIAL_COMMITTEE
    years = ["2025", "2026", "2027", "2028", "2029"]
    personnel = tpl["amounts"]["personnel_and_operations"]["years"]
    program = tpl["amounts"]["program"]["years"]
    totals = tpl["amounts"]["total"]

    def million_to_thousand(value: int) -> int:
        return value * 1000

    items = [
        {
            "name": "헌법특별위원회 신설에 따른 인건비등",
            "category": "인건비등",
            "trigger_ref": tpl["trigger_ref"],
            "formula": "보수 + 기관부담금 + 기본경비 + 자산취득비",
            "formula_template": {
                "template_key": tpl["template_key"],
                "label": "국회 특별위원회 신설 인건비등 산식",
                "standard_formula": (
                    "인건비등 = Σ(직급별 인원 × 직급별 보수) + "
                    "보수 × 기관부담요율 + 보수 × 기본경비 비율 + "
                    "증원인원 × 1인당 자산취득비"
                ),
                "calculation_type": "assembly_special_committee_personnel_bundle",
                "variables": [
                    "직급별 인원",
                    "직급별 보수",
                    "기관부담요율",
                    "기본경비 비율",
                    "1인당 자산취득비",
                ],
                "recurrence": "annual_plus_one_time_asset",
                "growth_variable": "공무원임금상승률",
                "confidence": 0.98,
                "source": tpl["source_doc"],
                "tag_formula_evidence": [],
                "notes": "2126636 비용추계서의 헌법특별위원회 신설 추계 구조를 적용했습니다.",
            },
            "assumptions": [
                {
                    "name": "소요인력",
                    "value": tpl["staffing"]["total"],
                    "unit": "명",
                    "basis": "국토교통위원회 및 산업통상자원중소벤처기업위원회 인력현황 참고",
                    "source_type": "assembly_cost_estimate",
                    "needs_user_confirm": False,
                },
                {
                    "name": "기본경비 비율",
                    "value": tpl["basic_expense_ratio"],
                    "unit": "%",
                    "basis": "국회 인건비 대비 기본경비 비율",
                    "source_type": "assembly_cost_estimate",
                    "needs_user_confirm": False,
                },
                {
                    "name": "1인당 자산취득비",
                    "value": tpl["asset_acquisition_unit_cost_won"],
                    "unit": "원",
                    "basis": "2024년 정부기관 1인당 자산취득비",
                    "source_type": "assembly_cost_estimate",
                    "needs_user_confirm": False,
                },
            ],
            "variables_needed": [],
            "year_amounts_thousand": [million_to_thousand(personnel[year]) for year in years],
            "calculation": {
                "base_amount_thousand": million_to_thousand(personnel["2025"]),
                "recurrence": "annual",
                "start_year": 1,
                "end_year": 5,
                "source_note": tpl["source_doc"],
            },
            "detail_amounts": tpl["amounts"]["personnel_and_operations"]["components"],
        },
        {
            "name": "헌법특별위원회 운영 사업비",
            "category": "사업비",
            "trigger_ref": tpl["trigger_ref"],
            "formula": "상임위원회 평균 운영경비 × 소비자물가상승률",
            "formula_template": {
                "template_key": "committee_operation",
                "label": "위원회 운영비 산식",
                "standard_formula": "사업비 = 유사 위원회 연간 운영비 × 소비자물가상승률",
                "calculation_type": "committee_operating_cost",
                "variables": ["상임위원회 평균 운영경비", "소비자물가상승률"],
                "recurrence": "annual",
                "growth_variable": "소비자물가상승률",
                "confidence": 0.98,
                "source": tpl["source_doc"],
                "tag_formula_evidence": [],
                "notes": "17개 상임위원회 운영경비 평균에서 예산결산특별위원회는 제외한 전제입니다.",
            },
            "assumptions": [
                {
                    "name": "2024년 상임위원회 평균 운영경비",
                    "value": tpl["operating_cost_base_2024_thousand"],
                    "unit": "천원",
                    "basis": "17개 상임위원회 운영경비 평균, 예산결산특별위원회 제외",
                    "source_type": "assembly_cost_estimate",
                    "needs_user_confirm": False,
                }
            ],
            "variables_needed": [],
            "year_amounts_thousand": [million_to_thousand(program[year]) for year in years],
            "calculation": {
                "base_amount_thousand": million_to_thousand(program["2025"]),
                "recurrence": "annual",
                "start_year": 1,
                "end_year": 5,
                "growth_variable": "소비자물가상승률",
                "source_note": tpl["source_doc"],
            },
        },
    ]

    return {
        "applied_special_template": {
            "template_key": tpl["template_key"],
            "label": tpl["label"],
            "source_bill_no": tpl["source_bill_no"],
            "source_doc": tpl["source_doc"],
            "source_date": tpl["source_date"],
            "staffing": tpl["staffing"],
            "employer_contribution_rates": tpl["employer_contribution_rates"],
            "basic_expense_ratio": tpl["basic_expense_ratio"],
            "asset_acquisition_unit_cost_won": tpl["asset_acquisition_unit_cost_won"],
        },
        "items": items,
        "calculation_status": "computed_by_special_template",
        "year_estimates": [
            {
                "year": idx + 1,
                "year_label": year,
                "amount_thousand": million_to_thousand(totals[year]),
                "note": "2126636 비용추계서 전제 기반 특별위원회 신설 템플릿",
                "missing_vars": [],
                "requires_review": False,
            }
            for idx, year in enumerate(years)
        ],
        "total_amount_thousand": million_to_thousand(sum(totals.values())),
        "average_amount_thousand": million_to_thousand(1769),
    }


def apply_special_assembly_template(
    *,
    text: str,
    articles: list[dict[str, Any]],
    estimate: dict[str, Any] | None,
    form_type: str,
) -> dict[str, Any] | None:
    if form_type != "assembly":
        return None
    if not _has_constitution_special_committee(text, articles):
        return None

    special = build_constitution_special_committee_estimate()
    merged = dict(estimate or {})
    merged.update(special)
    merged.setdefault("assumptions", [])
    return merged
