"""Court-upgrade comparables and target-only staffing, with source dates.

The 2025 salary/rate table is taken from the earlier Goyang District Court
estimate (2212273), not independently from the Supreme Court's raw submission.
Anyang's net staffing and start date are answer-derived and never reusable.
"""
from __future__ import annotations

from backend.erce.reviewed_variable_rows import evidence_row


def court_organization_rows() -> list[dict]:
    prior = dict(
        source_bill_no="2212273", available_at="2025-09-12",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2212273/cost_estimate.pdf",
        agency="대법원", policy_domain="법원조직",
        scope="기존 지원의 지방법원 승격에 따른 순증 법원공무원",
        service_function="법원공무원 인건비·기본경비·자산취득비",
        reuse_policy="comparable", requires_applicability_note=True,
        obtained_from="earlier_cost_estimate", reviewed_at="2026-09-28",
        limitation="대법원 원자료·경제전망 원문은 독립 확인하지 않음. 순증 인원과 청사·자산 집행시점은 새 법원별로 별도 산정",
    )
    answer = dict(
        source_bill_no="2213969", available_at="2025-11-12",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2213969/cost_estimate.pdf",
        agency="대법원", policy_domain="법원조직",
        scope="안양지원의 안양지방법원 승격 및 광명시 관할 추가",
        service_function="안양지방법원 순증 법원공무원",
        reuse_policy="target_only", obtained_from="reviewed_answer",
        reviewed_at="2026-09-28",
        limitation="정답 추계서의 대상별 가정. 다른 법원 신설·승격 의안에 전용 금지",
    )
    return [
        evidence_row(
            evidence_key="2212273:court_salary_by_grade:2025",
            variable_key="salary_by_grade",
            value={"3급": 134_897_659, "4급": 122_008_949,
                   "5급": 100_863_123, "6급": 83_431_626,
                   "7급": 81_864_430, "8급": 52_218_181,
                   "9급": 42_271_410},
            unit="KRW/person/year", variable_role="court_salary_comparable",
            allowed_routes=["personnel_grade"], price_year=2025,
            source_ref="의안 2212273 추계서 25D4478 PDF p.6, 법원 2025년 예산 기준 직급별 연봉",
            **prior),
        evidence_row(
            evidence_key="2212273:court_wage_growth:2026-2030",
            variable_key="growth_rates_by_year",
            value={str(year): .024 for year in range(2026, 2031)},
            unit="ratio/year", variable_role="salary_growth_assumption",
            allowed_routes=["personnel_grade"], value_years=list(range(2026, 2031)),
            source_ref="의안 2212273 추계서 25D4478 PDF p.4, 2025.3.31 경제전망 인용",
            **prior),
        evidence_row(
            evidence_key="2212273:court_salary_base_year:2025",
            variable_key="base_year", value=2025, unit="year",
            variable_role="salary_price_base_year", allowed_routes=["personnel_grade"],
            source_ref="의안 2212273 추계서 25D4478 PDF p.6, 법원 2025년 예산 기준",
            **prior),
        evidence_row(
            evidence_key="2212273:court_employer_rate:2026-2030",
            variable_key="employer_contribution_rate",
            value=[.13066, .13130, .13194, .13286, .13380],
            unit="ratio/year", variable_role="employer_rate_forecast",
            allowed_routes=["personnel_employer_contribution"],
            value_years=list(range(2026, 2031)),
            source_ref="의안 2212273 추계서 25D4478 PDF p.4, 기관부담 요율 전망 인용",
            **prior),
        evidence_row(
            evidence_key="2212273:court_basic_expense_ratio:2025",
            variable_key="basic_expense_ratio", value=.0647, unit="ratio",
            variable_role="court_basic_expense_comparable",
            allowed_routes=["personnel_basic_expense"],
            source_ref="의안 2212273 추계서 25D4478 PDF p.7, 사법운영 기본경비/보수 6.47%",
            **prior),
        evidence_row(
            evidence_key="2212273:asset_price_per_person:2026",
            variable_key="asset_unit_price_per_person", value=4_981_000,
            unit="KRW/person", variable_role="government_asset_price_comparable",
            allowed_routes=["personnel_asset"], price_year=2026,
            source_ref="의안 2212273 추계서 25D4478 PDF p.4, 2026년 정부기관 1인당 자산취득비 전망 인용",
            **prior),
        evidence_row(
            evidence_key="2213969:anyang_net_staff_by_grade:2026",
            variable_key="headcount_by_grade",
            value={"4급": 1, "5급": 1, "6급": 9, "7급": 2, "8급": 15},
            unit="person/grade", variable_role="target_net_staff",
            allowed_routes=["personnel_grade"],
            source_ref="의안 2213969 추계서 25D5913 PDF p.6, 안양지방법원 순증 28명",
            **answer),
        evidence_row(
            evidence_key="2213969:anyang_first_year_fraction:2026",
            variable_key="first_year_fraction", value=10/12, unit="ratio",
            variable_role="target_start_assumption", allowed_routes=["personnel_grade"],
            value_years=list(range(2026, 2031)),
            source_ref="의안 2213969 추계서 25D5913 PDF p.5~7, 2026.3.1 시행 가정",
            **answer),
    ]
