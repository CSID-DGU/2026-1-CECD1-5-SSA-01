"""Reusable lower calculations for basic/parent benefits indexed with floors.

No target totals are stored. Parent population proxy requires review, rather
than treating population as independently observed recipient counts.
"""
from math import isfinite, prod

from backend.erce.child_allowance_evidence import child_allowance_rows
from backend.erce.child_allowance_indexed_evidence import child_allowance_indexed_rows
from backend.erce.parent_benefit_evidence import parent_benefit_rows
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

CHILD_PROFILE = "child_allowance_under18_indexed_floor"
PARENT_PROFILE = "parent_benefit_age_indexed_floor"
CHILD_KEYS = (
    "2200147:under18_population:2025-2029:family_indexed",
    "2200147:under8_population:2025-2029:family_indexed",
    "2200147:child_allowance_payment_rate:2024:family_indexed",
    "2204028:index_base_monthly_amount:2024:family_indexed",
    "2204028:child_cpi_rates:2025-2029:family_indexed",
)
PARENT_CPI_KEY = "2204028:child_cpi_rates:2025-2029:parent_indexed"


def parent_keys(age):
    return (f"kosis_202312:age{age}_population:2025-2029:parent_indexed",
            f"mohw_parent_benefit:age{age}:2024_monthly:parent_indexed", PARENT_CPI_KEY)


def family_indexed_rows():
    source = {r["evidence_key"]:r for r in
              child_allowance_rows()+child_allowance_indexed_rows()+parent_benefit_rows()}
    rows=[]
    def alias(key, variable, profile, route, unit, **metadata):
        original=source[key.rsplit(":",1)[0]]
        rows.append({**original,"evidence_key":key,"variable_key":variable,"unit":unit,
            "alias_of":original["evidence_key"],"allowed_routes":[route],
            "support_derivation":profile,"reviewed_at":"2026-10-04",
            "scope":"전국 동일연령·같은2025~2029년·기준2024년 물가연동 비교",
            "service_function":profile,"child_population_geography":"전국",
            "child_allowance_scenario":"all_under18_indexed_parent_changed" if profile==CHILD_PROFILE else "parent_age_indexed",
            "limitation":original["limitation"]+"; 프로필·연령·기간·기준연도 및 지급범위 확인 필수. 원출처 값 재사용, 최신값 자동갱신 아님",
            **metadata})
    for key,variable,unit in zip(CHILD_KEYS,
            ("under18_population","under8_population","child_payment_rate","index_base_monthly_amount","child_cpi_rates"),
            ("person","person","ratio","KRW/person/month","ratio/year")):
        alias(key,variable,CHILD_PROFILE,"transfer_population_amount_delta",unit)
    for age in (0,1):
        pop,amount,_=parent_keys(age)
        alias(pop,"parent_population",PARENT_PROFILE,"transfer_recipient_delta","person",
            parent_benefit_age=age,parent_population_basis="forecast_population_proxy")
        alias(amount,"parent_base_monthly_amount",PARENT_PROFILE,"transfer_recipient_delta","KRW/person/month",
            parent_benefit_age=age,parent_population_basis="forecast_population_proxy",child_index_base_year=2024)
    alias(PARENT_CPI_KEY,"parent_cpi_rates",PARENT_PROFILE,"transfer_recipient_delta","ratio/year",
        parent_population_basis="forecast_population_proxy")
    return rows


def prepare_family_indexed_operands(payload):
    profile=payload["support_derivation"]
    child=profile==CHILD_PROFILE
    route="transfer_population_amount_delta" if child else "transfer_recipient_delta"
    if payload.get("route_key")!=route or not str(payload.get("support_derivation_note") or "").strip():
        raise ValueError("family indexed profile needs route and applicability note")
    if payload.get("child_population_geography")!="전국":
        raise ValueError("family indexed population geography must be confirmed")
    scenario="all_under18_indexed_parent_changed" if child else "parent_age_indexed"
    if payload.get("child_allowance_scenario")!=scenario:
        raise ValueError("family indexed scenario mismatch")
    if child and payload.get("parent_benefit_unchanged") is not False:
        raise ValueError("parent benefit change must be handled separately, not assumed unchanged")
    if not child and (payload.get("parent_benefit_age") not in (0,1)
            or isinstance(payload.get("parent_benefit_age"),bool)
            or payload.get("parent_population_basis")!="forecast_population_proxy"
            or not str(payload.get("parent_population_proxy_note") or "").strip()):
        raise ValueError("parent population proxy and age require confirmation")
    if not str(payload.get("family_index_scope_note") or "").strip():
        raise ValueError("family indexed scope, voucher overlap and floor need review")
    base=payload.get("child_index_base_year");start=payload.get("start_year")
    if isinstance(base,bool) or not isinstance(base,int) or (start is not None and start!=base+1):
        raise ValueError("family indexed start must follow confirmed base year")
    if start is not None and not str(payload.get("estimation_start_note") or "").strip():
        raise ValueError("family indexed estimation start needs separate basis")
    units=({"under18_population":"person","under8_population":"person","child_payment_rate":"ratio",
            "index_base_monthly_amount":"KRW/person/month","child_cpi_rates":"ratio/year"} if child else
           {"parent_population":"person","parent_base_monthly_amount":"KRW/person/month","parent_cpi_rates":"ratio/year"})
    units["minimum_monthly_amount"]="KRW/person/month"
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    resolved,missing=resolve_formula_variables(tuple(units),**layers)
    for layer in (layers["target_explicit"],layers["target_current_actual"],layers["official_standard"],
                  layers["calculated_estimate"],layers["precedent_assumption"]):
        if any(k in (layer or {}) for k in ("participation_rate","growth_rate","growth_rates_by_year")):
            raise ValueError("family indexed duplicate adjustment forbidden")
    top,_=resolve_formula_variables(("benefit_per_recipient","existing_benefit_per_recipient","payments_per_year"),**layers)
    for key,row in top.items():
        expected="month/year" if key=="payments_per_year" else "KRW/person/month"
        if row.unit!=expected or not row.source_ref:
            raise ValueError(f"{key}: expected sourced {expected}")
    years=int(payload.get("years") or 5);data={}
    for key,row in resolved.items():
        if row.unit!=units[key] or not row.source_ref:
            raise ValueError(f"{key}: expected sourced {units[key]}")
        values=list(row.value) if isinstance(row.value,(list,tuple)) else [row.value]*years
        cpi=key.endswith("cpi_rates")
        if len(values)!=years or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v)
                or (v<=-1 if cpi else v<0) or (units[key]=="ratio" and v>1) for v in values):
            raise ValueError(f"invalid family indexed operand: {key}")
        if key in {"index_base_monthly_amount","parent_base_monthly_amount","minimum_monthly_amount"} and len(set(values))!=1:
            raise ValueError("family indexed base and floor must be fixed values")
        data[key]=values
    if child and all(k in data for k in ("under18_population","under8_population")) and any(
            old>new for old,new in zip(data["under8_population"],data["under18_population"])):
        raise ValueError("inconsistent family age cohorts")
    calculated=dict(payload.get("calculated_inputs") or {});trace=[];dependencies={}
    def derive(key,deps,unit,expression,calc):
        dependencies[key]=deps
        if not all(d in data for d in deps):return
        values=[calc(i) for i in range(years)]
        upper,_=resolve_formula_variables((key,),**{**layers,"calculated_estimate":calculated})
        refs="; ".join(dict.fromkeys(resolved[d].source_ref for d in deps))
        if key not in upper:calculated[key]=dict(value=values,unit=unit,source_ref=refs,is_assumption=True)
        trace.append(dict(variable_key=key,dependencies=list(deps),expression=expression,values=values,
            unit=unit,source_ref=refs,applied=key not in upper,applicability_note=payload["support_derivation_note"]))
    if child:
        derive("new_recipient_count",("under18_population","child_payment_rate"),"person",
            "18세미만 인구×아동수당 지급률",lambda i:data["under18_population"][i]*data["child_payment_rate"][i])
        derive("existing_recipient_count",("under8_population","child_payment_rate"),"person",
            "현행8세미만 인구×동일 지급률",lambda i:data["under8_population"][i]*data["child_payment_rate"][i])
    else:
        derive("recipient_count",("parent_population",),"person",
            "확인한 해당연령 전망인구 준용; 실제 수급자 관측값 아님",lambda i:data["parent_population"][i])
        derive("existing_benefit_per_recipient",("parent_base_monthly_amount",),"KRW/person/month",
            "확인한2024년 연령별 공식 부모급여를 현행 시나리오에 동결",lambda i:data["parent_base_monthly_amount"][i])
    amount="index_base_monthly_amount" if child else "parent_base_monthly_amount"
    cpi="child_cpi_rates" if child else "parent_cpi_rates"
    derive("benefit_per_recipient",(amount,cpi,"minimum_monthly_amount"),"KRW/person/month",
        "max(확인한 법정하한, 기준월액×기준연도 다음해부터 누적∏(1+물가변동률)); 중간 표시 반올림 없음",
        lambda i:max(data["minimum_monthly_amount"][0],data[amount][0]*prod(1+v for v in data[cpi][:i+1])))
    _,top_missing=resolve_formula_variables(tuple(dependencies),**{**layers,"calculated_estimate":calculated})
    needed={d for key in top_missing for d in dependencies[key]}
    return {**payload,"calculated_inputs":calculated,"support_derivation_trace":trace,
            "support_missing_operands":[key for key in missing if key in needed]}
