"""Comparable wage-survey budget, reviewed after case 2205985's answer."""
from backend.erce.reviewed_variable_rows import evidence_row


def care_worker_survey_rows():
    common = dict(
        source_bill_no="2205985", available_at="2024-12-02",
        source_ref="의안 2205985 비용추계서(24C5258), PDF p.5; 보건복지부 2023년 사회복지사 보수 등 실태조사",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2205985/cost_estimate.pdf",
        agency="보건복지부", policy_domain="돌봄·사회복지 종사자 보수 실태조사",
        scope="중앙정부와 지방자치단체가 협력하는 전국 보수·지급실태 조사 1회",
        service_function="종사자 보수수준·지급실태·기준 준수율 조사",
        reuse_policy="comparable", source_class="precedent_assumption",
        allowed_routes=["research_survey", "annual_research_survey"],
        reviewed_at="2026-10-02", obtained_from="reviewed_answer",
        requires_applicability_note=True, price_year=2023,
        survey_population="사회복지사; 요양보호사 보수조사에 준용한 사례",
        implementation_model="central_local_cooperative_single_survey",
        scale_basis="전국 1회 통합조사 사업비; 표본 규모는 출처에 미기재",
        independently_verified=False,
    )
    cost = evidence_row(
        **common, evidence_key="2205985:social_worker_wage_survey:2023",
        variable_key="survey_unit_cost", value=178000000, unit="KRW/survey",
        variable_role="comparable_unit_rate",
        limitation="공식 고정요금이 아닌 2023년 유사 조사 사업비. 대상 직종·조사항목·전국 범위·수행방식을 확인한 뒤 사용. 지자체마다 별도 조사 시 개별 단가로 전용 금지; 시행 주기는 새 법안에서 추출")
    frozen = evidence_row(
        **common, evidence_key="2205985:wage_survey_price_freeze",
        variable_key="growth_rate", value=0, unit="ratio/year",
        variable_role="price_projection_assumption",
        limitation="해당 추계서의 추계기간 단가 동결 가정. 물가상승률 공식값이 아니며 새 추계에서도 동결할지 별도 확인 필요")
    return [cost, frozen]


def welfare_meal_safety_survey_rows():
    common = dict(source_bill_no="2208199", available_at="2026-10-11", reviewed_at="2026-10-11",
        source_ref="2208199 첨부25C0024 PDF3~4쪽; 2023 어린이 식생활안전관리 실태조사 및 식생활 안전지수 통합조사",
        agency="식품의약품안전처", policy_domain="사회복지급식소 위생·영양 조사",
        scope="전국 사회복지급식소 운영·위생·영양 조사에 어린이 식생활 통합조사를 준용한 참고 시나리오",
        service_function="social_welfare_meal_safety_survey", research_service_function="social_welfare_meal_safety_survey",
        research_cost_scope="integrated_survey_budget", implementation_model="national_integrated_meal_safety_survey",
        support_derivation="", allowed_routes=["research_survey"], requires_applicability_note=True,
        source_bill_version_match=False, requires_reference_scenario=True,
        source_version_issue="첨부표지 의안번호 공란·회답2025-02-03, 원문발의2025-02-17. 동일버전 미확인, 확보일 이후 참고만 허용",
        independently_verified=False, obtained_from="reviewed_answer",
        limitation="2023 어린이 통합조사 예산을 노인·장애인 급식소에 준용한 가정. 표본·과업범위 검토 필요. 최신 공식단가·법정3년주기 아님; 시설수와 다시 곱하지 않음")
    specs = [
        ("survey_unit_cost", 760000000, "KRW/survey", "comparable_budget", dict(price_year=2023)),
        ("base_year", 2023, "year", "price_reference_year", {}),
        ("recurrence_interval_years", 3, "year", "comparable_cycle_assumption", {}),
        ("growth_rates_by_year", {"2024": .025, "2025": .021, "2026": .02, "2027": .02, "2028": .02, "2029": .02, "2030": .02}, "ratio/year", "historical_forecast", dict(forecast_vintage="2024-12")),
    ]
    rows = []
    for key, value, unit, role, extra in specs:
        metadata = {**common, **extra}
        if key == "growth_rates_by_year":
            metadata["limitation"] = "2024.12 NABO 전망을 첨부에서 인용. 최신 실적·최신 전망 아님; 기준2023년 이후 매년 반영하고 적용연도 누락 시 계산하지 않음"
        rows.append(evidence_row(**metadata, evidence_key=f"2208199:meal_survey:{key}:reference",
            variable_key=key, value=value, unit=unit, variable_role=role))
    return rows


def social_worker_treatment_plan_rows():
    common = dict(source_bill_no="2207435", available_at="2025-02-13", reviewed_at="2026-10-11",
        source_ref="2207435 비용추계서25C0178 PDF3쪽; 2022 사회복지시설 종사자 인건비 가이드라인 개선 등 처우개선 지원방안 연구",
        agency="보건복지부", policy_domain="사회복지사 처우개선",
        scope="전국 종사자 보수·근로환경·처우개선 기본방향 및 재원조달의 별도 정책연구",
        service_function="social_worker_treatment_basic_plan", research_service_function="social_worker_treatment_basic_plan",
        research_cost_scope="research_contract_only", implementation_model="separate_national_treatment_plan",
        support_derivation="", allowed_routes=["research_plan"], requires_applicability_note=True,
        independently_verified=False, obtained_from="reviewed_answer",
        limitation="2022 연구용역을 준용한 선례 가정. 기존 보수·근로여건 조사비와 구분. 최신 공식요금 아님; 새 과업·규모·가격동결 확인 필요")
    return [evidence_row(**common, evidence_key="2207435:treatment_plan:2022_unit_cost",
        variable_key="plan_unit_cost", value=80000000, unit="KRW/plan", variable_role="comparable_unit_rate",
        price_year=2022, original_contract_cost_won=79500000,
        price_derivation="2022 실제 계약7,950만원을 추계서에서 약8,000만원으로 준용"),
        evidence_row(**common, evidence_key="2207435:treatment_plan:price_freeze",
        variable_key="growth_rate", value=0, unit="ratio/year", variable_role="price_projection_assumption")]


def social_worker_rights_rows():
    # 인권·폭력경험 과업은 보수조사와 단가 및 수행 범위를 분리한다.
    rights_common = dict(source_bill_no="2203955", available_at="2024-10-21", reviewed_at="2026-10-10",
        source_ref="2203955 비용추계서24C3788 PDF3~4쪽; 2021 사회복지사 안전 확보를 위한 폭력 경험 등에 관한 종합실태조사",
        agency="보건복지부", policy_domain="사회복지사 인권침해", scope="중앙·지방 협력 전국 통합 인권침해 연구용역",
        service_function="social_worker_rights_violence_survey", research_service_function="social_worker_rights_violence_survey",
        research_cost_scope="research_contract_only", implementation_model="central_local_cooperative_separate_survey",
        reuse_policy="comparable", source_class="precedent_assumption", allowed_routes=["research_survey"],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer", support_derivation="",
        limitation="2021 유사 인권·폭력경험 조사용역 준용 및 기간 동결. 기존 보수조사 전체사업비 아님. 지자체마다 별도 수행비로 중복 적용 금지")
    rights_cost = evidence_row(**rights_common, evidence_key="2203955:rights_survey:2021_unit_cost",
        variable_key="survey_unit_cost", value=50000000, unit="KRW/survey", price_year=2021,
        variable_role="comparable_unit_rate")
    rights_freeze = evidence_row(**rights_common, evidence_key="2203955:rights_survey:price_freeze",
        variable_key="growth_rate", value=0, unit="ratio/year", variable_role="price_projection_assumption")
    return [rights_cost, rights_freeze]


def social_worker_survey_history_rows():
    return [evidence_row(evidence_key="2205165:wage_survey:last_occurrence_year",
        variable_key="last_occurrence_year", value=2023, unit="year", source_bill_no="2205165",
        available_at="2024-11-19", reviewed_at="2026-10-10", source_ref="2205165 비용추계서24C4734 PDF3~4쪽; 보건복지부2023 보수실태조사",
        agency="보건복지부", policy_domain="사회복지사 보수조사", scope="기존 보수·지급실태 전국 통합조사",
        service_function="social_worker_wage_survey", research_service_function="social_worker_wage_survey",
        research_cost_scope="research_contract_only", support_derivation="",
        variable_role="historical_survey_phase", allowed_routes=["research_survey"],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="기존 조사2023 실시 이력. 개정 첫조사 시작연도와 구분, 주기는 새 원문에서 선택")]
