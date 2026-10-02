"""Reviewed executive position-difference inputs."""
from backend.erce.reviewed_variable_rows import evidence_row


def executive_position_difference_rows():
    difference_2025 = 5_520_000
    salary_differences = [difference_2025 * 1.024 ** offset for offset in range(5)]
    common = dict(
        agency="중앙행정기관",
        policy_domain="정부조직",
        scope="기존 국무위원이 부총리를 겸임하는 경우의 보수 순증분",
        service_function="장관의 부총리 겸임",
        reuse_policy="same_scope",
        obtained_from="non_target_source",
    )
    rows = [
        evidence_row(
            evidence_key="2212538:deputy_pm_salary_difference:2025-2029",
            variable_key="annual_salary_difference",
            value=salary_differences,
            unit="KRW/person/year",
            source_bill_no="2212538",
            available_at="2025-09-04",
            source_ref=("의안2212538, 25D4678, 비용추계서 PDF p.4~5; "
                        "2025년 부총리 1억7225만원-장관 1억6673만원=552만원, "
                        "공무원 보수상승률 연 2.4% 적용"),
            source_url="backend/generated/assembly_22_pdfs/by_bill/2212538/cost_estimate.pdf",
            value_years=[2025, 2026, 2027, 2028, 2029],
            price_year=2025,
            base_difference_won=difference_2025,
            annual_growth_assumption=.024,
            allowed_routes=["personnel_position_difference"],
            variable_role="unit_rate",
            limitation="부총리-장관 전체 보수의 차액만 재사용. 증원 인건비나 다른 직급 승격에 적용 금지",
            **common,
        ),
        evidence_row(
            evidence_key="2124672:central_government_employer_rate:2025-2029",
            variable_key="employer_contribution_rate",
            value=[.13165, .13251, .13339, .13428, .13512],
            unit="ratio",
            source_bill_no="2124672",
            available_at="2023-10-31",
            source_ref=("의안2124672 비용추계서; 국회예산정책처 전망 "
                        "공무원 기관부담요율 2025~2029년"),
            source_url="backend/generated/assembly_rag_seed/cost_estimate_variables.jsonl",
            value_years=[2025, 2026, 2027, 2028, 2029],
            allowed_routes=["personnel_employer_contribution"],
            variable_role="forecast_assumption",
            limitation="중앙정부 공무원 보수에 적용. 공공기관 요율과 구분",
            **common,
        ),
    ]
    target_common = dict(
        agency="중앙행정기관", policy_domain="정부조직",
        scope="기존 국무위원이 부총리를 겸임하는 경우의 보수 순증분",
        service_function="장관의 부총리 겸임", source_bill_no="2200010",
        available_at="2024-06-05", source_ref="의안2200010, 24D0291, 비용추계서 PDF p.2~3",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200010/cost_estimate.pdf",
        value_years=[2025, 2026, 2027, 2028, 2029], reuse_policy="same_scope",
        obtained_from="reviewed_answer",
    )
    rows.extend([
        evidence_row(evidence_key="2200010:deputy_pm_salary_difference:2025-2029",
            variable_key="annual_salary_difference",
            value=[5_494_000, 5_598_000, 5_704_000, 5_812_000, 5_922_000],
            unit="KRW/person/year", variable_role="unit_rate",
            allowed_routes=["personnel_position_difference"],
            base_difference_won=5_392_000, annual_growth_assumption=.019,
            limitation="2024년 보수표와 당시 전망치를 적용한 과거 버전; 현행단가로 승격하지 않음",
            **target_common),
        evidence_row(evidence_key="2200010:central_government_employer_rate:2025-2029",
            variable_key="employer_contribution_rate",
            value=[.13114, .13210, .13305, .13399, .13494], unit="ratio",
            variable_role="forecast_assumption", allowed_routes=["personnel_employer_contribution"],
            limitation="2024.4 국회예산정책처 과거 전망치",
            **target_common),
    ])
    return rows
