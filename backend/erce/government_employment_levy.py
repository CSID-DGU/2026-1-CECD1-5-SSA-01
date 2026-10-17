"""Government employer expenditure is separate from levy-fund receipts."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "government_employment_levy_delta"
DOUBLE_MODEL = "floor_one_zero_double"


def government_double_levy_rows():
    common = dict(source_bill_no="2207081", available_at="2025-03-20", reviewed_at="2026-10-11",
        source_ref="2207081 비용추계서24B6384 PDF4·7~10쪽", agency="고용노동부",
        policy_domain="정부고용주 장애인고용부담금", scope="기초100%·무고용200% 개정의 정부납부지출",
        service_function=PROFILE, support_derivation=PROFILE, levy_payer_scope="state_local_employer",
        levy_band_model=DOUBLE_MODEL, variable_role="government_levy_operand", allowed_routes=[PROFILE],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="2025기초액·2024.11전망과 구간분포 동결의 선례. 가중치2.5는 법정상수가 아닌 검토할 구간배분 가정")
    values = [("levy_old_bands", {"1":1258000,"2":1333480,"3":1509600,"4":1761200,"5":2096270}, "band_to_KRW/month"),
        ("levy_minimum_monthly_base",2096270,"KRW/month"), ("levy_price_base_year",2025,"year"),
        ("levy_new_floor_share",1,"ratio"), ("levy_zero_employment_share",2,"multiplier"),
        ("levy_band_difference_weight",2.5,"ratio"),
        ("levy_minimum_growth",{"2026":.039,"2027":.038,"2028":.038,"2029":.038,"2030":.038},"year_to_ratio")]
    return [evidence_row(**common,evidence_key=f"2207081:{key}:reviewed",variable_key=key,value=value,unit=unit)
            for key,value,unit in values]


def government_levy_rows():
    common = dict(source_bill_no="2200209", available_at="2024-08-29", reviewed_at="2026-10-10",
        source_ref="2200209 비용추계서24B0612 PDF4~11쪽;2024기초액·2023정부미고용인원·납부실적",
        agency="고용노동부", policy_domain="정부고용주 장애인고용부담금", scope="국가·지자체 공무원 및 비공무원 납부지출",
        service_function=PROFILE, support_derivation=PROFILE, levy_payer_scope="state_local_employer",
        variable_role="government_levy_operand", allowed_routes=[PROFILE], requires_applicability_note=True,
        independently_verified=False, obtained_from="reviewed_answer",
        limitation="과거고용률구간·미고용인원·비공무원비중동결, 고용행태변화·감면미반영. 기금수입이 아닌 정부고용주지출")
    values = [("levy_old_bands", {"1": 1237000, "2": 1311220, "3": 1484400, "4": 1731800, "5": 2060740}, "band_to_KRW/month"),
        ("government_unfilled_by_band", {"1": 542, "2": 3988, "3": 4055, "4": 0, "5": 1}, "band_to_person"),
        ("levy_minimum_monthly_base", 2060740, "KRW/month"),
        ("levy_new_floor_share", .8, "ratio"), ("levy_band_difference_weight", .5, "ratio"),
        ("government_non_civil_share", .064, "ratio"), ("levy_payment_months", 12, "month/year"),
        ("levy_minimum_growth", {"2025": .017, "2026": .032, "2027": .032, "2028": .032, "2029": .032, "2030": .031}, "year_to_ratio")]
    rows = [evidence_row(evidence_key=f"2200209:{key}:reviewed", variable_key=key, value=value, unit=unit, **common)
            for key, value, unit in values]
    rows[-1]["source_ref"] += ";2030 3.1%는동일NABO2024.7전망2200664 PDF3각주1"
    return rows


def prepare_government_levy(payload):
    if payload.get("route_key") != PROFILE or payload.get("levy_payer_scope") != "state_local_employer":
        raise ValueError("government employer levy scope required, not fund receipts")
    model = payload.get("levy_band_model", "floor_eighty_zero_one")
    if model not in {"floor_eighty_zero_one", DOUBLE_MODEL}:
        raise ValueError("unknown government levy band model")
    notes = ("government_payer_note", "levy_band_note", "levy_overlap_note", "levy_timing_note")
    if payload.get("government_levy_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["government_levy_confirmation"], "support_derivation_trace": []}
    if payload.get("fiscal_reporting") != "separate_revenue_and_expenditure":
        raise ValueError("government levy expense cannot be netted with fund receipts")
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or start < 2026 or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid levy cash-flow period")
    offset = payload.get("reviewed_table_year_offset", 0)
    if isinstance(offset, bool) or offset not in (0, 1):
        raise ValueError("invalid table price-year offset")
    replay_bill = "2207081" if model == DOUBLE_MODEL else "2200209"
    if offset and (payload.get("bill_no") != replay_bill or payload.get("evidence_mode") != "development_review"
                   or not str(payload.get("levy_table_year_discrepancy_note") or "").strip()):
        raise ValueError("disputed source price-year mode is own-bill replay only")
    units = dict(levy_old_bands="band_to_KRW/month", government_unfilled_by_band="band_to_person",
        levy_minimum_monthly_base="KRW/month", levy_new_floor_share="ratio", levy_band_difference_weight="ratio",
        government_non_civil_share="ratio", levy_payment_months="month/year", levy_minimum_growth="year_to_ratio")
    if model == DOUBLE_MODEL:
        units.update(levy_price_base_year="year", levy_zero_employment_share="multiplier")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "subsidy_rate", "revenue_netting")):
        raise ValueError("no duplicate levy growth or netting")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    for key, row in r.items():
        xs = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid government levy operand/unit")
    v = {key: row.value for key, row in r.items()}; bands = set(map(str, range(1, 6)))
    old = v["levy_old_bands"]; counts = v["government_unfilled_by_band"]; base = v["levy_minimum_monthly_base"]
    if (not isinstance(old, dict) or not isinstance(counts, dict) or set(old) != bands or set(counts) != bands
            or base <= 0 or any(x != int(x) for x in counts.values()) or old["5"] != base
            or any(x > base for x in old.values()) or not 0 <= v["levy_new_floor_share"] <= 1
            or (model != DOUBLE_MODEL and not 0 <= v["levy_band_difference_weight"] <= 1)
            or not 0 <= v["government_non_civil_share"] <= 1
            or not 0 < v["levy_payment_months"] <= 12):
        raise ValueError("invalid levy band distribution/base/shares")
    old_shares = {band: old[band] / base for band in bands}
    base_year = 2024
    zero_share = 1
    if model == DOUBLE_MODEL:
        base_year = v["levy_price_base_year"]
        zero_share = v["levy_zero_employment_share"]
        if (base_year != int(base_year) or base_year < 2024 or base_year > start-1
                or v["levy_new_floor_share"] != 1 or zero_share != 2
                or not 1 <= v["levy_band_difference_weight"] <= 2.5):
            raise ValueError("double-minimum model requires reviewed floor/zero shares and price year")
    new_shares = {"1": v["levy_new_floor_share"], "5": zero_share}
    for band in ("2", "3", "4"):
        new_shares[band] = v["levy_new_floor_share"] + v["levy_band_difference_weight"] * (old_shares[band] - old_shares["1"])
    if any(x > zero_share for x in new_shares.values()):
        raise ValueError("new band levy above full minimum needs separate legal review")
    rates = v["levy_minimum_growth"]; annual = []; trace = []
    for i in range(years):
        cash_year = start + i; price_year = cash_year - 1 + offset
        if not isinstance(rates, dict) or any(str(y) not in rates for y in range(int(base_year)+1, price_year + 1)):
            return {**payload, "support_missing_operands": ["levy_growth_year_coverage"], "support_derivation_trace": []}
        monthly = base * prod(1 + rates[str(y)] for y in range(int(base_year)+1, price_year + 1))
        parts = {b: counts[b] * (new_shares[b] - old_shares[b]) * monthly * v["levy_payment_months"] for b in bands}
        civil = sum(parts.values()); other = civil * v["government_non_civil_share"]
        annual.append(civil + other)
        trace.append(dict(year=cash_year, liability_year=cash_year - 1, price_reference_year=price_year,
            old_band_shares=old_shares, new_band_shares=new_shares, civil_won_by_band=parts,
            civil_won=civil, non_civil_won=other, total_won=civil + other, netted_with_receipts=False,
            table_year_note=payload.get("levy_table_year_discrepancy_note")))
        trace[-1].update(band_model=model, minimum_base_year=base_year, zero_employment_share=zero_share)
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
