"""2200487: versioned veteran support rates and target-specific quantities.

Answer-derived projections are not official future tariffs. Target populations
must not be transferred to an unrelated bill merely because its topic matches.
"""
from backend.erce.reviewed_variable_rows import evidence_row

YEARS = [2026, 2027, 2028, 2029, 2030]
KINDS = {
    "self_compensation": ("transfer_recipient_delta", "본인 보상금 순증", "veteran_self"),
    "survivor_compensation": ("transfer_recipient", "선순위 배우자 유족보상금", "surviving_spouse"),
    "dependent_spouse": ("transfer_recipient", "생존자의 부양 배우자 수당", "dependent_spouse"),
    "hospital_inpatient": ("transfer_service_use", "보훈병원 입원", "hospital_family"),
    "hospital_outpatient": ("transfer_service_use", "보훈병원 외래", "hospital_family"),
    "hospital_drug": ("transfer_service_use", "보훈병원 약제", "hospital_family"),
    "contract_inpatient": ("transfer_service_use", "위탁병원 입원", "contract_survivor75plus"),
    "contract_outpatient": ("transfer_service_use", "위탁병원 외래", "contract_survivor75plus"),
    "prosthetic": ("quantity_unit", "보철구 지급", "prosthetic_recipient"),
}


def veteran_support_rows():
    rows = []
    def add(kind, key, value, unit, *, target=False, series=False, note="", page="5~16"):
        route, name, group = KINDS[kind]
        rows.append(evidence_row(
            evidence_key=f"2200487:{kind}:{key}:2024", variable_key=key, value=value, unit=unit,
            source_bill_no="2200487", available_at="2024-08-14",
            source_ref=f"2200487 비용추계서 24D1005, PDF p.{page}",
            agency="국가보훈부", policy_domain="국가유공자 지원 확대",
            scope=f"6·25참전 소년소녀병 {name}", service_function=name,
            variable_role="target_quantity" if target else "support_rate_assumption",
            reuse_policy="target_only" if target else "comparable",
            source_class="precedent_assumption", obtained_from="reviewed_answer",
            reviewed_at="2026-10-03", independently_verified=False,
            requires_applicability_note=True, allowed_routes=[route],
            veteran_support_kind=kind, veteran_population_group=group,
            value_years=YEARS if series else None,
            observation_year=2023 if "visits" in key else None,
            limitation=note or "선례의 지원 조건·기준연도·관측기간을 확인 후 사용. 공식 최신 단가 또는 미래 확정값이 아님",
        ))

    # Explicit target projections, NOT reusable general population tariffs.
    populations = {
        "veteran_self": [4909,3945,3101,2379,1778],
        "surviving_spouse": [23332,23697,23083,21643,19581],
        "dependent_spouse": [4209,3622,3060,2533,2052],
        "hospital_family": [6465,6842,7124,7319,7439],
        "contract_survivor75plus": [1320,1884,2377,2800,3151],
        "prosthetic_recipient": [198,159,125,96,72],
    }
    for kind, (route, _, group) in KINDS.items():
        key = "quantity" if kind == "prosthetic" else "recipient_count"
        add(kind,key,populations[group],"person/year",target=True,series=True,
            note="해당 의안의 인구·유배우자율·사망률 가정으로 산출한 연도별 수량. 다른 의안에 복사 불가; 인구 산출 입력 및 원 사망률로 별도 재추정 필요")

    for kind, benefits in (
        ("self_compensation", [1764000,1845000,1931000,2020000,2113000]),
        ("survivor_compensation", [1839000,1924000,2013000,2105000,2202000]),
    ):
        add(kind,"benefit_per_recipient",benefits,"KRW/person/month",series=True,page="5~8",
            note="2024년 재일학도의용군인 본인/유족 단가에 과거 연평균 상승률 4.6%를 적용한 선례 전망치. 공식 미래 단가 아님; 표시 단가의 반올림으로 순증 차액 오차 가능")
    add("self_compensation","existing_benefit_per_recipient",[481000,515000,551000,590000,632000],
        "KRW/person/month",series=True,page="6",
        note="현재 지급 중인 참전명예수당 차감. 2024년 월 42만원에 과거 상승률 7% 적용 가정. 새 보상금 전액을 순증으로 더하지 않음")
    add("dependent_spouse","benefit_per_recipient",100000,"KRW/person/month",page="9",
        note="선례에서 2020~2024 유지된 배우자수당 월10만원을 동결한 가정. 현재 공식 단가를 웹에서 새로 확인한 것이 아님")
    for kind in ("self_compensation", "survivor_compensation", "dependent_spouse"):
        add(kind,"payments_per_year",12,"month/year",page="6~9",note="월급여 12개월 지급 전제. 일시 보상금에 적용 금지")

    # Use unrounded historical visits / eligible persons, not the rounded .1/.5/.3 in the table.
    for kind, visits, denom, prices in (
        ("hospital_inpatient",155634,1165285,[140127,179541,230043,294749,377656]),
        ("hospital_outpatient",561355,1165285,[34487,36708,39072,41588,44266]),
        ("hospital_drug",347593,1165285,[25084,23432,21890,20449,19102]),
        ("contract_inpatient",168665,53864,[27578,28608,29677,30786,31936]),
        ("contract_outpatient",233418,53864,[19941,20957,22026,23148,24328]),
    ):
        add(kind,"visits_per_recipient",visits/denom,"visit/person/year",page="11~14",
            note=f"2023년 국가유공자 가족/유족 정부지원 실적 {visits}건/{denom}명. 입원·외래·약제와 병원을 구분하며 원 분자/분모로 계산. 본인 집단 이용률로 대체 불가")
        rows[-1].update(historical_visits=visits,historical_eligible_persons=denom,
                        medical_channel="contract" if kind.startswith("contract") else "hospital",
                        cost_basis="government_paid_support")
        add(kind,"cost_per_visit",prices,"KRW/visit",series=True,page="11~14",
            note="정부 지원금 지출/수진 건수 기반 단가를 선례의 상승률로 연장. 전체 의료비 단가가 아니므로 60% 감면율을 다시 곱하지 않음. 채널·서비스·연도 확인 필수")
        rows[-1].update(medical_channel="contract" if kind.startswith("contract") else "hospital",
                        cost_basis="government_paid_support")
    add("prosthetic","unit_cost",[1660000,1680000,1700000,1720000,1730000],
        "KRW/person/year",series=True,page="15~16",
        note="품목별 가격이 아닌 연간 지급예산/지급인원 평균 지원액. 2023년 약161만원에 연1% 상승 가정; 사용연한을 무시한 연1회 지급은 선례 가정")

    # Preserve underlying population assumptions without pretending missing age-specific mortality is present.
    rows.append(evidence_row(
        evidence_key="2200487:population_basis:2024", variable_key="veteran_population_basis",
        value={"base_year":2024,"living_by_age":dict(zip(range(82,100),
            [5,8,19,125,278,556,877,1254,1596,1831,398,109,58,19,16,8,6,2])),
            "living_count":7165,"already_deceased":25384,
            "married_share_age80_84":.837,"married_share_age85plus":.755,
            "spouse_age_gap":3,"contract_survivor_age75plus_share":.585,
            "prosthetic_historical_recipients":4751,"prosthetic_historical_eligible":117645},
        unit="population_bundle", source_bill_no="2200487",available_at="2024-08-14",
        source_ref="2200487 비용추계서 PDF p.4~7,10,13,15; 국가보훈부 자료 및 통계청 인용",
        agency="국가보훈부",policy_domain="국가유공자 지원 확대",scope="소년소녀병 2024년 집단",
        service_function="생존자·유족 지원 대상 인구 추정",variable_role="population_basis",
        reuse_policy="target_only",reviewed_at="2026-10-03",obtained_from="reviewed_answer",
        limitation="사망률 원시 연령별 표와 빈티지는 아직 미확보. 이 묶음만으로 인구를 재산출할 수 없음. 다른 소년소녀병 법안의 대상 정의·원자료와 구분",
    ))
    return rows


def reviewed_replay_payloads(db_path):
    """Development-only DB replay after answer review, not a blind evaluator."""
    rows=veteran_support_rows()
    return [dict(route_key=route,bill_no="2200487",cutoff_date="2026-10-03",
                 years=5,start_year=2026,evidence_mode="development_review",
                 veteran_support_kind=kind,veteran_population_group=group,
                 variable_db_path=db_path,
                 selected_evidence_keys=[r["evidence_key"] for r in rows if r.get("veteran_support_kind")==kind],
                 evidence_selection_reasons={r["evidence_key"]:"동일 대상 정답 확인 후 개발 재현"
                    for r in rows if r.get("veteran_support_kind")==kind})
            for kind,(route,_,group) in KINDS.items()]
