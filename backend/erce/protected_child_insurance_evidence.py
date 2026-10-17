"""Protected-child share times an explicit age cohort; flag answer-age conflicts."""
from math import isfinite
from backend.erce.common_population_evidence import single_age_population_matrix
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE = "protected_child_insurance_population_share"
NOTES = ("protected_child_scope_note","protected_child_share_note","protected_child_premium_note")


def protected_child_insurance_rows():
    common = dict(source_bill_no="2216665",available_at="2026-04-15",reviewed_at="2026-10-14",
        source_ref="2216665 비용추계서26C0846 PDF3쪽",agency="보건복지부",
        policy_domain="시설보호아동 상해보험료",scope="기존가정위탁 제외·시설보호아동 비중대리",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],
        variable_role="protected_child_insurance_operand",requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer")
    premium = evidence_row(**common,evidence_key="2216665:protected_child:annual_premium:2025",
        variable_key="protected_child_annual_premium",value=68500,unit="KRW/person/year",
        limitation="2025가정위탁아동 보험료 연68500원내외를 시설아동에 준용. 미래가격동결·전액지원은 가정이며 계약견적 아님")
    premium.update(source_ref="공식2025복지안내책자 아동·청소년 가정위탁아동상해보험료",
        source_url="https://www.bokjiro.go.kr/ssis-tbu/cms/pc/common/download/2025년%20안내책자%20[아동·청소년].pdf",
        source_class="official_standard",independently_verified=True,obtained_from="official_public_guidance",
        available_at="2026-10-14",price_year=2025)
    share = evidence_row(**common,evidence_key="2216665:protected_child:published_population_share",
        variable_key="protected_child_population_share",value=.0017,unit="ratio",
        limitation="본문표시2020~2024평균0.17%의 반올림값. 원보호아동5년관측·비중정밀도 미검증. 실제평균 재계산값 아님",
        share_observation_years=[2020,2021,2022,2023,2024],value_precision="published_percent_two_decimals")
    return [premium,share]


def prepare_protected_child_insurance(payload):
    if payload.get("route_key")!=PROFILE:
        raise ValueError("protected-child insurance route required")
    if (payload.get("protected_child_model_confirmed") is not True
            or payload.get("protected_child_premium_mode")!="freeze_reference_premium"
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["protected_child_model_confirmation"],"support_derivation_trace":[]}
    age_basis = payload.get("protected_child_age_basis","under18_law")
    if age_basis not in {"under18_law","under19_answer_reference"}:
        raise ValueError("unsupported protected-child cohort")
    if age_basis=="under19_answer_reference" and (
            payload.get("estimate_purpose")!="reference_scenario"
            or payload.get("protected_child_age_conflict_approved") is not True
            or not str(payload.get("protected_child_age_conflict_note") or "").strip()):
        return {**payload,"support_missing_operands":["protected_child_age_conflict_confirmation"],"support_derivation_trace":[]}
    units = {r["variable_key"]:r["unit"] for r in protected_child_insurance_rows()}
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","payments_per_year","recipient_count")):
        raise ValueError("annual premium/population proxy already derived")
    r,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        if (row.unit!=units[k] or not row.source_ref or isinstance(row.value,bool)
                or not isinstance(row.value,(int,float)) or not isfinite(row.value) or row.value<0):
            raise ValueError("invalid protected-child evidence")
    share,premium = r["protected_child_population_share"].value,r["protected_child_annual_premium"].value
    if not 0<=share<=1:
        raise ValueError("protected-child share must be ratio")
    start,years = payload.get("start_year"),payload.get("years",5)
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1):
        raise ValueError("insurance horizon required")
    max_age = 17 if age_basis=="under18_law" else 18
    try:
        matrix = single_age_population_matrix(0,max_age,start,years)
    except ValueError:
        return {**payload,"support_missing_operands":["protected_child_population_year_coverage"],"support_derivation_trace":[]}
    annual,trace = [],[]
    for i,year in enumerate(range(start,start+years)):
        population = sum(row[i] for row in matrix.values())
        children = round(population*share)
        amount = children*premium
        annual.append(amount)
        trace.append(dict(year=year,population=population,population_age_max=max_age,
            population_vintage="2023-12",published_protected_child_share=share,
            estimated_protected_children=children,annual_premium_won=premium,amount_won=amount,
            age_basis=age_basis,answer_age_conflict=max_age==18))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys([*(x.source_ref for x in r.values()),
            "저장된KOSIS2023.12중위추계 연령별남녀인구 합산"])))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
