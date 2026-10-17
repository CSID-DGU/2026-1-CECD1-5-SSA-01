"""Initial unlicensed stock, later entrants, then regular-exam retakes."""
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="qualification_exam_stock_flow"
NOTES=("exam_scope_note","exam_population_note","exam_transition_note","exam_price_note","exam_start_note")


def qualification_exam_rows():
    common=dict(source_bill_no="2207043",available_at="2025-01-07",reviewed_at="2026-10-11",
        source_ref="2207043 비용추계서24C6328 PDF3~6쪽",agency="보건복지부",
        policy_domain="발달재활사 자격시험",scope="첫해미자격자특례시험·이후신규제공인원·정규시험재응시",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],variable_role="exam_operand",
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="언어재활사 유사시험과 시행계획의 선례가정. 시험종류·특례운영·비용포함범위 확인 필요; 최신공식응시료 아님")
    specs=[("exam_reference_annual_cost",662000000,"KRW/year"),("exam_reference_candidates",2760,"person"),
        ("exam_price_base_year",2023,"year"),("exam_initial_unlicensed_share",.513,"ratio"),
        ("exam_new_provider_eligibility_share",1,"ratio"),("exam_regular_failure_share",.32,"ratio"),
        ("exam_cpi_rates",{"2024":.025,"2025":.021,"2026":.02,"2027":.02,"2028":.02,"2029":.02,"2030":.02,"2031":.02},"year_to_ratio")]
    rows=[evidence_row(**common,evidence_key=f"2207043:{k}:reviewed",variable_key=k,value=v,unit=u) for k,v,u in specs]
    rows[-1]["limitation"]="2024.12 CPI 전망 및 표4 단가의2031동일2%연장 가정. 원경제전망의2031값을독립확인한것아님"
    rows.append(evidence_row(**{**common,"variable_role":"target_population_projection","limitation":"정답표2 미래제공인원 전망.2021~2023원관측값·추세식 미공개로 아직재구성못함;다른의안후보인원으로전용금지"},
        evidence_key="2207043:service_provider_forecast:2027-2031:target_only",variable_key="service_provider_forecast",
        value={str(y):n for y,n in zip(range(2027,2032),[36188,37236,38161,38988,39736])},
        unit="year_to_person",reuse_policy="target_only",
        value_years=list(range(2027,2032))))
    return rows


def later_qualification_exam_projection_rows():
    # Same published projection, independently attributed to this later answer.
    # It remains target-only, never a reconstructed historical observation.
    return [evidence_row(evidence_key="2210347:service_provider_forecast:2027-2031:target_only",
        variable_key="service_provider_forecast",
        value={str(y):n for y,n in zip(range(2027,2032),[36188,37236,38161,38988,39736])},
        unit="year_to_person",source_bill_no="2210347",available_at="2025-06-30",
        reviewed_at="2026-10-12",source_ref="2210347 비용추계서25C2709 PDF3~4쪽 표2",
        agency="보건복지부",policy_domain="발달재활사 자격시험",
        scope="2027~2031 제공인원 전망·현재 의안 사후회귀 전용",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],
        variable_role="target_population_projection",reuse_policy="target_only",
        value_years=list(range(2027,2032)),requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="2021~2023 원관측·추세식 미확보. 미래정답전망을 다른의안에 전용하거나 과거관측으로 바꾸지 않음")]


def prepare_qualification_exam(payload):
    if payload.get("route_key")!=PROFILE:
        raise ValueError("qualification stock/flow route required")
    if payload.get("exam_model_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["exam_model_confirmation"],"support_derivation_trace":[]}
    if payload.get("exam_linked_dependency_present") is True and payload.get("exam_linked_bill_assumed_passed") is not True:
        return {**payload,"support_missing_operands":["exam_linked_bill_confirmation"],"support_derivation_trace":[]}
    if payload.get("exam_special_all_pass_assumed") is not True:
        return {**payload,"support_missing_operands":["exam_special_pass_assumption"],"support_derivation_trace":[]}
    start,years=payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("exam first-implementation year required")
    units={r["variable_key"]:r["unit"] for r in qualification_exam_rows()}
    units["exam_special_duration_years"]="year"
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","frequency_per_year")):
        raise ValueError("exam unit price and annual attempts already include frequency/growth")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        values=list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in values):
            raise ValueError("invalid qualification exam operand/unit")
    v={k:row.value for k,row in r.items()}
    base=v["exam_price_base_year"];duration=v["exam_special_duration_years"]
    if base!=int(base) or base>=start or duration!=int(duration) or duration<0 or v["exam_reference_candidates"]<=0:
        raise ValueError("exam price-year/candidate count/transition duration invalid")
    if any(not 0<=v[k]<=1 for k in ("exam_initial_unlicensed_share","exam_new_provider_eligibility_share","exam_regular_failure_share")):
        raise ValueError("exam eligibility and failure shares must be ratios")
    population=v["service_provider_forecast"];rates=v["exam_cpi_rates"]
    if not isinstance(population,dict) or any(str(y) not in population for y in range(start,start+years)):
        return {**payload,"support_missing_operands":["service_provider_forecast_year_coverage"],"support_derivation_trace":[]}
    if any(n!=int(n) for n in population.values()):
        raise ValueError("provider forecasts must use persons, not money or growth coefficients")
    annual=[];trace=[];previous_failures=0
    unit=v["exam_reference_annual_cost"]/v["exam_reference_candidates"]
    for i,year in enumerate(range(start,start+years)):
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(int(base)+1,year+1)):
            return {**payload,"support_missing_operands":["exam_cpi_year_coverage"],"support_derivation_trace":[]}
        if i==0:
            new=round(population[str(year)]*v["exam_initial_unlicensed_share"])
            basis="initial_unlicensed_stock"
        else:
            new=round(max(population[str(year)]-population[str(year-1)],0)*v["exam_new_provider_eligibility_share"])
            basis="net_new_providers"
        retakes=previous_failures
        candidates=new+retakes
        special=i<duration
        failures=0 if special else round(candidates*v["exam_regular_failure_share"])
        price=unit*prod(1+rates[str(y)] for y in range(int(base)+1,year+1))
        amount=candidates*price;annual.append(amount)
        trace.append(dict(year=year,service_providers=population[str(year)],new_candidates=new,retake_candidates=retakes,
            total_candidates=candidates,failed_candidates=failures,exam_type="special" if special else "regular",
            quantity_basis=basis,unit_price_won=price,amount_won=amount,
            projection_source_class=r["service_provider_forecast"].source_class))
        previous_failures=failures
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
