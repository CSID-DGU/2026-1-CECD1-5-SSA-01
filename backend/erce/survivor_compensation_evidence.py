"""Reviewed survivor compensation assumptions, not universal official prices."""
from backend.erce.reviewed_variable_rows import evidence_row


def survivor_compensation_rows():
    rows = []
    for group, count, age, pension, monthly in (
        ("ordinary", 22, 50, 2570000, 5940000),
        ("dangerous", 7, 51, 2310000, 4890000),
    ):
        for variable, value, unit, routes, years in (
            ("new_survivors", count, "person/year", ["survivor_pension_cohort_delta", "death_grant_delta"], None),
            ("initial_annual_pension_delta", pension, "KRW/person/year", ["survivor_pension_cohort_delta"], [2026]),
            ("monthly_income_delta", round(monthly*.068), "KRW/person/month", ["death_grant_delta"], [2026]),
            ("grant_months", 2, "month", ["death_grant_delta"], None),
        ):
            rows.append(evidence_row(
                evidence_key=f"2201105:{group}:{variable}:2024", variable_key=variable,
                value=[value] if years else value, unit=unit, source_bill_no="2201105",
                available_at="2024-08-22", source_ref="2201105 비용추계서 24D1399, PDF p.4~11",
                agency="인사혁신처", policy_domain="공무원 재해보상",
                scope=f"{'위험직무' if group == 'dangerous' else '일반'} 순직 특별승진 유족 보상",
                service_function="사후 특별승진에 따른 유족급여 증가",
                variable_role="compensation_assumption", reviewed_at="2026-10-02",
                obtained_from="reviewed_answer", requires_applicability_note=True,
                allowed_routes=routes, survivor_group=group, representative_spouse_age=age,
                promotion_income_increase_rate=.068, value_years=years,
                compensation_population_scope="all_civil_servants" if variable == "new_survivors" else None,
                observation_period=[2018, 2022] if variable == "new_survivors" else None,
                historical_special_promotion_deaths=145 if variable == "new_survivors" else None,
                quantity_derivation="2018~2022 전체 공무원 특별승진 순직 145명/5년=29명; 경찰·소방 위험직무 비율 24%를 준용하여 22/7명 배분" if variable == "new_survivors" else None,
                price_base_year=2024, observation_year=2026 if years else None,
                limitation="연간 순직자·대표 배우자·승진 증가율은 선례 가정. 최초 단가는 2026년/2024 불변가격 전용. 다른 기관·계급·연도에 무조건 적용 불가. 장기 추계에는 별도 생존율·연도별 지수 필요",
            ))
    for group, count in (("ordinary",14), ("dangerous",5)):
        rows.append(evidence_row(
            evidence_key=f"2201700:{group}:new_survivors:2024", variable_key="new_survivors",
            value=count, unit="person/year", source_bill_no="2201700", available_at="2024-08-22",
            source_ref="2201700 비용추계서 24D1945, PDF p.5: 인사혁신처 2019~2023 경찰·소방 특별승진 순직 총 96명",
            agency="인사혁신처", policy_domain="공무원 재해보상",
            scope=f"경찰·소방 {'위험직무' if group == 'dangerous' else '일반'} 특별승진 순직자",
            service_function="사후 특별승진에 따른 유족급여 증가",
            variable_role="historical_incidence_assumption", reviewed_at="2026-10-02",
            obtained_from="reviewed_answer", requires_applicability_note=True,
            allowed_routes=["survivor_pension_cohort_delta", "death_grant_delta"],
            survivor_group=group, compensation_population_scope="police_firefighters",
            observation_period=[2019,2023], historical_special_promotion_deaths=96,
            quantity_derivation="인사혁신처의 경찰·소방 특별승진 순직 96명/5년=19.2명; 선례는 연 19명으로 반올림하고 일반14/위험직무5명 배분",
            limitation="선례를 통해 확인한 기관 제공 과거 실적 기반 발생인원 가정. 통계청 공식 단가나 미래 확정 사망자 수가 아님. 전체 공무원 대상에 대체 적용 금지. 최신 통계 자동 갱신 아님",
        ))
    return rows
