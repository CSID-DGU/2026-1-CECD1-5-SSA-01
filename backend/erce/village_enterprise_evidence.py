"""Reviewed 2200039 answer assumptions; never available in its blind run."""
from backend.erce.reviewed_variable_rows import evidence_row


def village_enterprise_rows():
    common = dict(
        source_bill_no="2200039", available_at="2024-07-02",
        source_ref="의안 2200039 비용추계서(24D0282), PDF p.4~6",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200039/cost_estimate.pdf",
        agency="행정안전부", policy_domain="마을기업", reviewed_at="2026-09-28",
        obtained_from="reviewed_answer",
    )
    return [
        evidence_row(
            evidence_key="2200039:mois_plan_research_unit_cost:2021-2023",
            variable_key="plan_unit_cost", value=203_000_000, unit="KRW/plan",
            scope="행정안전부 5년 종합계획 수립 연구용역",
            service_function="기본계획 수립 연구용역", variable_role="unit_rate",
            reuse_policy="comparable", requires_applicability_note=True,
            allowed_routes=["research_plan"], source_class="precedent_assumption",
            sample_costs_won=[200_000_000, 360_000_000, 100_000_000, 150_000_000],
            sample_years=[2021, 2022, 2022, 2023], price_reference_year=2023,
            calculation_note="4건 평균 202.5백만원을 추계서에서 203백만원으로 반올림",
            limitation="2024-07-02 정답에서 처음 확인한 행안부 제출자료. 이 대상의 블라인드 입력 아님. 다른 계획에는 범위·규모 비교 필요",
            **common),
        evidence_row(
            evidence_key="2200039:plan_cpi_rates:2024-2030",
            variable_key="growth_rates_by_year",
            value={str(year): rate for year, rate in {
                2024:.026, 2025:.022, 2026:.022, 2027:.021,
                2028:.021, 2029:.021, 2030:.020,
            }.items()}, unit="ratio/year",
            scope="제2200039호 종합계획 2023년 가격의 2026년 환산",
            service_function="기본계획 수립 연구용역", variable_role="target_forecast_vintage",
            reuse_policy="target_only", allowed_routes=["research_plan"],
            limitation="정답 PDF의 2024년 4월 물가전망 인용표. 원 전망서 독립 확인 전 타 의안에 재사용 금지",
            **common),
        evidence_row(
            evidence_key="2200039:plan_base_year:2023", variable_key="base_year",
            value=2023, unit="year",
            scope="제2200039호 종합계획 연구용역 비교가격 기준연도",
            service_function="기본계획 수립 연구용역", variable_role="target_assumption",
            reuse_policy="target_only", allowed_routes=["research_plan"],
            limitation="4개 사례 가격의 기준을 2023년으로 통일하는 정답 추계 가정",
            **common),
        evidence_row(
            evidence_key="2200039:central_committee_components:2026-2030",
            variable_key="committee_components",
            value=[{"paid_members":14, "annual_meetings":4,
                    "meeting_unit_price":250_000}],
            unit="component_bundle", scope="제2200039호 중앙 마을기업지원위원회",
            service_function="중앙위원회 참석·안건검토수당", variable_role="target_assumption_bundle",
            reuse_policy="target_only", allowed_routes=["committee_components"],
            limitation="총 20명 중 위촉위원 14명·연 4회·회당 25만원은 정답 가정. 법안에 직접 명시되지 않음",
            **common),
    ]
