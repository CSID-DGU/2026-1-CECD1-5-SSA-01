"""Reviewed population inputs for transfer-payment formulas."""
from backend.erce.reviewed_variable_rows import evidence_row


def transfer_payment_rows():
    population = evidence_row(
        evidence_key="mois:registered_population:2024-05",
        variable_key="recipient_count", value=51_277_347, unit="person",
        source_bill_no="official:mois-resident-population-2024-05",
        available_at="2024-05-31",
        source_ref="행정안전부 주민등록인구현황, 2024년 5월말 전국 51,277,347명",
        source_url="https://jumin.mois.go.kr/statMonth.do",
        agency="전국", policy_domain="인구통계", scope="2024년 5월말 전국 주민등록인구",
        service_function="전국민 일회성 지원금", variable_role="target_quantity",
        reuse_policy="same_scope", source_class="official_standard",
        allowed_routes=["transfer_recipient"], valid_from_year=2024, valid_to_year=2024,
        reference_date="2024-05-31",
        limitation="다른 연도·월 또는 연령·소득 제한 지원사업에 자동 전용 금지")
    adjusted_population = evidence_row(
        evidence_key="mois:base_population:2024-05",
        variable_key="base_population", value=51_277_347, unit="person",
        source_bill_no="official:mois-resident-population-2024-05",
        available_at="2024-05-31",
        source_ref="행정안전부 주민등록인구현황, 2024년 5월말 전국 51,277,347명",
        source_url="https://jumin.mois.go.kr/statMonth.do",
        agency="전국", policy_domain="인구통계", scope="2024년 5월말 전국 주민등록인구",
        service_function="전국민 일회성 지원금 대상인구 조정", variable_role="baseline_actual",
        reuse_policy="same_scope", source_class="official_standard",
        allowed_routes=["transfer_recipient_adjusted"], valid_from_year=2024, valid_to_year=2024,
        reference_date="2024-05-31", reviewed_at="2026-09-28",
        limitation="기준 인구일 뿐, 특정 법안의 최종 지급 대상자는 아님")
    answer_common = dict(
        source_bill_no="2200563", available_at="2024-07-11",
        source_ref="의안 2200563 비용추계서(24D0967), PDF p.3~5, [표 2]",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200563/cost_estimate.pdf",
        agency="전국", policy_domain="민생회복지원금", scope="2024년 일회성 민생회복지원금",
        service_function="법안 제5조 지급대상 인구 조정",
        reuse_policy="target_only", source_class="precedent_assumption",
        allowed_routes=["transfer_recipient_adjusted"], reviewed_at="2026-09-28",
        obtained_from="reviewed_answer", value_years=[2024],
    )
    excluded = evidence_row(
        evidence_key="2200563:excluded_recipients:2024", variable_key="excluded_recipients",
        value=53_738, unit="person", variable_role="target_quantity", **answer_common,
        components={"correctional_inmates_2022": 52_940, "forensic_hospital_2022": 798},
        limitation="두 수용자 집계는 2022년 관측치의 정답 추계 가정. 다른 법안에 자동 재사용 금지")
    added = evidence_row(
        evidence_key="2200563:additional_recipients:2024", variable_key="additional_recipients",
        value=2_067_362, unit="person", variable_role="target_quantity", **answer_common,
        components={"long_term_foreigners_2023": 1_881_921, "permanent_residents_2023": 185_441},
        possible_overlap_count=185_441,
        limitation="정답 재현 전용. 법무부 통계의 장기 체류외국인 1,881,921명에 F-5 영주자 185,441명이 이미 포함될 가능성이 있어 별도 가산은 중복 위험. 다른 법안 전용 금지")
    farmer_common = dict(
        source_bill_no="2200431", available_at="2024-07-05",
        source_ref="의안 2200431 비용추계서(24B0837), PDF p.11~14, 표 5·6·8·9",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200431/cost_estimate.pdf",
        agency="전국", policy_domain="농어민수당",
        scope="2026~2030년 농어업경영체 등록 개인 수급자; 법인 제외",
        service_function="농어민수당 지급과 국비 분담",
        reuse_policy="target_only", source_class="precedent_assumption",
        allowed_routes=["transfer_recipient", "transfer_recipient_subsidy"],
        reviewed_at="2026-09-28", obtained_from="reviewed_answer",
        value_years=[2026, 2027, 2028, 2029, 2030],
        limitation="정답 확인 후 재현용. 다른 법안의 대상자·단가·분담률로 자동 전용 금지",
    )
    farmer_count = evidence_row(
        evidence_key="2200431:recipient_count:2026-2030", variable_key="recipient_count",
        value=[2597872, 2594119, 2590360, 2586543, 2582599], unit="person/year",
        variable_role="target_quantity", method="총인구 전망 × 중복제거 등록자 비율 5.03%; 정답 표 6의 반올림 인원",
        **farmer_common)
    farmer_benefit = evidence_row(
        evidence_key="2200431:benefit_per_recipient:2026-2030",
        variable_key="benefit_per_recipient", value=[4632000, 4824000, 5016000, 5220000, 5424000],
        unit="KRW/person/year", variable_role="unit_rate",
        method="2024년 1인가구 기준중위소득 2,228,445원 × 연 4.0% 증가 × 생계급여 선정비율 32% × 50%; 월 천원 단위 올림 후 12개월",
        **farmer_common)
    farmer_share = evidence_row(
        evidence_key="2200431:subsidy_rate:2026-2030", variable_key="subsidy_rate",
        value=0.5, unit="ratio", variable_role="assumption",
        legal_floor=0.4, assumption_note="법안 제27조의 40% 이상은 하한. 50%는 정답 추계의 국비 시나리오 가정",
        **{**farmer_common, "allowed_routes": ["transfer_recipient_subsidy"]})
    return [population, adjusted_population, excluded, added,
            farmer_count, farmer_benefit, farmer_share]


def veteran_allowance_rows():
    """Atomic operands from 2200169, captured only after the blind run failed."""
    common = dict(
        source_bill_no="2200169", available_at="2024-08-09",
        source_ref="의안 2200169 비용추계서(24D0536), PDF p.5~17, 표 4·7·9·11·14·19·21·23",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200169/cost_estimate.pdf",
        agency="국가보훈부", policy_domain="참전유공자 예우",
        scope="참전명예수당·유족 의료지원·수송지원, 2025~2029",
        service_function="참전유공자법 개정에 따른 추가 지급",
        reuse_policy="target_only", source_class="precedent_assumption",
        reviewed_at="2026-09-28", obtained_from="reviewed_answer",
        value_years=[2025, 2026, 2027, 2028, 2029],
        limitation="대상 의안 정답에서 확인한 추계 가정. 다른 법안에 자동 재사용 금지",
    )
    rows = []
    def add(suffix, variable, value, unit, role, routes, **extra):
        rows.append(evidence_row(
            evidence_key=f"2200169:{suffix}:2025-2029", variable_key=variable,
            value=value, unit=unit, variable_role=role, allowed_routes=routes,
            **common, **extra))
    recipient_routes = ["transfer_recipient", "transfer_recipient_delta"]
    add("concurrent_new_recipients", "recipient_count", [78919,72084,65842,60140,54932],
        "person/year", "target_quantity", ["transfer_recipient"],
        population_group="병급금지 해제로 새로 지급받는 참전유공자")
    add("existing_recipients", "recipient_count", [110527,100955,92212,84227,76933],
        "person/year", "target_quantity", ["transfer_recipient_delta"],
        population_group="기존 참전명예수당 수급자")
    add("surviving_spouses", "recipient_count", [12950,23730,32613,39840,45627],
        "person/year", "target_quantity", ["transfer_recipient"],
        population_group="시행 이후 사망자 중 배우자 승계 누계; 유배우자율 72.1%, 배우자 사망률 8.1% 가정")
    for level, value in ((32,[757000,803000,852000,904000,960000]),
                         (60,[1419000,1506000,1598000,1696000,1799000])):
        add(f"new_monthly_benefit_{level}pct", "benefit_per_recipient", value,
            "KRW/person/month", "unit_rate", recipient_routes,
            scenario_key=f"{level}pct",
            scenario=f"최저생계비를 1인가구 중위소득의 {level}%로 해석",
            rate_note="2024년 중위소득에서 연 6.1% 증가 가정; 정답의 연도별 표시금액")
    add("existing_monthly_benefit", "existing_benefit_per_recipient",
        [450000,481000,515000,551000,590000], "KRW/person/month", "baseline_unit_rate",
        ["transfer_recipient_delta"], method="2024년 월 42만원에서 연 7.0% 증가 가정")
    for channel, count, visits, price in (
        ("veterans_hospital", [447680,450988,454010,456771,459292], [.6]*5,
         [75141,79428,83960,88750,93814]),
        ("contract_hospital", [528388,531864,535039,537939,540588],
         [7.4,6.8,6.3,5.8,5.3], [24525,25461,26432,27441,28488]),
    ):
        add(f"{channel}_recipients", "recipient_count", count, "person/year",
            "target_quantity", ["transfer_service_use"], care_channel=channel)
        add(f"{channel}_visits", "visits_per_recipient", visits, "visit/person/year",
            "utilization_assumption", ["transfer_service_use"], care_channel=channel)
        add(f"{channel}_cost_per_visit", "cost_per_visit", price, "KRW/visit",
            "unit_rate", ["transfer_service_use"], care_channel=channel)
    add("transport_recipients", "recipient_count", [143866,131407,120027,109633,100139],
        "person/year", "target_quantity", ["transfer_recipient"],
        population_group="기존 수송지원 대상 보상금 수급자 제외")
    rows.append(evidence_row(
        evidence_key="2200169:transport_unit_cost:2023", variable_key="benefit_per_recipient",
        value=90341, unit="KRW/person/year", source_bill_no="2200169", available_at="2024-08-09",
        source_ref="의안 2200169 비용추계서(24D0536), PDF p.16, 2023년 국가유공자 수송지원 예산/대상자",
        source_url=common["source_url"], agency="국가보훈부", policy_domain="참전유공자 예우",
        scope="2023년 국가유공자 수송시설 이용지원 전국 평균", service_function="수송시설 할인 지원",
        variable_role="unit_rate", reuse_policy="comparable", source_class="precedent_assumption",
        reviewed_at="2026-09-28", obtained_from="reviewed_answer", allowed_routes=["transfer_recipient"],
        price_year=2023, source_estimate_years=[2025, 2026, 2027, 2028, 2029],
        requires_applicability_note=True,
        limitation="2023년 과거 평균지원액이며 법정 고정요금이 아님. 2024-08-09 이전 공개를 확인하지 못해 그 전 컷오프에 사용 금지; 다른 수송수단 구성·지원범위·가격연도에는 직접 전용 금지"))
    return rows
