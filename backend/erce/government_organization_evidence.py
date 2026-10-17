"""Vice-minister creation evidence and NABO central-government forecasts.

All values were read from the reviewed answer 24D4379 (bill 2204756) after
its first run was frozen. The forecasts are NABO's November-2024 projections
quoted there, not independently re-read from the forecast publication.
Ministry-specific staff pay, office composition and basic-expense ratio are
Ministry-of-Environment observations: other ministries need their own values.
"""
from __future__ import annotations

from backend.erce.reviewed_variable_rows import evidence_row

CENTRAL_AGENCY_GROUP = "중앙행정기관"


def government_organization_rows() -> list[dict]:
    common = dict(
        source_bill_no="2204756", available_at="2024-12-23",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2204756/cost_estimate.pdf",
        policy_domain="정부조직", obtained_from="reviewed_answer",
        reviewed_at="2026-10-15", requires_applicability_note=True,
    )
    forecast = dict(
        common, agency=CENTRAL_AGENCY_GROUP, reuse_policy="comparable",
        scope="중앙행정기관 공무원 순증에 따른 인건비·자산취득비",
        service_function="정부기관 공무원 보수 전망·기관부담금·1인당 자산취득비",
        limitation="국회예산정책처 2024.11 전망을 24D4379에서 인용한 값. 이후 전망 개정 시 새 버전을 사용",
    )
    vice_office = dict(
        common, agency="환경부", reuse_policy="same_scope",
        scope="환경부 차관 1명 신설과 기존 1차관 비서실 구성 준용",
        service_function="차관 및 차관 비서실 인건비·기본경비",
    )
    return [
        evidence_row(
            evidence_key="nabo:central_wage_growth:2025-2029:v202411",
            variable_key="growth_rates_by_year",
            value={str(year): .019 for year in range(2025, 2030)},
            unit="ratio/year", variable_role="salary_growth_assumption",
            allowed_routes=["personnel_grade"], value_years=list(range(2025, 2030)),
            source_ref="의안 2204756 추계서 24D4379 PDF p.2 각주1, 공무원임금 평균상승률(2024.11 경제전망)",
            **forecast),
        evidence_row(
            evidence_key="nabo:central_salary_base_year:2024:v202411",
            variable_key="base_year", value=2024, unit="year",
            variable_role="salary_price_base_year", allowed_routes=["personnel_grade"],
            source_ref="의안 2204756 추계서 24D4379 PDF p.3 표2, 2024년 보수규정·환경부 예산 기준",
            **forecast),
        evidence_row(
            evidence_key="nabo:central_employer_rate:2025-2029:v202411",
            variable_key="employer_contribution_rate",
            value=[.13004, .13066, .13130, .13194, .13286],
            unit="ratio/year", variable_role="employer_rate_forecast",
            allowed_routes=["personnel_employer_contribution"],
            value_years=list(range(2025, 2030)),
            source_ref="의안 2204756 추계서 24D4379 PDF p.2 각주2, 공무원 인건비 기관부담금요율 전망(2024.11)",
            **forecast),
        evidence_row(
            evidence_key="nabo:central_asset_per_person:2025:v202411",
            variable_key="asset_unit_price_per_person", value=4_907_000,
            unit="KRW/person", variable_role="government_asset_price_forecast",
            allowed_routes=["personnel_asset"], price_year=2025,
            source_ref="의안 2204756 추계서 24D4379 PDF p.2 각주3, 정부기관 1인당 자산취득비 전망(2024.11)",
            **{**forecast, "limitation": forecast["limitation"]
               + ". 추계 첫해가 2025년이고 첫해에만 취득하는 경우에 한함"}),
        evidence_row(
            evidence_key="2204756:moe_vice_office_salary_by_grade:2024",
            variable_key="salary_by_grade",
            value={"차관": 156_795_000, "5급": 67_937_000,
                   "7급": 42_480_000, "별정직6급": 52_356_000},
            unit="KRW/person/year", variable_role="vice_minister_office_pay",
            allowed_routes=["personnel_grade"], price_year=2024,
            source_ref=("의안 2204756 추계서 24D4379 PDF p.3 표2. 차관=2024 정무직 연봉 143,235천+"
                        "직급보조비 11,400천·정액급식비 1,680천·가족수당 480천; 5·7급·별정직6급="
                        "2024 환경부 예산 평균 연봉액+수당"),
            limitation=("차관 보수는 정무직 공통이나 비서실 직급 보수는 환경부 평균연봉 기준. "
                        "다른 부처는 해당 부처 평균연봉으로 대체해야 함. 가족수당은 배우자 1인 가정"),
            **vice_office),
        evidence_row(
            evidence_key="2204756:moe_vice_office_headcount:convention",
            variable_key="headcount_by_grade",
            value={"차관": 1, "5급": 1, "7급": 2, "별정직6급": 1},
            unit="person/grade", variable_role="vice_minister_office_convention",
            allowed_routes=["personnel_grade"],
            source_ref="의안 2204756 추계서 24D4379 PDF p.2, 2차관 비서실을 환경부 1차관 비서실(비서관1·비서3) 구성 준용",
            limitation=("원문 명시값이 아닌 NABO 준용 가정. 같은 부처 차관 신설에만 그대로 사용하고, "
                        "다른 부처는 그 부처 기존 차관 비서실 구성을 확인해야 함. 사무공간은 유휴공간 가정"),
            **vice_office),
        evidence_row(
            evidence_key="2204756:moe_basic_expense_ratio:2024",
            variable_key="basic_expense_ratio", value=.21, unit="ratio",
            variable_role="ministry_basic_expense_ratio",
            allowed_routes=["personnel_basic_expense"], price_year=2024,
            source_ref="의안 2204756 추계서 24D4379 PDF p.4 각주4, 2024년 환경부 예산 인건비 대비 기본경비 21%",
            limitation="환경부 부처 평균. 분모는 보수+기관부담금(인건비 총액)",
            **{**vice_office, "scope": "환경부 공무원 순증에 따른 기본경비",
               "service_function": "환경부 인건비 대비 기본경비"}),
    ]
