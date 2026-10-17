"""Public-activity stipend/minimum-wage delta; version-disputed reference only."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "elderly_public_activity_minimum_wage_delta"
ROUTE = "elderly_public_activity_wage_delta"


def elderly_public_activity_rows():
    values = [("public_activity_participant_history", {str(y): n for y, n in zip(range(2019, 2024), [543000, 590000, 608000, 608000, 654000])}, "year_to_person"),
        ("minimum_wage_history", {str(y): n for y, n in zip(range(2021, 2026), [8720, 9160, 9620, 9860, 10030])}, "year_to_KRW/hour"),
        ("current_monthly_activity_pay", 290000, "KRW/person/month"),
        ("monthly_activity_hours", 30, "hour/month"), ("normal_activity_months", 11, "month/year"),
        ("ancillary_annual_cost", 180000, "KRW/person/year")]
    return [evidence_row(evidence_key=f"2203550:public_activity:{key}", variable_key=key,
        value=value, unit=unit, source_bill_no="2203550", available_at="2024-08-08", reviewed_at="2026-10-10",
        source_ref="2203550 폴더 첨부24C2515 PDF3~5쪽; 복지부2019~2023사업 실적·2021~2025최저임금 고시 인용",
        agency="보건복지부", policy_domain="공익활동형 노인일자리", scope="공익활동형만 최저시급 적용, 기존 민간·사회서비스형 제외",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="historical_activity_operand",
        allowed_routes=[ROUTE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer", source_bill_version_match=False,
        limitation="회답2024-08-08이대상발의2024-09-03보다빠르고표지의안번호공란. 승인된참고시나리오만. 역사적 추세이지최신 실적·최저임금전망 확정치 아님") for key, value, unit in values]


def prepare_elderly_public_activity(payload):
    if payload.get("route_key") != ROUTE or payload.get("elderly_job_type") != "public_activity":
        raise ValueError("public-activity-only route/scope required")
    if (payload.get("use_unmatched_source_as_reference") is not True
            or not all(str(payload.get(k) or "").strip() for k in
                       ("unmatched_source_reference_note", "public_activity_scope_note", "activity_projection_note", "activity_timing_note"))):
        raise ValueError("historical source version and activity scenario review required")
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start != 2024 or isinstance(start, bool) or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("reference scenario must start from its confirmed 2024 basis")
    if payload.get("law_effective_date") != "2024-11-01":
        raise ValueError("first-year payment timing must be confirmed")
    units = dict(public_activity_participant_history="year_to_person", minimum_wage_history="year_to_KRW/hour",
        current_monthly_activity_pay="KRW/person/month", monthly_activity_hours="hour/month",
        normal_activity_months="month/year", ancillary_annual_cost="KRW/person/year")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "subsidy_rate", "participation_rate")):
        raise ValueError("no duplicate index or population adjustment")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    for key, row in r.items():
        xs = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid public-activity operand/unit")
    v = {key: row.value for key, row in r.items()}
    people = v["public_activity_participant_history"]; wages = v["minimum_wage_history"]
    if (not isinstance(people, dict) or set(people) != set(map(str, range(2019, 2024)))
            or not isinstance(wages, dict) or set(wages) != set(map(str, range(2021, 2026)))
            or people["2019"] <= 0 or wages["2021"] <= 0 or not 0 < v["normal_activity_months"] <= 12):
        raise ValueError("activity and minimum-wage histories need dated endpoint bases")
    people_growth = (people["2023"] / people["2019"]) ** .25 - 1
    wage_growth = (wages["2025"] / wages["2021"]) ** .25 - 1
    annual = []; trace = []
    for i in range(years):
        year = start + i
        count = round(people["2023"] * (1 + people_growth) ** (year - 2023))
        hourly = wages[str(year)] if str(year) in wages else round(wages["2025"] * (1 + wage_growth) ** (year - 2025))
        months = 2 if year == 2024 else v["normal_activity_months"]
        ancillary = v["ancillary_annual_cost"] * months / v["normal_activity_months"]
        old = count * (v["current_monthly_activity_pay"] * months + ancillary)
        new_monthly = max(v["current_monthly_activity_pay"], hourly * v["monthly_activity_hours"])
        new = count * (new_monthly * months + ancillary)
        annual.append(new - old)
        trace.append(dict(year=year, public_activity_participants=count, minimum_hourly_wage=hourly,
            participant_cagr=people_growth, minimum_wage_cagr=wage_growth, payment_months=months,
            current_monthly_pay=v["current_monthly_activity_pay"], new_monthly_pay=new_monthly,
            ancillary_per_person_both_sides=ancillary, baseline_won=old, amended_won=new,
            additional_won=annual[-1], source_version_note=payload["unmatched_source_reference_note"]))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
