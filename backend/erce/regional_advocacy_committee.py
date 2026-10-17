"""Case-volume-scaled appointed members, not a universal staffing rule."""
from decimal import Decimal,ROUND_HALF_UP
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="regional_advocacy_case_scaled_committee"
CASES={"서울":204,"부산":181,"대구":154,"인천":117,"광주":70,"대전":99,"울산":151,
    "세종":62,"경기":569,"강원":125,"충북":188,"충남":136,"전북":92,"전남":123,"경북":144,"경남":144,"제주":82}


def regional_advocacy_committee_rows():
    common=dict(source_bill_no="2202038",available_at="2024-08-01",reviewed_at="2026-10-06",
        source_ref="2202038 비용추계서24C2066 PDF4~5쪽표2~3;2022장애인학대현황·서울2024위원회·경기조례준용",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2202038/cost_estimate.pdf",
        agency="서울특별시·보건복지부",policy_domain="피해장애인통합지원협의회",scope="17시도지역협의회 위촉위원수당",
        service_function=PROFILE,support_derivation=PROFILE,committee_workload_proxy="suspected_cases_scaled_members",
        allowed_routes=["committee_components"],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="인원·28명상한·연2회·20만원동결은해당정답의비교가정.법정고정정원·최신공식수당아님.당연직공무원수당·인건비·사무국운영비추가를자동가정하지않음")
    rows=[]
    for key,value,unit in (
        ("regional_suspected_cases",CASES,"region_to_case"),
        ("reference_suspected_cases",204,"case"),
        ("reference_paid_members",23,"person"),
        ("maximum_paid_members",28,"person"),
        ("annual_meetings",2,"meeting/year"),
        ("meeting_allowance",200000,"KRW/person/meeting"),
    ):
        rows.append(evidence_row(evidence_key=f"2202038:{key}:reviewed",variable_key=key,value=value,unit=unit,
            variable_role="workload_observation" if key=="regional_suspected_cases" else "committee_assumption",**common,
            observation_year=2022 if "cases" in key else 2024,
            rounding_rule="half_up_after_cap",reference_region="서울"))
    return rows


def prepare_regional_advocacy_committee(payload):
    if payload.get("route_key")!="committee_components" or payload.get("committee_workload_proxy")!="suspected_cases_scaled_members":
        raise ValueError("regional committee route or workload model mismatch")
    if payload.get("committee_rounding")!="half_up_after_cap" or payload.get("public_officials_paid") is not False or any(
        not str(payload.get(k) or "").strip() for k in ("support_derivation_note","committee_scope_note","estimation_start_note")):
        raise ValueError("regional committee needs rounding, unpaid officials and applicability review")
    if any(k in (payload.get(l) or {}) for l in ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs")
           for k in ("growth_rate","growth_rates_by_year","participation_rate")):
        raise ValueError("regional committee freeze assumption forbids duplicate growth")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    upper,_=resolve_formula_variables(("committee_components",),**layers)
    if "committee_components" in upper:return {**payload,"support_missing_operands":[],"support_derivation_trace":[]}
    units=dict(regional_suspected_cases="region_to_case",reference_suspected_cases="case",reference_paid_members="person",
        maximum_paid_members="person",annual_meetings="meeting/year",meeting_allowance="KRW/person/meeting")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    for k,row in r.items():
        if row.unit!=units[k] or not row.source_ref:raise ValueError("regional committee unit/source mismatch")
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    cases=r["regional_suspected_cases"].value
    if not isinstance(cases,dict) or not cases or any(not isinstance(k,str) or not k.strip() or isinstance(v,bool)
        or not isinstance(v,(int,float)) or not isfinite(v) or v<0 for k,v in cases.items()):
        raise ValueError("invalid regional case counts")
    data={}
    for key in units:
        if key=="regional_suspected_cases":continue
        v=r[key].value
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:raise ValueError("invalid committee parameter")
        data[key]=v
    if data["reference_suspected_cases"]<=0:raise ValueError("reference case count must be positive")
    for key in ("reference_paid_members","maximum_paid_members"):
        if data[key]!=int(data[key]):raise ValueError("member parameters must be whole counts")
    if payload.get("reference_region") not in cases or cases[payload["reference_region"]]!=data["reference_suspected_cases"]:
        raise ValueError("reference region and denominator do not match")
    components=[];trace=[]
    for region,c in cases.items():
        raw=Decimal(str(data["reference_paid_members"]))*Decimal(str(c))/Decimal(str(data["reference_suspected_cases"]))
        capped=min(Decimal(str(data["maximum_paid_members"])),raw)
        paid=int(capped.quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        components.append(dict(paid_members=paid,annual_meetings=data["annual_meetings"],meeting_unit_price=data["meeting_allowance"]))
        trace.append(dict(region=region,suspected_cases=c,uncapped_members=float(raw),paid_members=paid,
            cap_applied=raw>data["maximum_paid_members"],rounding="half_up_after_cap",
            expression="round_half_up(min(상한,기준위촉위원×지역사례/기준사례))"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["committee_components"]=dict(value=components,unit="component_bundle",
        source_ref="; ".join(dict.fromkeys(v.source_ref for v in r.values())),is_assumption=True)
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
