"""Submitted-plan costs: quantities are candidate assumptions, not statutory staffing."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "submitted_elder_protection_plan"
SLOTS = {
    "operation": {"central_centers": "center", "regional_centers": "center", "annual_center_cost": "KRW/center/year"},
    "project": {"regional_centers": "center", "helpers_per_center": "person/center", "monthly_helper_payment": "KRW/person/month", "activity_months": "month/year"},
    "staff": {"central_staff": "person", "regional_centers": "center", "staff_per_center": "person/center", "annual_staff_costs": "KRW/person/year"},
    "research": {"initial_research_cost": "KRW"},
    "system": {"initial_system_cost": "KRW"},
}


def submitted_plan_rows():
    data = {
        "central_centers": (1, "center"), "regional_centers": (38, "center"),
        "annual_center_cost": (50000000, "KRW/center/year"),
        "helpers_per_center": (3, "person/center"), "monthly_helper_payment": (761000, "KRW/person/month"),
        "central_staff": (5, "person"), "staff_per_center": (2, "person/center"),
        "annual_staff_costs": ([36528000, 37664000, 38835000, 40043000, 41288000], "KRW/person/year"),
        "initial_research_cost": (50000000, "KRW"), "initial_system_cost": (300000000, "KRW"),
    }
    rows = []
    for key, (value, unit) in data.items():
        extra = {}
        if key == "annual_staff_costs":
            extra = dict(value_years=list(range(2025, 2030)), salary_base_year=2024,
                monthly_base_salary=2262000, salary_growth_assumption=.0311,
                salary_allowance_scope="holiday_60_percent_twice",
                limitation="2025~2029 표의 1인 총보수. 퇴직적립·기관보험부담 포함. 원요율 독립확인 전 재계산 불가; 최신 공식보수표 아님")
        rows.append(evidence_row(evidence_key=f"2200482:plan:{key}:reviewed", variable_key=key,
            value=value, unit=unit, source_bill_no="2200482", available_at="2024-07-03",
            reviewed_at="2026-10-06", source_ref="2200482 비용추계서24C0850 PDF3~5쪽; 복지부 별도제출 예상사업계획 및 표3",
            agency="보건복지부", policy_domain="경제적 노인학대 대응", scope="중앙1·지역38개 보호기관의 신규지원사업",
            service_function=PROFILE, support_derivation=PROFILE, variable_role="submitted_plan_candidate",
            allowed_routes=["direct_annual_amount"], requires_applicability_note=True,
            obtained_from="reviewed_answer", independently_verified=False,
            original_plan_independently_obtained=False,
            source_url="backend/generated/assembly_22_pdfs/by_bill/2200482/cost_estimate.pdf",
            **extra))
    return rows


def prepare_submitted_plan(payload):
    kind = payload.get("plan_cost_item")
    if payload.get("route_key") != "direct_annual_amount" or kind not in SLOTS:
        raise ValueError("submitted plan cost item/route mismatch")
    if payload.get("fiscal_scope") != "national_and_local_combined" or not all(
        str(payload.get(k) or "").strip() for k in ("plan_applicability_note", "support_derivation_note", "estimation_start_note")):
        raise ValueError("submitted plan requires scope, applicability and forecast timing review")
    if payload.get("start_year") is None:
        return {**payload, "support_missing_operands": ["start_year"]}
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    upper, _ = resolve_formula_variables(("annual_amount",), **layers)
    if upper:
        return payload
    slots = dict(SLOTS[kind])
    table_review = kind == "project" and payload.get("activity_period_basis") == "historical_table_unresolved_monthly_unit"
    if table_review:
        if payload.get("evidence_mode") != "development_review" or payload.get("bill_no") != "2200482":
            raise ValueError("unresolved monthly unit is historical own-answer replay only")
        slots.pop("activity_months")
    r, missing = resolve_formula_variables(tuple(slots), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    for key, row in r.items():
        if key != "annual_staff_costs" and isinstance(row.value, (list, tuple, dict)):
            raise ValueError("submitted plan scalar operand required")
        values = row.value if isinstance(row.value, list) else [row.value]
        if row.unit != slots[key] or not row.source_ref or any(isinstance(v, bool) or not isinstance(v, (int,float))
                or not isfinite(v) or v < 0 for v in values):
            raise ValueError("submitted plan unit/value/source mismatch")
        if key in {"central_centers", "regional_centers", "helpers_per_center", "central_staff", "staff_per_center"} and row.value != int(row.value):
            raise ValueError("plan counts must be whole numbers")
    v = {k: row.value for k, row in r.items()}
    years = int(payload.get("years", 5))
    if years < 1:
        raise ValueError("invalid years")
    if kind == "operation":
        amounts = [(v["central_centers"] + v["regional_centers"]) * v["annual_center_cost"]] * years
        expression = "(중앙기관수+지역기관수)×기관당연운영비"
    elif kind == "project":
        months = 1 if table_review else v["activity_months"]
        if not 0 < months <= 12:
            raise ValueError("activity months must be in (0,12]")
        amounts = [v["regional_centers"] * v["helpers_per_center"] * v["monthly_helper_payment"] * months] * years
        expression = "지역기관수×기관당지킴이×월활동비×활동개월"
    elif kind == "staff":
        costs = v["annual_staff_costs"]
        if not isinstance(costs, list) or len(costs) != years:
            raise ValueError("annual staff costs need exact forecast horizon")
        amounts = [(v["central_staff"] + v["regional_centers"] * v["staff_per_center"]) * x for x in costs]
        expression = "(중앙정원+지역기관수×기관당정원)×연도별1인총보수"
    else:
        amounts = [v["initial_" + kind + "_cost"]] + [0] * (years-1)
        expression = "사업계획의일회성비용, 첫해만"
    source = "; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=amounts, unit="KRW/year", source_ref=source, is_assumption=True)
    trace = dict(item=kind, formula=expression, operands=v, annual_won=amounts,
        monthly_unit_unresolved=table_review, original_plan_independently_obtained=False)
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": [trace]}
