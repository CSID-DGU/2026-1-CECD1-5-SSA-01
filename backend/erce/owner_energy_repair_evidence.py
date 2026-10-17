"""Grouped owner-house repair increments; annual recipient flows already include repair cycles."""
from decimal import Decimal,ROUND_HALF_UP
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="owner_energy_repair_grouped"


def energy_repair_rows():
    rows=[]
    data=[
        ("repair_household_history",{"light":[11915,11779,11632],"medium":[4317,4674,5581],"heavy":[3375,2574,3137]},"class_to_households"),
        ("old_building_share",.654,"ratio"),
        ("repair_increment_base",{"light":600000,"medium":1800000,"heavy":3000000},"class_to_KRW/household"),
        ("repair_cpi",{"2026":.019,**{str(y):.02 for y in range(2027,2032)}},"year_to_ratio"),
    ]
    for key,value,unit in data:
        rows.append(evidence_row(evidence_key=f"2211430:{key}:reviewed",variable_key=key,value=value,unit=unit,
            source_bill_no="2211430",available_at="2025-11-28",reviewed_at="2026-10-08",
            source_ref="2211430 비용추계서25B3733 PDF5~8쪽 표2~6",
            agency="국토교통부",policy_domain="자가주택고효율수선급여",scope="연간경·중·대보수지원가구,준공15년이상주택",
            service_function=PROFILE,support_derivation=PROFILE,variable_role="grouped_repair_operand",
            allowed_routes=["direct_annual_amount"],requires_applicability_note=True,
            independently_verified=False,obtained_from="reviewed_answer",
            repair_recipient_scope="owner_annual_repair_flow",repair_increment_base_year=2025,
            limitation="2022~2024연간지원실적·주택노후비중·유사사업추가단가/전망.최신고시단가아님.중보수180만원은60/300중간값가정"))
    return rows


def prepare_energy_repair(payload):
    if payload.get("route_key")!="direct_annual_amount" or payload.get("repair_recipient_scope")!="owner_annual_repair_flow":
        raise ValueError("energy repair route/owner-flow scope mismatch")
    if payload.get("repair_payment_scenario")!="upper_bound_100" or payload.get("repair_counts_rounding")!="half_up":
        raise ValueError("energy repair upper-bound and rounding need confirmation")
    if not all(str(payload.get(k) or "").strip() for k in
               ("support_derivation_note","annual_flow_note","repair_income_scope_note","repair_price_year_note","estimation_start_note")):
        raise ValueError("energy repair applicability notes required")
    start=payload.get("start_year");years=payload.get("years",5);base=payload.get("repair_increment_base_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"]}
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("invalid energy repair period")
    if isinstance(base,bool) or not isinstance(base,int) or base>=start:raise ValueError("energy repair base year mismatch")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in
           ("repair_cycle","participation_rate","growth_rate","growth_rates_by_year","subsidy_rate")):
        raise ValueError("energy repair annual flow or growth double adjustment")
    units={"repair_household_history":"class_to_households","old_building_share":"ratio",
        "repair_increment_base":"class_to_KRW/household","repair_cpi":"year_to_ratio"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        if row.unit!=units[k] or not row.source_ref:raise ValueError("energy repair source/unit mismatch")
    v={k:row.value for k,row in r.items()};groups=("light","medium","heavy")
    hist=v["repair_household_history"];prices=v["repair_increment_base"];rates=v["repair_cpi"];share=v["old_building_share"]
    if not isinstance(hist,dict) or set(hist)!=set(groups) or not isinstance(prices,dict) or set(prices)!=set(groups) or not isinstance(rates,dict):
        raise ValueError("energy repair class mapping mismatch")
    if isinstance(share,bool) or not isinstance(share,(int,float)) or not isfinite(share) or not 0<=share<=1:
        raise ValueError("invalid old-building proportion")
    for group in groups:
        vals=hist[group]
        if not isinstance(vals,list) or len(vals)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in vals):
            raise ValueError("energy repair needs three-year annual class counts")
        p=prices[group]
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not isfinite(p) or p<0:
            raise ValueError("invalid energy repair increment")
    if any(str(y) not in rates for y in range(base+1,start+years)):
        return {**payload,"support_missing_operands":["repair_cpi_year_coverage"]}
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<=-1 for x in rates.values()):
        raise ValueError("invalid energy repair CPI")
    counts={g:int((sum(Decimal(str(x)) for x in hist[g])/3*Decimal(str(share))).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) for g in groups}
    annual=[];trace=[]
    for i in range(years):
        factor=prod(1+rates[str(y)] for y in range(base+1,start+i+1))
        parts={g:counts[g]*prices[g]*factor for g in groups};annual.append(sum(parts.values()))
        trace.append(dict(year=start+i,eligible_households=counts,base_increment_won=prices,cpi_factor=factor,
            grouped_amounts_won=parts,annual_won=annual[-1],income_payment_share=1,
            expression="Σ(round(종류별최근3년지원평균×노후비중)×종류별추가단가×CPI),수선주기재분할없음"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
