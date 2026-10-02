"""Direct official population observations and age-specific parent benefits."""
from backend.erce.reviewed_variable_rows import evidence_row

POPULATION_URL = "https://kosis.kr/visual/populationKorea/populationPyramidData.do"
BENEFIT_URL = "https://www.mohw.go.kr/board.es?act=view&bid=0027&list_no=1479667&mid=a10503000000"


def parent_benefit_rows():
    rows = []
    for age, counts, monthly in (
        (0, [217226, 217079, 227833, 237996, 247279], 1000000),
        (1, [228266, 216540, 216413, 227121, 237221], 500000),
    ):
        context = dict(
            agency="보건복지부", policy_domain="부모급여", geography="전국",
            scope=f"전국 {age}세 부모급여 대상 인구", service_function="연령별 부모급여 폐지",
            reuse_policy="comparable", reviewed_at="2026-10-02",
            requires_applicability_note=True, independently_verified=True,
            allowed_routes=["transfer_benefit_abolition"],
        )
        rows.append(evidence_row(
            **context, evidence_key=f"kosis_202312:age{age}_population:2025-2029",
            variable_key="recipient_count", value=counts, unit="person/year",
            source_bill_no="KOSIS_202312", available_at="2026-10-02",
            source_ref=f"KOSIS 인구피라미드, 전국 중위 시나리오 rcgnSn=222, 2025~2029년 남녀 {age}세 합계; 2026-10-02 직접 조회",
            source_url=POPULATION_URL, source_class="official_standard",
            variable_role="target_quantity", obtained_from="official_web_data",
            value_years=[2025,2026,2027,2028,2029], population_age_min=age, population_age_max=age,
            forecast_version="통계청 2023.12 장래인구추계(2022 기준), 중위",
            request_parameters={"rcgnSn":"222", "areaId":""},
            derivation="manDtvalArry와 femaleDtvlArry의 해당 연령을 정수 합산",
            limitation="실제 수급자 수가 아닌 전망 인구. 국적·수급요건·보육료 중복·부분월 확인 필요. 공개 시점은 보수적으로 직접 확보일 사용; 최신 개편 버전으로 간주하지 않음",
        ))
        rows.append(evidence_row(
            **context, evidence_key=f"mohw_parent_benefit:age{age}:2024_monthly",
            variable_key="existing_benefit_per_recipient", value=monthly, unit="KRW/person/month",
            source_bill_no="MOHW_PARENT_2024", available_at="2026-10-02",
            source_ref=f"보건복지부 2024년 정부지원 확대 보도자료: {age}세 부모급여 월 {monthly//10000}만원; 2026-10-02 확인",
            source_url=BENEFIT_URL, source_class="official_standard",
            variable_role="official_reference_rate", observation_year=2024,
            population_age_min=age, population_age_max=age,
            limitation="2024년 공식 급여 기준액. 이후 연도 동결은 별도 추계 가정이며 최신 지급액 자동 갱신 아님. 현금과 보육료 바우처 중복 차감 금지",
        ))
    rows.append(evidence_row(
        evidence_key="2200509:parent_benefit_treasury_share:2024",
        variable_key="subsidy_rate", value=.6834, unit="ratio",
        source_bill_no="2200509", available_at="2024-07-05",
        source_ref="2200509 비용추계서(24C0465), PDF p.4: 2024년 부모급여 평균 국고보조율",
        agency="보건복지부", policy_domain="부모급여", scope="전국 부모급여 국비 분리",
        service_function="부모급여 폐지", variable_role="financing_share_assumption",
        reviewed_at="2026-10-02", obtained_from="reviewed_answer",
        requires_applicability_note=True, allowed_routes=["transfer_benefit_abolition"],
        observation_year=2024, valid_from_year=2025, valid_to_year=2029,
        limitation="선례가 유지한 2024년 평균 분담률. 총 감소액에는 적용하지 않고 국비 분리 시만 사용",
    ))
    return rows
