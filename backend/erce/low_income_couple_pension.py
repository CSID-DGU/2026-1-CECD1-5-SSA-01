"""Conditional shares retain type-specific denominators; unknown effects stay missing."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="low_income_couple_pension"
GROUPS={"no_nr_full":.485,"no_nr_reduced":0,"nr_full":.296,"nr_reduced":.045,"occupational_special":.716}


def low_income_couple_rows():
    common=dict(source_bill_no="2213794",available_at="2025-12-02",reviewed_at="2026-10-06",
        source_ref="2213794 비용추계서25C5764 PDF4쪽표3·4",
        agency="국회예산정책처·보건복지부",policy_domain="기초연금",scope="전국소득하위40% 부부2인2027~2031",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=["transfer_recipient_delta"],
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer")
    rows=[]
    for group,share in GROUPS.items():
        rows.append(evidence_row(evidence_key=f"2213794:{group}:conditional_low_income_share:2022-2024",
            variable_key="conditional_low_income_share",value=share,unit="ratio",**common,
            variable_role="conditional_population_share",pension_group=group,low_income_scope="overall_elderly_bottom40",
            observation_years=[2022,2023,2024],valid_from_year=2027,valid_to_year=2031,
            denominator="해당유형기초연금수급자명",display_precision_percentage_points=.1,
            limitation="유형별조건부비율이며전체수급자비율아님.합계를1로정규화하지않음.0.0%는표시정밀도이하를포함할수있어법적대상0으로확정금지"))
    rows.append(evidence_row(evidence_key="2213794:standard_monthly:2027-2031:202509",
        variable_key="low_income_pension_standard",value=[355960,362930,370180,377580,385130],unit="KRW/person/month",**common,
        variable_role="forecast_standard",value_years=list(range(2027,2032)),
        pension_standard_vintage="2025_09_reviewed_forecast",
        limitation="2025기준342510원·2025.9전망의역사적기준액.최신고시·감액후실제지급액아님"))
    return rows


def prepare_low_income_couple(payload):
    group=payload.get("pension_group")
    if payload.get("route_key")!="transfer_recipient_delta" or group not in GROUPS or payload.get("start_year")!=2027 or payload.get("years")!=5:
        raise ValueError("low-income pension route/group/period mismatch")
    if payload.get("low_income_scope")!="overall_elderly_bottom40" or payload.get("pension_standard_vintage")!="2025_09_reviewed_forecast" or any(
        not str(payload.get(k) or "").strip() for k in ("support_derivation_note","pension_denominator_note","pension_increment_factor_note")):
        raise ValueError("review conditional denominator and actual increment factor")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("duplicate low-income adjustment")
    units=dict(conditional_low_income_share="ratio",pension_type_recipients="person",pension_increment_factor="ratio",
        low_income_pension_standard="KRW/person/month",old_couple_reduction="ratio",new_couple_reduction="ratio")
    r,missing=resolve_formula_variables(tuple(units),**layers);data={}
    for key,row in r.items():
        vals=list(row.value) if isinstance(row.value,(list,tuple)) else [row.value]*5
        if row.unit!=units[key] or not row.source_ref or len(vals)!=5 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0 or (units[key]=="ratio" and v>1) for v in vals):
            raise ValueError("invalid low-income operand")
        data[key]=vals
    if "new_couple_reduction" in data and data["new_couple_reduction"]!=[.15,.15,.15,.1,.1]:raise ValueError("wrong legal reduction schedule")
    if "old_couple_reduction" in data and data["old_couple_reduction"]!=[.2]*5:raise ValueError("wrong existing reduction")
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    deps=dict(recipient_count=("pension_type_recipients","conditional_low_income_share","pension_increment_factor"),
        benefit_per_recipient=("low_income_pension_standard","new_couple_reduction"),
        existing_benefit_per_recipient=("low_income_pension_standard","old_couple_reduction"))
    for key,dependencies in deps.items():
        if not all(k in data for k in dependencies):continue
        if key=="recipient_count":
            if group=="no_nr_reduced" and payload.get("accept_printed_zero_as_scenario") is not True:continue
            vals=[data["pension_type_recipients"][i]*data["conditional_low_income_share"][i]*data["pension_increment_factor"][i] for i in range(5)]
            expression="해당유형인원×유형내저소득비율×실제회복액계수;회복액가중인원"
        else:
            reduction="new_couple_reduction" if key=="benefit_per_recipient" else "old_couple_reduction"
            vals=[p*(1-d) for p,d in zip(data["low_income_pension_standard"],data[reduction])]
            expression="기준액×(1−부부감액률);실제차액은가중인원계수에서반영"
        upper,_=resolve_formula_variables((key,),**{**layers,"calculated_estimate":calculated})
        ref="; ".join(dict.fromkeys(r[d].source_ref for d in dependencies));unit="person" if key=="recipient_count" else "KRW/person/month"
        if key not in upper:calculated[key]=dict(value=vals,unit=unit,source_ref=ref,is_assumption=True)
        trace.append(dict(variable_key=key,expression=expression,values=vals,unit=unit,source_ref=ref,applied=key not in upper))
    _,top_missing=resolve_formula_variables(tuple(deps),**{**layers,"calculated_estimate":calculated})
    needed={d for key in top_missing for d in deps[key]}
    pending=[k for k in missing if k in needed]
    if group=="no_nr_reduced" and "recipient_count" in top_missing and payload.get("accept_printed_zero_as_scenario") is not True:
        pending.append("printed_zero_precision_review")
    return {**payload,"calculated_inputs":calculated,"support_derivation_trace":trace,"support_missing_operands":pending}
