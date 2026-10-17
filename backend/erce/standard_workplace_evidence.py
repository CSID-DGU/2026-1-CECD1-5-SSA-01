"""Regulatory eligibility expansion -> additional annual establishment grants."""
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "standard_workplace_subsidy_expansion"


def standard_workplace_rows():
    common = dict(source_bill_no="2200200", available_at="2024-06-19", reviewed_at="2026-10-10",
        source_ref="2200200 비용추계서24B0480 PDF4~7쪽;2024지원계획·2023일반/자회사 실적",
        agency="고용노동부", policy_domain="장애인표준사업장 설립지원", scope="자회사형 추가신청 신규설립 보조",
        service_function=PROFILE, support_derivation=PROFILE, workplace_form="subsidiary_joint_investment",
        variable_role="standard_workplace_operand", allowed_routes=[PROFILE], requires_applicability_note=True,
        independently_verified=False, obtained_from="reviewed_answer",
        limitation="규제완화가 신규신청으로 이어지고 예산을 확대하는 참고가정. 고정예산내배분이면 추가지출없을수있음. 민간출자금 아님")
    values = [("standard_planned_general_subsidiary", 170, "workplace/year"),
              ("standard_previous_general", 74, "workplace"), ("standard_previous_subsidiary", 64, "workplace"),
              ("standard_grant_unit", 295000000, "KRW/workplace"),
              ("standard_grant_cpi", {"2025": .022, "2026": .022, "2027": .021, "2028": .021, "2029": .021}, "year_to_ratio")]
    rows = [evidence_row(evidence_key=f"2200200:{k}:reviewed", variable_key=k, value=v, unit=u, **common) for k,v,u in values]
    for scenario, rate in (("increase1", .01), ("increase5", .05), ("increase10", .1)):
        rows.append(evidence_row(evidence_key=f"2200200:standard_application_rate:{scenario}",
            variable_key="standard_application_rate", value=rate, unit="ratio", application_growth_scenario=scenario,
            **{**common, "variable_role": "application_scenario",
               "limitation": "매년기준물량의1/5/10% 고정증분, 복리나누적기존사업장 재지원 아님"}))
    for row in rows:
        if row["variable_key"] in {"standard_grant_unit", "standard_grant_cpi"}:
            # 가격과 물가는 동일 설립지원 과업이면 검토 가능하다. 물량은 여전히 출자형별로 제한한다.
            row.pop("workplace_form", None)
            row["support_derivation"] = ""
            row["allowed_routes"] = [PROFILE, "medical_standard_workplace_reference"]
            if row["variable_key"] == "standard_grant_unit": row["price_year"] = 2024
    return rows


def prepare_standard_workplace(payload):
    if payload.get("route_key") != PROFILE or payload.get("workplace_form") != "subsidiary_joint_investment":
        raise ValueError("subsidiary grant scope required, not government equity")
    notes = ("workplace_indirect_scope_note", "workplace_quantity_note", "workplace_budget_note", "workplace_price_note")
    if payload.get("workplace_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["workplace_expansion_confirmation"], "support_derivation_trace": []}
    if payload.get("budget_expansion_assumed") is not True:
        return {**payload, "support_missing_operands": ["budget_expansion_confirmation"], "support_derivation_trace": []}
    if payload.get("application_increase_mode") != "fixed_annual_increment_from_base":
        raise ValueError("new establishment grants cannot compound/repeat old grants")
    start = payload.get("start_year"); years = payload.get("years", 5); base_year = payload.get("standard_grant_price_year")
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if any(isinstance(x,bool) or not isinstance(x,int) for x in (start,years,base_year)) or years<1 or start<=base_year:
        raise ValueError("invalid grant period/price basis")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("subsidy_rate","growth_rate","grant_cap")):
        raise ValueError("average aid is not investment cost: no extra75% or cap/index")
    direct,_ = resolve_formula_variables(("annual_additional_workplaces",), **layers)
    units = dict(standard_grant_unit="KRW/workplace",standard_grant_cpi="year_to_ratio")
    if not direct:
        units.update(standard_planned_general_subsidiary="workplace/year",standard_previous_general="workplace",
                     standard_previous_subsidiary="workplace",standard_application_rate="ratio")
    r,missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    def valid(x):
        return not isinstance(x,bool) and isinstance(x,(int,float)) and isfinite(x) and x>=0
    for k,row in r.items():
        xs=list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid standard workplace operand/unit")
    v={k:row.value for k,row in r.items()}
    def rounded(x):
        return int(Decimal(str(x)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
    reference=None
    if direct:
        row=direct["annual_additional_workplaces"]
        if row.unit!="workplace/year" or not row.source_ref or not valid(row.value) or row.value!=int(row.value):
            raise ValueError("confirmed extra applications require unit/source/integer")
        extra=int(row.value)
    else:
        previous=v["standard_previous_general"]+v["standard_previous_subsidiary"]
        if previous<=0 or not 0<=v["standard_application_rate"]<=1:
            raise ValueError("invalid reference composition/application rate")
        reference=rounded(v["standard_planned_general_subsidiary"]*v["standard_previous_subsidiary"]/previous)
        extra=rounded(reference*v["standard_application_rate"])
    rates=v["standard_grant_cpi"]; annual=[];trace=[]
    for i in range(years):
        year=start+i
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(base_year+1,year+1)):
            return {**payload,"support_missing_operands":["standard_grant_cpi_year_coverage"],"support_derivation_trace":[]}
        price=v["standard_grant_unit"]*prod(1+rates[str(y)] for y in range(base_year+1,year+1))
        annual.append(extra*price)
        trace.append(dict(year=year,reference_subsidiary_workplaces=reference,additional_applications=extra,
            grant_per_new_workplace=price,annual_won=annual[-1],repeated_existing_grants=False,
            budget_expansion_assumed=True,indirect_scope_note=payload["workplace_indirect_scope_note"]))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
