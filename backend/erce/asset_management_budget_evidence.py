"""Confirmed whole-program budget proxy with explicit price timing."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "asset_management_annual_budget_proxy"
NOTES = ("asset_task_scope_note", "asset_scale_note", "asset_staffing_note", "asset_price_note")


def asset_management_budget_rows():
    common = dict(source_bill_no="2207509", available_at="2025-02-03", reviewed_at="2026-10-12",
        source_ref="2207509 비용추계서25C0255 PDF2~3쪽", agency="보건복지부",
        policy_domain="아동·발달장애인 자산관리 신탁지원", scope="재산관리 지원서비스 전체 연간예산 준용",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="whole_program_budget_operand",
        allowed_routes=[PROFILE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer",
        limitation="2024 시범사업 예산 선례. 최신 공식단가·아동당 단가 아님. 대상·규모·과업·무증원 조건 확인 필요")
    specs = [("asset_reference_annual_budget",460000000,"KRW/year"),
             ("asset_budget_observation_year",2024,"year"),
             ("asset_budget_cpi_rates",{str(y):.021 if y==2025 else .02 for y in range(2025,2031)},"year_to_ratio")]
    return [evidence_row(**common,evidence_key=f"2207509:{k}:reviewed",
                        variable_key=k,value=v,unit=u) for k,v,u in specs]


def prepare_asset_management_budget(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("asset budget route required")
    if (payload.get("asset_budget_proxy_confirmed") is not True
            or payload.get("asset_existing_agency_no_expansion") is not True
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["asset_budget_scope_confirmation"],"support_derivation_trace":[]}
    units = {r["variable_key"]:r["unit"] for r in asset_management_budget_rows()}
    units["asset_price_adjustment_first_year"] = "year"
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","headcount","salary_per_person")):
        raise ValueError("whole-program budget: no duplicate staffing/CPI")
    r,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        values = list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if (row.unit != units[k] or not row.source_ref or any(isinstance(x,bool)
                or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in values)):
            raise ValueError("invalid asset budget operand")
    v = {k:row.value for k,row in r.items()}
    start,years = payload.get("start_year"),payload.get("years",5)
    first,base = v["asset_price_adjustment_first_year"],v["asset_budget_observation_year"]
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1 or first!=int(first) or base!=int(base)
            or not base<first<=start):
        raise ValueError("explicit price adjustment horizon required")
    rates,annual,trace = v["asset_budget_cpi_rates"],[],[]
    for year in range(start,start+years):
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(int(first),year+1)):
            return {**payload,"support_missing_operands":["asset_budget_cpi_year_coverage"],"support_derivation_trace":[]}
        amount = v["asset_reference_annual_budget"]*prod(1+rates[str(y)] for y in range(int(first),year+1))
        annual.append(amount)
        trace.append(dict(year=year,reference_budget_won=v["asset_reference_annual_budget"],
            budget_observation_year=int(base),price_adjustment_first_year=int(first),
            annual_amount_won=amount,staffing_expansion_assumed=False,whole_program_proxy=True))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(x.source_ref for x in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
