"""Annual food + operating expense, distinct from per-meal food-only tariffs."""
from backend.erce.reviewed_variable_rows import evidence_row

COST_BASIS="school_meal_food_and_operation_excluding_facilities"
FINANCING_SCOPE="education_special_account_and_local_government"


def school_meal_rows():
    rows=[]
    for suffix,key,value,unit,target,year,note in (
        ("alternative_students_2023","recipient_count",9560,"student",True,2023,
         "교육부2023.4.1 등록 대안교육기관217개 재학생 수. 미지원 학생수 아님. 해당 집단 전용; 일반 학교·학교 밖 청소년 전체로 전용 불가. 추계기간 동결은 선례 가정"),
        ("annual_cost_2023","annual_service_cost_per_person",1279347,"KRW/person/year",False,2023,
         "2023학교급식 실시현황의 식품비+운영비/급식학생수. 시설·설비 제외. 교육부 원 통계를 직접 재조회하지 않고 추계서 인용값으로 확보"),
        ("annual_cost_2025_assumption","annual_service_cost_per_person",1371000,"KRW/person/year",False,2025,
         "본문이2025기준이라고 기재한 학생1명당 연간 경비 전망. 2026첫해 금액과도 연결되어 기준연도 설명이 불명확. 원 물가경로가 없어 공식2026단가로 승격하지 않음"),
        ("combined_public_share_2023","public_support_share",.923,"ratio",False,2023,
         "교육비특별회계70.6%+지자체21.7%. 국고보조율이 아니며 보호자·기타 부담 제외. 전국 학교급식 실적을 대안교육기관에 준용하고 미래 동결한 가정; 현재 공식 분담률 아님"),
    ):
        row=evidence_row(
            evidence_key=f"2201813:{suffix}",variable_key=key,value=value,unit=unit,
            source_bill_no="2201813",available_at="2026-10-03",
            source_ref="2201813 비용추계서24C1991 PDF p.3~5; 교육부2023자료 인용",
            agency="교육부",policy_domain="학교급식",scope="등록 대안교육기관 급식 지원",
            service_function="시설비 제외 식품비·운영비 연간 지원",
            variable_role="target_quantity" if target else "annual_rate_assumption",
            reuse_policy="target_only" if target else "comparable",reviewed_at="2026-10-03",
            obtained_from="reviewed_answer",requires_applicability_note=True,
            allowed_routes=["school_meal_annual_public_support"],observation_year=year,
            service_cost_basis=COST_BASIS,public_financing_scope=FINANCING_SCOPE,
            published_date_status="표지2023.08.14는2024발의일·추계번호와 충돌; 공개일을 과거로 확정하지 않고 직접 확보일을 사용",
            limitation=note,
        )
        if key=="public_support_share":
            row.update(education_special_account_share=.706,local_government_share=.217)
        if target:
            row.update(reference_institutions=217,population_policy="재학생9560명 동결 시나리오; 이미 지원된 비용은 별도 확인 필요")
        rows.append(row)
    rows.append(evidence_row(
        evidence_key="2203380:cpi_2024_10:school_meal_2025_base:2026-2030",
        variable_key="cost_adjustment_factors",value=[1.02**n for n in range(1,6)],unit="ratio",
        source_bill_no="2203380",available_at="2024-10-28",
        source_ref="2203380 비용추계서 PDF p.8 각주6, NABO2024.10 CPI 전망:2026~2030년 각2.0%",
        agency="국회예산정책처",policy_domain="물가전망",scope="2025단가를2026~2030으로 환산",
        service_function="연간 급식경비 CPI 조정",variable_role="forecast_index_assumption",
        reuse_policy="comparable",reviewed_at="2026-10-03",obtained_from="non_target_report_forecast",
        requires_applicability_note=True,allowed_routes=["school_meal_annual_public_support"],
        value_years=[2026,2027,2028,2029,2030],cost_base_year=2025,
        service_cost_basis=COST_BASIS,public_financing_scope=FINANCING_SCOPE,
        forecast_vintage="NABO2024.10",rates_by_year={str(y):.02 for y in range(2026,2031)},
        limitation="이미 확보한 비대상 의안 인용 CPI전망으로2025기준 단가를 조정한 시나리오. 최신2026전망 아님. 급식 정답의 원 전망경로를 재현한 것으로 주장하지 않음",
    ))
    return rows


def reviewed_school_meal_payload(db_path):
    return dict(route_key="school_meal_annual_public_support",bill_no="2201813",years=5,start_year=2026,
                cutoff_date="2026-10-03",evidence_mode="development_review",variable_db_path=db_path,
                service_cost_basis=COST_BASIS,public_financing_scope=FINANCING_SCOPE,
                selected_evidence_keys=["2201813:alternative_students_2023",
                    "2201813:annual_cost_2025_assumption","2201813:combined_public_share_2023",
                    "2203380:cpi_2024_10:school_meal_2025_base:2026-2030"],
                evidence_selection_reasons={"2203380:cpi_2024_10:school_meal_2025_base:2026-2030":
                    "급식 단가의2025기준 기재를 그대로 따른 시나리오. 동일 소비자물가 지표를 별도 비대상 의안에서 확보; 원 정답 CPI경로는 미확인"})
