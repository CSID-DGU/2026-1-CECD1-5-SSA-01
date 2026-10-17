"""Reviewed incremental interpreter staffing, distinct from a service package."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "hospital_interpreter_increment"
NOTES = ("interpreter_scope_note", "interpreter_increment_note", "interpreter_price_note", "interpreter_timing_note")


def interpreter_increment_rows():
    common = dict(source_bill_no="2205811", available_at="2024-12-05", reviewed_at="2026-10-11",
        source_ref="2205811 비용추계서24C5381 PDF3~5쪽", agency="보건복지부",
        policy_domain="국립대학병원 수어통역", scope="18개 국립대학병원 각1명 추가배치",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="interpreter_increment_operand",
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="정답에서 검토한 역사적 후보. 현재 기관수·증원계획·보수기준 확인 후 적용. 공무원 보수표 아님")
    rows = []
    specs = [
        ("national_university_hospital_count", 18, "hospital", ["personnel_average", "personnel_asset"]),
        ("additional_interpreters_per_hospital", 1, "person/hospital", ["personnel_average", "personnel_asset"]),
        ("interpreter_salary_2024", 25680000, "KRW/person/year", ["personnel_average"]),
        ("interpreter_wage_rates", {"2025": .036, "2026": .039, "2027": .038, "2028": .038, "2029": .038, "2030": .038}, "year_to_ratio", ["personnel_average"]),
        ("interpreter_asset_2024", 6740000, "KRW/person", ["personnel_asset"]),
        ("interpreter_asset_cpi", {"2025": .021, "2026": .02, "2027": .02, "2028": .02, "2029": .02, "2030": .02}, "year_to_ratio", ["personnel_asset"]),
    ]
    for key, value, unit, routes in specs:
        rows.append(evidence_row(evidence_key=f"2205811:{key}:reviewed", variable_key=key,
            value=value, unit=unit, allowed_routes=routes, **common))
    return rows


def prepare_interpreter_increment(payload):
    route = payload.get("route_key")
    if route not in {"personnel_average", "personnel_asset"}:
        raise ValueError("수어통역 증원은 인건비·첫해 자산 경로로 분리해야 합니다")
    if (payload.get("interpreter_increment_confirmed") is not True
            or payload.get("existing_interpreters_subtracted") is not False
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload, "support_missing_operands": ["interpreter_increment_confirmation"], "support_derivation_trace": []}
    start, years = payload.get("start_year"), payload.get("years", 5)
    if isinstance(start, bool) or not isinstance(start, int) or start < 2025 or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("기준단가 이후 추계 연도를 확인해야 합니다")
    units = dict(national_university_hospital_count="hospital", additional_interpreters_per_hospital="person/hospital")
    price, rates = ("interpreter_salary_2024", "interpreter_wage_rates") if route == "personnel_average" else ("interpreter_asset_2024", "interpreter_asset_cpi")
    units.update({price: "KRW/person/year" if route == "personnel_average" else "KRW/person", rates: "year_to_ratio"})
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "growth_rates_by_year", "subsidy_rate", "duration")):
        raise ValueError("하위 전망과 중복되는 상승률·기간·분담률은 적용할 수 없습니다")
    resolved, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    for key, row in resolved.items():
        values = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) or x < 0 for x in values):
            raise ValueError("통역사 증원 변수의 단위·근거·값을 확인해야 합니다")
    v = {k: r.value for k, r in resolved.items()}
    if any(v[k] != int(v[k]) for k in ("national_university_hospital_count", "additional_interpreters_per_hospital")):
        raise ValueError("병원 수와 추가 인원은 정수여야 합니다")
    headcount = v["national_university_hospital_count"] * v["additional_interpreters_per_hospital"]
    end = start + years - 1 if route == "personnel_average" else start
    if not isinstance(v[rates], dict) or any(str(y) not in v[rates] for y in range(2025, end + 1)):
        return {**payload, "support_missing_operands": [rates + "_year_coverage"], "support_derivation_trace": []}
    prices = [v[price] * prod(1 + v[rates][str(y)] for y in range(2025, year + 1)) for year in range(start, end + 1)]
    ref = "; ".join(dict.fromkeys(r.source_ref for r in resolved.values()))
    def operand(value, unit):
        return dict(value=value, unit=unit, source_ref=ref, is_assumption=True)
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["headcount"] = operand(headcount, "person")
    if route == "personnel_average":
        calculated["salary_per_person"] = operand(prices, "KRW/person/year")
    else:
        calculated["asset_unit_price_per_person"] = operand(prices[0], "KRW/person")
        calculated["duration"] = operand(1, "year")
    trace = [dict(year=start+i, hospitals=v["national_university_hospital_count"], additional_headcount=headcount,
        existing_staff_subtracted=False, price_year=2024, unit_price=prices[i] if route == "personnel_average" else prices[0],
        amount_won=headcount * (prices[i] if route == "personnel_average" else prices[0] if i == 0 else 0)) for i in range(years)]
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
