"""Historical regional recipient projections, not universal population prices."""
from backend.erce.reviewed_variable_rows import evidence_row


def regional_child_allowance_rows():
    rows = []
    for age_min, age_max, populations in (
        (0, 7, [129029, 124827, 121274, 118196, 115481]),
        (8, 17, [304206, 301807, 299778, 298020, 296470]),
    ):
        rows.append(evidence_row(
            evidence_key=f"2210913:declining_region:age{age_min}-{age_max}:recipients:2026-2030",
            variable_key="recipient_count", value=[n * .996 for n in populations], unit="person",
            source_bill_no="2210913", available_at="2025-07-15",
            source_ref="2210913 비용추계서25C3281 PDF4~6쪽; 표5 지역별 연령집단 인구×집행계수99.6%",
            agency="국회예산정책처", policy_domain="아동수당",
            scope=f"2025년 당시 지정 인구감소지역89개시군구 {age_min}~{age_max}세",
            service_function="인구감소지역 아동수당 추가지급",
            variable_role="assumption", reviewed_at="2026-10-04",
            allowed_routes=["transfer_recipient"], value_years=list(range(2026, 2031)),
            child_population_geography="인구감소지역89개시군구:2025",
            population_age_min=age_min, population_age_max=age_max,
            recipient_population_basis="regional_2022_2024_trend_execution_0996",
            requires_applicability_note=True, obtained_from="reviewed_answer",
            independently_verified=False, raw_population=populations, execution_factor=.996,
            already_adjusted_for_execution=True,
            population_source="행정안전부 주민등록 인구통계2022~2024년; 지정89개시군구",
            projection_method="지역 아동수의 최근3년간 추이가 지속된다는 선례 가정",
            projection_method_limit="정답의 연령별 전망값을 저장. 연령별2022~2024 원자료와 구체 전망 산출법은 독립 검증하지 않음",
            historical_total_under18_population={"2022":489905,"2023":470770,"2024":448984},
            source_url="backend/generated/assembly_22_pdfs/by_bill/2210913/cost_estimate.pdf",
            refresh_policy="지역 지정 목록·연령별 공식통계·전망기간·집행계수를 확인하여 새 버전 추가; 기존 선례 덮어쓰기 금지",
            limitation="정답 열람 후 저장한 역사적 전망. 전국/다른지역/다른연령/2026~2030년 외 전용금지. 집행계수 중복적용금지. 최신 공식 인구라고 주장하지 않음",
        ))
    return rows
