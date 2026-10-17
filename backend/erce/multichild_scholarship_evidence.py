"""Income-band annual tuition minus actual scholarship, using the existing formula."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

GROUP = "multichild_first_second_income1_8"
ROUTE = "transfer_recipient_delta"
BASE_COUNTS = (13358,10117,10928,10964,5477,16499,9973,20404)
ANNUAL_TUITION = (6269000,6292000,6277000,6275000,6302000,6364000,6359000,6388000)
ANNUAL_EXISTING_AID = (5059000,5062000,5043000,4410000,4434000,4444000,4212000,4217000)


def multichild_scholarship_rows():
    common=dict(source_bill_no="2201899",available_at="2026-10-03",reviewed_at="2026-10-03",
        agency="교육부",policy_domain="다자녀 국가장학금",scope="1~8소득구간 다자녀 첫째·둘째 등록금 전액지원",
        service_function="기존 장학금 차감 후 등록금 지원 순증",obtained_from="reviewed_answer",
        requires_applicability_note=True,allowed_routes=[ROUTE],
        scholarship_population_group=GROUP,scholarship_policy_reference_year=2024,
        eligibility_note="기초·차상위와 셋째 이상 기존 전액지원 집단 제외.9~10구간은 미추계",
        limitation="24C1992가 인용한 교육부2024년1학기 실적·가정. 교육부 원자료 독립 검증 전. 현재 최신 단가·전체 다자녀 인원 아님")
    rows=[]
    for band,(count,tuition,aid) in enumerate(zip(BASE_COUNTS,ANNUAL_TUITION,ANNUAL_EXISTING_AID),1):
        for key,value,unit,page,role in (
            ("base_recipient_count",count,"person",5,"historical_population_actual"),
            ("benefit_per_recipient",tuition,"KRW/person/year",6,"annual_tuition_mean"),
            ("existing_benefit_per_recipient",aid,"KRW/person/year",6,"annual_scholarship_actual_mean"),
        ):
            rows.append(evidence_row(**common,evidence_key=f"2201899:band{band}:{key}:2024",
                variable_key=key,value=value,unit=unit,source_ref=f"2201899 첨부24C1992 PDF p.{page}",
                variable_role=role,scholarship_income_band=band,observation_year=2024,
                reference_semester="2024-1",price_year=2024 if key!="base_recipient_count" else None,
                amount_basis="연간환산 평균; 해당 집단 등록금/실제 지급액, 지원 상한 아님"))
    for suffix,key,value,unit,page,role in (
        ("base_year","population_base_year",2024,"year",5,"reference_year"),
        ("student_growth","annual_population_growth_rate",-.019,"ratio/year","4~5","projection_assumption"),
        ("annual_payments","payments_per_year",1,"payment/year",6,"annual_unit_conversion"),
    ):
        rows.append(evidence_row(**common,evidence_key=f"2201899:{suffix}",variable_key=key,value=value,
            unit=unit,source_ref=f"2201899 첨부24C1992 PDF p.{page}",variable_role=role,
            trend_basis="2020~2023 일반·산업·교육·전문대학 학생수 증감률−1.90% 선례 가정; 등록금·지원액 성장률 아님" if key=="annual_population_growth_rate" else "2024년1학기 실적의 연간 환산 기준"))
    rows.append(evidence_row(**common,evidence_key="2201899:scope_rule:2024",variable_key="scholarship_scope_rule",
        value={"estimated_income_bands":list(range(1,9)),"estimated_birth_orders":[1,2],
               "zero_increment_groups":["기초·차상위 다자녀","1~8구간 셋째 이상"],
               "unestimated_income_bands":[9,10]},unit="rule",source_ref="2201899 첨부24C1992 PDF p.3~4",
        variable_role="applicability_rule",rule_note="2024 기존 제도를 유지한 시나리오에서만 적용.9~10구간은 비용0이 아니라 규모 미확보"))
    return rows


def prepare_scholarship_projection(payload):
    if payload.get("scholarship_population_group")!=GROUP:
        return payload
    band=payload.get("scholarship_income_band")
    if isinstance(band,bool) or not isinstance(band,int) or band not in range(1,9):
        raise ValueError("scholarship income band is outside the confirmed1–8 scope")
    resolved,_=resolve_formula_variables(("recipient_count","base_recipient_count","population_base_year",
        "annual_population_growth_rate","benefit_per_recipient","existing_benefit_per_recipient","payments_per_year"),
        target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    for key in ("benefit_per_recipient","existing_benefit_per_recipient"):
        if key in resolved and resolved[key].unit!="KRW/person/year":
            raise ValueError(f"{key} must be an annual mean, not a semester amount or limit")
    if "payments_per_year" in resolved and resolved["payments_per_year"].value!=1:
        raise ValueError("annual scholarship means cannot be multiplied by semesters again")
    if "recipient_count" in resolved:
        return payload  # Do not overwrite confirmed target counts.
    if payload.get("scholarship_population_projection")!="historical_count_growth":
        return payload
    if not str(payload.get("scholarship_projection_confirmation_note") or "").strip():
        raise ValueError("scholarship population projection needs applicability confirmation")
    required=("base_recipient_count","population_base_year","annual_population_growth_rate")
    missing=[key for key in required if key not in resolved]
    if missing:
        raise ValueError("missing scholarship projection evidence: "+", ".join(missing))
    count,base,rate=(resolved[key].value for key in required)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in (count,base,rate)):
        raise ValueError("invalid scholarship population projection inputs")
    if count<0 or int(base)!=base or not -1<rate<=1:
        raise ValueError("invalid scholarship population projection range")
    if resolved["base_recipient_count"].unit!="person" or resolved["annual_population_growth_rate"].unit!="ratio/year":
        raise ValueError("scholarship population projection unit mismatch")
    if payload.get("start_year") is None or int(payload["start_year"])<base:
        raise ValueError("scholarship projection start_year")
    for layer in ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs","selected_variable_inputs"):
        if any(key in (payload.get(layer) or {}) for key in ("growth_rate","growth_rates_by_year","first_year_fraction")):
            raise ValueError("population growth must not be reapplied to annual scholarship cost")
    years=int(payload.get("years") or 5)
    values=[round(count*(1+rate)**(int(payload["start_year"])+i-int(base))) for i in range(years)]
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["recipient_count"]=dict(value=values,unit="person/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(resolved[key].source_ref for key in required)))
    return {**payload,"calculated_inputs":calculated}


def reviewed_multichild_payloads(db_path):
    return [dict(route_key=ROUTE,bill_no="2201899",agency="교육부",policy_domain="다자녀 국가장학금",
        start_year=2026,years=5,cutoff_date="2026-10-03",evidence_mode="development_review",variable_db_path=db_path,
        scholarship_population_group=GROUP,scholarship_policy_reference_year=2024,scholarship_income_band=band,
        scholarship_population_projection="historical_count_growth",
        scholarship_projection_confirmation_note="정답 확인 후2024 기존 정책·동결 단가 및 학생수−1.90% 선례 전망 재계산.9~10구간 제외한 일부추계",
        selected_evidence_keys=[f"2201899:band{band}:{key}:2024" for key in
            ("base_recipient_count","benefit_per_recipient","existing_benefit_per_recipient")]
            +["2201899:base_year","2201899:student_growth","2201899:annual_payments","2201899:scope_rule:2024"])
        for band in range(1,9)]
