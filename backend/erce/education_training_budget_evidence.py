"""Whole annual teaching/content/trainer budget with an explicit price freeze."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "education_training_package_freeze"
NOTES = ("training_task_scope_note", "training_scale_note", "training_overlap_note", "training_price_note")


def education_training_budget_rows():
    return [evidence_row(evidence_key="2209738:education_training_annual_budget:2025",
        variable_key="education_training_annual_budget", value=700000000, unit="KRW/year",
        source_bill_no="2209738", available_at="2025-04-28", reviewed_at="2026-10-12",
        source_ref="2209738 비용추계서25C2156 PDF3~4쪽,2025장애인식개선교육 예산",
        agency="보건복지부", policy_domain="강사양성·교재·교육 통합사업",
        scope="콘텐츠제작·전문강사육성·교육 포함 연간사업예산",
        service_function=PROFILE, support_derivation=PROFILE, allowed_routes=[PROFILE],
        variable_role="annual_training_package_budget", price_year=2025,
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="2025사업 예산 선례이며 교육생당 요금 아님. 아동 금융교육에 같은규모 준용·매년실시·가격동결은 가정. 최신예산 독립확인 아님")]


def prepare_education_training_budget(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("annual training package route required")
    if (payload.get("training_package_confirmed") is not True
            or payload.get("training_price_mode") != "freeze_reference_budget"
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload, "support_missing_operands":["training_package_confirmation"],
                "support_derivation_trace":[]}
    layers = dict(target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"), official_standard=payload.get("official_inputs"),
        calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","frequency_per_year","quantity","unit_cost")):
        raise ValueError("frozen whole training budget cannot add CPI or duplicate package units")
    r,missing = resolve_formula_variables(("education_training_annual_budget",),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    row = r["education_training_annual_budget"]
    if (row.unit!="KRW/year" or not row.source_ref or isinstance(row.value,bool)
            or not isinstance(row.value,(int,float)) or not isfinite(row.value) or row.value<0):
        raise ValueError("invalid annual training budget")
    start,years = payload.get("start_year"),payload.get("years",5)
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1):
        raise ValueError("training horizon required")
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=[row.value]*years,unit="KRW/year",
        source_ref=row.source_ref,is_assumption=True)
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
        "support_derivation_trace":[dict(year=y,annual_amount_won=row.value,price_frozen=True,
            scope="content_trainer_teaching_whole_program") for y in range(start,start+years)]}
