"""Existing sampled survey versus an approved expanded annual survey budget."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "facility_survey_scope_expansion_delta"
NOTES = ("facility_scope_comparison_note", "facility_expansion_proxy_note",
         "facility_baseline_budget_note", "facility_price_note")


def facility_survey_expansion_rows():
    common = dict(source_bill_no="2210775",available_at="2025-06-30",reviewed_at="2026-10-12",
        source_ref="2210775 비용추계서25C3154 PDF2~3쪽",agency="보건복지부",
        policy_domain="장애인거주시설 인권실태조사",scope="기존 표본조사에서 규모확대 가정·기존예산 차감",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],
        variable_role="survey_expansion_operand",requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="정답에서 확인한 예산 선례. 확대조사5억원은2023편의시설전수조사 준용이며 인권조사 실제견적 아님.80/526으로 예산을 기계적으로 확대하지 않음")
    specs = [("expanded_survey_annual_budget",500000000,"KRW/year",2023),
             ("existing_survey_annual_budget",100000000,"KRW/year",2025),
             ("existing_survey_covered_facilities",80,"facility",2025),
             ("reference_government_funded_facilities",526,"facility",2024)]
    return [evidence_row(**common,evidence_key=f"2210775:{k}:reviewed",variable_key=k,
        value=v,unit=u,observation_year=y,approximate=(k=="existing_survey_covered_facilities"))
        for k,v,u,y in specs]


def prepare_facility_survey_expansion(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("facility expansion route required")
    if (payload.get("facility_expansion_scenario_confirmed") is not True
            or payload.get("facility_price_mode") != "freeze_reference_budget"
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["facility_expansion_confirmation"],
                "support_derivation_trace":[]}
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","frequency_per_year","quantity","unit_cost")):
        raise ValueError("annual fixed survey budgets already include frequency and scale")
    units = {r["variable_key"]:r["unit"] for r in facility_survey_expansion_rows()}
    r,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        if (row.unit!=units[k] or not row.source_ref or isinstance(row.value,bool)
                or not isinstance(row.value,(int,float)) or not isfinite(row.value) or row.value<0):
            raise ValueError("invalid survey expansion evidence")
    v = {k:row.value for k,row in r.items()}
    if (v["existing_survey_covered_facilities"]<=0
            or v["existing_survey_covered_facilities"]>=v["reference_government_funded_facilities"]):
        raise ValueError("sample expansion scenario requires verified incomplete existing coverage")
    new,old = v["expanded_survey_annual_budget"],v["existing_survey_annual_budget"]
    if new<old:
        raise ValueError("budget reduction requires a separate signed-delta route")
    start,years = payload.get("start_year"),payload.get("years",5)
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1):
        raise ValueError("survey horizon required")
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=[new-old]*years,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(x.source_ref for x in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
        "support_derivation_trace":[dict(year=y,expanded_budget_won=new,existing_budget_won=old,
            incremental_cost_won=new-old,current_sample_facilities=v["existing_survey_covered_facilities"],
            reference_facilities=v["reference_government_funded_facilities"],
            expansion_is_assumption=True,price_frozen=True) for y in range(start,start+years)]}
