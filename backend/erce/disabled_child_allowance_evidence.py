"""Mandatory child allowance: incremental non-recipients by severity/residence."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "disabled_child_allowance_mandatory_delta"
GROUPS = {"severe_home", "severe_facility", "mild_home", "mild_facility"}
SCOPE = "under18_livelihood_medical"


def disabled_child_allowance_rows():
    values = [
        ("child_allowance_eligible_by_group", dict(severe_home=3999, severe_facility=1028, mild_home=4583, mild_facility=1005), "group_to_person"),
        ("child_allowance_current_by_group", dict(severe_home=3919, severe_facility=1018, mild_home=4409, mild_facility=968), "group_to_person"),
        ("child_allowance_monthly_by_group", dict(severe_home=220000, severe_facility=90000, mild_home=110000, mild_facility=30000), "group_to_KRW/month"),
        ("child_allowance_payment_months", 12, "month/year"),
    ]
    return [evidence_row(evidence_key=f"2205274:{key}:reviewed", variable_key=key, value=value, unit=unit,
        source_bill_no="2205274", available_at="2024-12-12", reviewed_at="2026-10-10",
        source_ref="2205274 비용추계서24C4866 PDF3~4쪽, 2024.11행복이음 등록·수급자료 및2024지급기준",
        agency="한국사회보장정보원", policy_domain="장애아동수당", scope="생계·의료수급 만18세미만 등록장애아동",
        service_function=PROFILE, support_derivation=PROFILE, disability_child_scope=SCOPE,
        variable_role="child_allowance_grouped_operand", allowed_routes=[PROFILE], observation_year=2024,
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="2024.11 대상·수급자분포와2024단가동결 가정. 최신실적 아님. 재학18~20세는 추출한계로 제외, 성인장애수당과다름")
        for key, value, unit in values]


def prepare_disabled_child_allowance(payload):
    if payload.get("route_key") != PROFILE or payload.get("disability_child_scope") != SCOPE:
        raise ValueError("child allowance requires under18 livelihood/medical scope")
    notes = ("child_allowance_scope_note", "child_allowance_baseline_note", "child_allowance_freeze_note", "child_allowance_start_note")
    if payload.get("child_allowance_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["child_allowance_delta_confirmation"], "support_derivation_trace": []}
    if payload.get("child_allowance_projection") != "freeze_202411_cohort_and_2024_rate":
        raise ValueError("child allowance historical freeze scenario must be explicit")
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or start < 2025 or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid child allowance forecast period")
    units = dict(child_allowance_eligible_by_group="group_to_person", child_allowance_current_by_group="group_to_person",
                 child_allowance_monthly_by_group="group_to_KRW/month", child_allowance_payment_months="month/year")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "participation_rate", "subsidy_rate")):
        raise ValueError("frozen child allowance cannot add population/CPI/subsidy factors")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    v = {key: row.value for key, row in r.items()}
    for key, row in r.items():
        if row.unit != units[key] or not row.source_ref:
            raise ValueError("invalid child allowance operand unit/source")
    def number(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    eligible = v["child_allowance_eligible_by_group"]; current = v["child_allowance_current_by_group"]
    prices = v["child_allowance_monthly_by_group"]; months = v["child_allowance_payment_months"]
    if (any(not isinstance(x, dict) or set(x) != GROUPS for x in (eligible, current, prices))
            or not number(months) or not 0 < months <= 12):
        raise ValueError("four severity/residence groups and valid payment months required")
    deltas = {}; parts = {}
    for group in GROUPS:
        if (not all(number(x) for x in (eligible[group], current[group], prices[group]))
                or eligible[group] != int(eligible[group]) or current[group] != int(current[group])
                or current[group] > eligible[group]):
            raise ValueError("invalid eligible/current group counts or monthly rate")
        deltas[group] = eligible[group] - current[group]
        parts[group] = deltas[group] * prices[group] * months
    amount = sum(parts.values())
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=[amount] * years, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    trace = [dict(year=start+i, eligible_by_group=eligible, current_by_group=current,
        new_recipients_by_group=deltas, monthly_prices=prices, annual_won_by_group=parts, payment_months=months,
        additional_recipients=sum(deltas.values()), annual_won=amount,
        excluded_scope="행정자료 추출한계로 학교재학18~20세는 참고추계에서 제외") for i in range(years)]
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
