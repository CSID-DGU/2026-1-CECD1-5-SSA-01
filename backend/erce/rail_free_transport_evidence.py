"""Disabled urban-rail compensation from historical trips and fare losses."""
from math import isfinite, log
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "disabled_urban_rail_compensation"
ROUTE = "disabled_urban_rail_compensation"


def rail_free_transport_rows():
    common = dict(source_bill_no="2204465", available_at="2024-10-21", reviewed_at="2026-10-10",
        source_ref="2204465 비용추계서24C4189 PDF3~4쪽, 국토교통부2023철도통계연보 인용",
        agency="국토교통부", policy_domain="장애인 도시철도 무임보전", scope="장애인·동행보호자 도시철도, 코레일PSO 기존보상 제외",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="rail_historical_operand",
        rail_beneficiary_scope="disabled_and_one_companion", rail_operator_scope="urban_rail_excluding_korail_pso",
        allowed_routes=[ROUTE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer", limitation="2021~2023승차 연인원·손실비용의 참고전망. 고유장애인수·노인무임수송과다름. 정책적 전액보전 가정")
    values = [
        ("rail_free_trip_history", {"2021": 60469000, "2022": 63951000, "2023": 68665000}, "year_to_trip"),
        ("rail_free_loss_history", {"2021": 81268000000, "2022": 175777000000, "2023": 200189000000}, "year_to_KRW"),
        ("rail_compensation_share", 1, "ratio"),
    ]
    return [evidence_row(evidence_key=f"2204465:{key}:reviewed", variable_key=key,
                         value=value, unit=unit, **common) for key, value, unit in values]


def _ols(xs, ys):
    mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator <= 0:
        raise ValueError("rail trend needs distinct historical years")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator
    return slope, my - slope * mx


def prepare_rail_compensation(payload):
    if (payload.get("route_key") != ROUTE or payload.get("rail_beneficiary_scope") != "disabled_and_one_companion"
            or payload.get("rail_operator_scope") != "urban_rail_excluding_korail_pso"):
        raise ValueError("rail beneficiary/operator scope mismatch")
    notes = ("rail_scope_note", "korail_exclusion_note", "rail_trend_note", "rail_fiscal_share_note", "rail_start_note")
    if payload.get("rail_compensation_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["rail_compensation_confirmation"], "support_derivation_trace": []}
    if payload.get("rail_volume_trend") != "linear_ols" or payload.get("rail_fare_trend") != "log_ols":
        raise ValueError("separate rail volume/fare trend selection required")
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid rail forecast period")
    units = dict(rail_free_trip_history="year_to_trip", rail_free_loss_history="year_to_KRW", rail_compensation_share="ratio")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "subsidy_rate", "participation_rate")):
        raise ValueError("rail compensation must not add duplicate inflation or subsidy")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    for key, row in r.items():
        if row.unit != units[key] or not row.source_ref:
            raise ValueError("invalid rail operand unit/source")
    trips = r["rail_free_trip_history"].value; losses = r["rail_free_loss_history"].value
    share = r["rail_compensation_share"].value
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    if (not isinstance(trips, dict) or not isinstance(losses, dict) or set(trips) != set(losses)
            or len(trips) < 3 or any(not isinstance(k, str) or not k.isdigit() for k in trips)
            or any(not valid(x) or x == 0 for x in trips.values())
            or any(not valid(x) for x in losses.values()) or not valid(share) or share > 1):
        raise ValueError("dated trip/loss histories and compensation share required")
    dates = sorted(map(int, trips))
    if start <= dates[-1] or dates != list(range(dates[0], dates[-1] + 1)):
        raise ValueError("rail histories must be consecutive and predate forecast")
    indices = [y - dates[0] + 1 for y in dates]
    volumes = [trips[str(y)] for y in dates]
    fares = [losses[str(y)] / trips[str(y)] for y in dates]
    volume_slope, volume_intercept = _ols(indices, volumes)
    fare_slope, fare_intercept = _ols([log(x) for x in indices], fares)
    annual = []; trace = []
    for i in range(years):
        year = start + i; x = year - dates[0] + 1
        count = volume_intercept + volume_slope * x
        price = fare_intercept + fare_slope * log(x)
        if not valid(count) or not valid(price):
            raise ValueError("invalid extrapolated rail volume/price; review trend")
        amount = count * price * share; annual.append(amount)
        trace.append(dict(year=year, unrounded_trip_count=count, displayed_trip_thousand=round(count / 1000),
            unrounded_fare_per_trip=price, displayed_fare_won=round(price), compensation_share=share,
            volume_slope=volume_slope, fare_log_slope=fare_slope, annual_won=amount,
            trend_note=payload["rail_trend_note"], korail_exclusion_note=payload["korail_exclusion_note"]))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
