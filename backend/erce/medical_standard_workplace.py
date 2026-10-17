"""Formal non-estimation and reference-only medical-corporation subsidy model."""
from math import ceil,isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="medical_standard_workplace_reference"


def medical_workplace_rows():
    common=dict(source_bill_no="2204655",available_at="2024-11-15",reviewed_at="2026-10-10",
        source_ref="2204655 비용추계서24B4305 PDF4~6쪽;2024.3의료법인현황·2025설립보조계획안",
        agency="고용노동부",policy_domain="의료법인 표준사업장",scope="의료법인 자회사형 신규설립보조 참고시나리오",
        service_function=PROFILE,support_derivation=PROFILE,variable_role="medical_workplace_reference_operand",
        allowed_routes=[PROFILE],requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="신청·예산확대·인증유지 참고가정. 공식미첨부 판단과 별개, 실제지출확정 아님")
    values=[("medical_corporation_reference_count",1617,"corporation"),
            ("medical_annual_participation_share",.001,"ratio"),
            ("standard_grant_unit",300000000,"KRW/workplace"),
            ("standard_grant_cpi",{"2025":.021,"2026":.02,"2027":.02,"2028":.02,"2029":.02,"2030":.02},"year_to_ratio")]
    rows=[evidence_row(evidence_key=f"2204655:{k}:reference",variable_key=k,value=v,unit=u,**common) for k,v,u in values]
    for row in rows:
        if row["variable_key"]=="standard_grant_unit":row["price_year"]=2025
    return rows


def prepare_medical_workplace(payload):
    if payload.get("route_key")!=PROFILE or payload.get("workplace_form")!="medical_corporation_subsidiary":
        raise ValueError("medical subsidiary establishment grant scope required")
    notes=("medical_workplace_scope_note","medical_application_note","medical_budget_note","medical_support_basis_note")
    if payload.get("medical_reference_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload,"support_missing_operands":["medical_workplace_reference_confirmation"],"support_derivation_trace":[]}
    if payload.get("budget_expansion_assumed") is not True or payload.get("medical_certification_retention")!=1:
        return {**payload,"support_missing_operands":["medical_budget_retention_confirmation"],"support_derivation_trace":[]}
    mode=payload.get("medical_support_mode")
    if mode not in {"annual_new_establishments","cumulative_support_reference"}:
        raise ValueError("annual new grants and cumulative support must be separated")
    if mode=="cumulative_support_reference" and (payload.get("bill_no")!="2204655" or payload.get("evidence_mode")!="development_review"
            or payload.get("cumulative_source_replay_confirmed") is not True):
        raise ValueError("unverified cumulative support is own-bill source replay only")
    start=payload.get("start_year");years=payload.get("years",5);base=payload.get("standard_grant_price_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"],"support_derivation_trace":[]}
    if any(isinstance(x,bool) or not isinstance(x,int) for x in (start,years,base)) or years<1 or start<=base:
        raise ValueError("invalid medical reference period/price year")
    units=dict(medical_corporation_reference_count="corporation",medical_annual_participation_share="ratio",
               standard_grant_unit="KRW/workplace",standard_grant_cpi="year_to_ratio")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("subsidy_rate","growth_rate","grant_cap")):
        raise ValueError("average support grant cannot add extra subsidy/cap/index")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        xs=list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in xs):
            raise ValueError("invalid medical workplace operand/unit")
    v={k:row.value for k,row in r.items()}
    if not 0<=v["medical_annual_participation_share"]<=1 or v["medical_corporation_reference_count"]!=int(v["medical_corporation_reference_count"]):
        raise ValueError("invalid corporation count/application share")
    price_row=(payload.get("selected_variable_inputs") or {}).get("standard_grant_unit",{})
    if "standard_grant_unit" not in (payload.get("explicit_inputs") or {}) and price_row.get("price_year") is not None and price_row["price_year"]!=base:
        raise ValueError("medical grant price vintage mismatch")
    yearly_new=ceil(v["medical_corporation_reference_count"]*v["medical_annual_participation_share"])
    rates=v["standard_grant_cpi"];annual=[];trace=[]
    for i in range(years):
        year=start+i
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(base+1,year+1)):
            return {**payload,"support_missing_operands":["medical_grant_cpi_year_coverage"],"support_derivation_trace":[]}
        supported=yearly_new*(i+1) if mode=="cumulative_support_reference" else yearly_new
        price=v["standard_grant_unit"]*prod(1+rates[str(y)] for y in range(base+1,year+1))
        annual.append(supported*price)
        trace.append(dict(year=year,annual_new_workplaces=yearly_new,supported_workplaces=supported,
            grant_per_workplace=price,annual_won=annual[-1],support_mode=mode,estimate_purpose="reference_scenario",
            source_basis_note=payload["medical_support_basis_note"]))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace,
        "estimate_purpose":"reference_scenario","reference_notice":"공식미첨부 판단과 별도의 가정에 따른 참고금액. 확정된 예산이나 수요 추계가 아닙니다."}
