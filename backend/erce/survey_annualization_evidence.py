"""Annual survey expense minus already scheduled surveys under the old law."""
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="survey_annualization_delta"
ROUTE="research_survey_annualization_delta"
NOTES=("survey_task_scope_note","survey_phase_note","survey_price_note")


def survey_annualization_rows():
    common=dict(source_bill_no="2207176",available_at="2025-01-07",reviewed_at="2026-10-11",
        source_ref="2207176 비용추계서24C6463 PDF3~4쪽,2023보호종료아동 자립지원실태조사",
        agency="보건복지부",policy_domain="보호종료아동 자립지원실태조사",scope="전국 자립지원실태조사 단가·실시이력",
        service_function=PROFILE,support_derivation=PROFILE,research_service_function="care_leaver_independent_living_survey",
        variable_role="survey_annualization_operand",allowed_routes=[ROUTE],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="2023사업예산·실시이력과2024.12전망 준용. 신규법안 과업·관측시점·시행시점 확인 필요,최신요금 아님")
    specs=[("survey_unit_cost",200000000,"KRW/survey"),("survey_price_base_year",2023,"year"),
        ("last_survey_year",2023,"year"),
        ("survey_cpi_rates",{"2024":.025,"2025":.021,"2026":.02,"2027":.02,"2028":.02,"2029":.02,"2030":.02},"year_to_ratio")]
    return [evidence_row(**common,evidence_key=f"2207176:{k}:reviewed",variable_key=k,value=v,unit=u) for k,v,u in specs]


def prepare_survey_annualization(payload):
    if payload.get("route_key")!=ROUTE:
        raise ValueError("annualization delta route required")
    if payload.get("survey_annualization_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["survey_annualization_confirmation"],"support_derivation_trace":[]}
    start,years=payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("survey horizon required")
    units={r["variable_key"]:r["unit"] for r in survey_annualization_rows()}
    units.update(existing_survey_interval="year",amended_survey_interval="year")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","duration")):
        raise ValueError("survey CPI already applied; no duplicate growth or duration")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        values=list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in values):
            raise ValueError("invalid survey operand/unit")
    v={k:row.value for k,row in r.items()}
    for k in ("existing_survey_interval","amended_survey_interval","last_survey_year","survey_price_base_year"):
        if v[k]!=int(v[k]):
            raise ValueError("survey dates and cycles must be integers")
    if v["existing_survey_interval"]<1 or v["amended_survey_interval"]!=1:
        raise ValueError("this leaf supports annualization only; other frequency changes require a separate signed-delta model")
    if v["last_survey_year"]>=start or v["survey_price_base_year"]>=start:
        raise ValueError("baseline survey and price observations must predate the horizon")
    base=v["survey_price_base_year"];last=v["last_survey_year"];rates=v["survey_cpi_rates"];annual=[];trace=[]
    for year in range(start,start+years):
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(base+1,year+1)):
            return {**payload,"support_missing_operands":["survey_price_year_coverage"],"support_derivation_trace":[]}
        price=v["survey_unit_cost"]*prod(1+rates[str(y)] for y in range(base+1,year+1))
        existing=(year-last)%v["existing_survey_interval"]==0
        old=price if existing else 0;delta=price-old;annual.append(delta)
        trace.append(dict(year=year,survey_unit_won=price,new_survey_cost_won=price,existing_survey_cost_won=old,
            annual_delta_won=delta,baseline_survey_due=existing,last_observed_survey_year=last,
            existing_interval=v["existing_survey_interval"],amended_interval=1))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
