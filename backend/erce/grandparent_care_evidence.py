from decimal import Decimal,ROUND_HALF_UP
from math import isfinite
from backend.erce.common_population_evidence import single_age_population_matrix
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="grandparent_care_age_net"
PARALLEL="grandparent_care_allowance_parallel"


def grandparent_care_rows():
    rows=[evidence_row(evidence_key="official:kosis:age0_5:2027-2031:grandparent",
        variable_key="child_age_populations",value=single_age_population_matrix(0,5,2027,5),unit="age_to_person_series",
        source_bill_no="official:kosis:DT_1BPA001:202312",available_at="2023-12-14",reviewed_at="2026-10-08",
        source_ref="기존KOSIS2023.12전국중위전망 원자료+2031보충;0~5세별남녀합산",
        agency="통계청",policy_domain="공통인구",scope="전국0~5세2027~2031",
        service_function="official_population_stock",variable_role="official_population",
        source_class="official_standard",independently_verified=True,value_years=list(range(2027,2032)),
        population_geography="전국",statistical_sex="total",population_vintage="2023-12",
        requires_applicability_note=True,limitation="인구전망이지등록조부모수아님.기존공식원자료재사용,최신관측인구아님")]
    data=[
        ("grandparent_care_shares",dict(zip(map(str,range(6)),[.05,.046,.04,.042,.039,.045])),"age_to_ratio"),
        ("supported_care_hours",60,"hour/month"),
        ("public_care_hour_rate",3000,"KRW/hour"),
        ("foregone_allowance_by_age",dict(zip(map(str,range(6)),[0,0,100000,100000,100000,100000])),"age_to_KRW/month"),
        ("registration_take_up",1,"ratio"),
        ("care_payment_months",12,"month/year"),
    ]
    for key,value,unit in data:
        rows.append(evidence_row(evidence_key=f"2211034:{key}:reviewed",variable_key=key,value=value,unit=unit,
            source_bill_no="2211034",available_at="2025-07-16",reviewed_at="2026-10-08",
            source_ref="2211034 비용추계서25C3422 PDF4~7쪽;2024보육실태조사·당시시간제보육지원준용",
            agency="보건복지부",policy_domain="손자녀돌봄수당",scope="0~5세양육영유아수기준대리추계",
            service_function=PROFILE,support_derivation=PROFILE,grandparent_count_basis="child_age_proxy",
            variable_role="care_scenario_operand",allowed_routes=["direct_annual_amount"],
            requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
            limitation="공식조부모고시단가아님.모두연초등록·소득무관·단가동결·0~1세양육수당대체0/2~5세10만원차감가정.원조사독립검증미완료"))
    return rows


def prepare_grandparent_care(payload):
    if payload.get("route_key")!="direct_annual_amount" or payload.get("grandparent_count_basis")!="child_age_proxy":
        raise ValueError("grandparent benefit needs child-based scope confirmation")
    parallel = payload.get("support_derivation") == PARALLEL
    if parallel and (payload.get("grandparent_allowance_mode") != "allowance_parallel"
            or payload.get("care_proxy_confirmed") is not True
            or not str(payload.get("care_population_proxy_note") or "").strip()):
        return {**payload, "support_missing_operands": ["care_parallel_proxy_confirmation"],
                "support_derivation_trace": []}
    if payload.get("care_price_projection")!="freeze_reference_rate" or not all(str(payload.get(k) or "").strip()
        for k in ("support_derivation_note","registration_scope_note","allowance_overlap_note","estimation_start_note")):
        raise ValueError("grandparent registration/price/overlap notes required")
    if payload.get("population_geography")!="전국" or payload.get("statistical_sex")!="total" or payload.get("population_vintage")!="2023-12":
        raise ValueError("grandparent population scope/vintage mismatch")
    if payload.get("start_year") is None:return {**payload,"support_missing_operands":["start_year"]}
    years=payload.get("years",5)
    if isinstance(payload["start_year"],bool) or not isinstance(payload["start_year"],int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("invalid grandparent benefit period")
    units={"child_age_populations":"age_to_person_series","grandparent_care_shares":"age_to_ratio",
        "supported_care_hours":"hour/month","public_care_hour_rate":"KRW/hour",
        "foregone_allowance_by_age":"age_to_KRW/month","registration_take_up":"ratio","care_payment_months":"month/year"}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","participation_rate","subsidy_rate")):
        raise ValueError("grandparent benefit duplicate adjustment forbidden")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        if row.unit!=units[k] or not row.source_ref:raise ValueError("grandparent source/unit mismatch")
    v={k:row.value for k,row in r.items()};ages=set(map(str,range(6)))
    for k in ("child_age_populations","grandparent_care_shares","foregone_allowance_by_age"):
        if not isinstance(v[k],dict) or set(v[k])!=ages:raise ValueError("grandparent age groups must be 0~5")
    def valid(x):return not isinstance(x,bool) and isinstance(x,(int,float)) and isfinite(x) and x>=0
    for age in ages:
        pop=v["child_age_populations"][age]
        if not isinstance(pop,list) or len(pop)!=years or not all(valid(x) for x in pop):raise ValueError("invalid age population horizon")
        if not valid(v["grandparent_care_shares"][age]) or v["grandparent_care_shares"][age]>1 or not valid(v["foregone_allowance_by_age"][age]):
            raise ValueError("invalid care share/allowance")
    for k in ("supported_care_hours","public_care_hour_rate","registration_take_up","care_payment_months"):
        if not valid(v[k]):raise ValueError("invalid care scalar")
    if v["registration_take_up"]>1 or v["care_payment_months"]>12:raise ValueError("invalid registration/months")
    if parallel and any(v["foregone_allowance_by_age"][age] != 0 for age in ages):
        raise ValueError("parallel childcare allowance must not be deducted")
    gross_price=v["supported_care_hours"]*v["public_care_hour_rate"]
    net_price={age:gross_price-v["foregone_allowance_by_age"][age] for age in ages}
    if any(x<0 for x in net_price.values()):raise ValueError("allowance exceeds care support")
    annual=[];trace=[]
    for i in range(years):
        counts={age:int((Decimal(str(v["child_age_populations"][age][i]))*Decimal(str(v["grandparent_care_shares"][age]))).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) for age in ages}
        parts={age:counts[age]*v["registration_take_up"]*net_price[age]*v["care_payment_months"] for age in ages}
        annual.append(sum(parts.values()))
        trace.append(dict(year=payload["start_year"]+i,age_child_counts=counts,gross_monthly_support=gross_price,
            net_monthly_by_age=net_price,registration_take_up=v["registration_take_up"],annual_won_by_age=parts,
            allowance_mode=payload.get("grandparent_allowance_mode", "replacement_net"),
            population_proxy_note=payload.get("care_population_proxy_note"),
            expression="Σ(연령별인구×조부모돌봄비율×등록률×(시간한도×공공시간단가−기존양육수당)×개월)"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}


def grandparent_parallel_rows():
    rows = [evidence_row(evidence_key="official:kosis:age0_5:2025-2029:grandparent_parallel",
        variable_key="child_age_populations", value=single_age_population_matrix(0, 5, 2025, 5),
        unit="age_to_person_series", source_bill_no="official:kosis:DT_1BPA001:202312",
        available_at="2023-12-14", reviewed_at="2026-10-10",
        source_ref="기존KOSIS2023.12 전국 중위전망 원자료, 2025~2029 0~5세 각세 남녀합산",
        agency="통계청", policy_domain="공통인구", scope="전국0~5세2025~2029", service_function="official_population_stock",
        variable_role="official_population", source_class="official_standard", independently_verified=True,
        value_years=list(range(2025, 2030)), population_geography="전국", statistical_sex="total", population_vintage="2023-12",
        requires_applicability_note=True, limitation="각세 인구전망이지 실제 시설미이용·등록 조부모 수가 아님")]
    data = [
        ("grandparent_care_shares", dict(zip(map(str, range(6)), [.083, .039, .038, .049, .042, .05])), "age_to_ratio"),
        ("supported_care_hours", 80, "hour/month"), ("public_care_hour_rate", 3000, "KRW/hour"),
        ("foregone_allowance_by_age", dict.fromkeys(map(str, range(6)), 0), "age_to_KRW/month"),
        ("registration_take_up", 1, "ratio"), ("care_payment_months", 12, "month/year"),
    ]
    for key, value, unit in data:
        rows.append(evidence_row(evidence_key=f"2200629:{key}:parallel", variable_key=key, value=value, unit=unit,
            source_bill_no="2200629", available_at="2024-07-11", reviewed_at="2026-10-10",
            source_ref="2200629 비용추계서24C1054 PDF4~7쪽;2021보육실태조사·당시 시간제보육 지원한도",
            agency="보건복지부", policy_domain="손자녀돌보미", scope="낮시간 조부모양육 아동 대리모집단·양육수당 병행",
            service_function=PARALLEL, support_derivation=PARALLEL, grandparent_count_basis="child_age_proxy",
            grandparent_allowance_mode="allowance_parallel", variable_role="care_scenario_operand",
            allowed_routes=["direct_annual_amount"], requires_applicability_note=True,
            independently_verified=False, obtained_from="reviewed_answer",
            limitation="2021비율·당시80시간/3000원 준용, 전원등록·12개월·단가동결 가정. 실제 시설미이용자 확정수 및 최신 고정가격 아님"))
    return rows
