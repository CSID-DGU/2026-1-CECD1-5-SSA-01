"""Vocational-facility wage-gap subsidies, with reviewed scenario shares."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "disabled_worker_minimum_wage_gap"
DIRECT_MODEL = "direct_gap_subsidy"


def direct_worker_wage_rows():
    common = dict(source_bill_no="2207871",available_at="2025-05-14",reviewed_at="2026-10-11",
        source_ref="2207871 비용추계서25B0616 PDF3~6쪽",agency="보건복지부",
        policy_domain="장애인 직업재활시설 임금지원",scope="직업재활시설 적용제외 근로자, 시설외 사업체 제외",
        service_function=PROFILE,support_derivation=PROFILE,disabled_worker_scope="vocational_facility_exempt_workers",
        worker_support_model=DIRECT_MODEL,variable_role="disabled_worker_historical_operand",allowed_routes=[PROFILE],
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="전체시설 시급·시간을 적용제외집단 대리변수로 사용. 지원율은 가정, 다른법안 통과를 요구하지 않음")
    specs = [("exempt_worker_history",dict(zip(map(str,range(2020,2025)),[8016,8393,8741,8975,9189])),"year_to_person"),
        ("facility_hourly_wage_history",dict(zip(map(str,range(2020,2025)),[4903,5038,5447,5644,5705])),"year_to_KRW/hour"),
        ("facility_monthly_hours_history",dict(zip(map(str,range(2020,2025)),[106,106,119,118,118])),"year_to_hour/month"),
        ("worker_payment_months",12,"month/year")]
    rows=[evidence_row(**common,evidence_key=f"2207871:{k}:reviewed",variable_key=k,value=v,unit=u) for k,v,u in specs]
    rows.append(evidence_row(**common,evidence_key="2207871:minimum_wage_forecast_rates:202504",
        variable_key="minimum_wage_forecast_rates",value={"2026":.039,"2027":.038,"2028":.038,"2029":.038,"2030":.038},unit="year_to_ratio",
        worker_forecast_basis="published_2025_04_rates",forecast_vintage="2025-04"))
    for scenario,share in (("share30",.3),("share50",.5),("share100",1)):
        rows.append(evidence_row(**common,evidence_key=f"2207871:wage_gap_subsidy_share:{scenario}",
            variable_key="wage_gap_subsidy_share",value=share,unit="ratio",wage_gap_scenario=scenario))
    rows.append(evidence_row(**{**common,"source_bill_no":"2207081","available_at":"2025-03-20",
        "source_ref":"2207081 비용추계서24B6384 PDF9쪽 표7 최저임금 대비 현행i=5 월기초액, 월209시간으로 시급환산",
        "limitation":"2024.11 역사적 전망 단가를 준용한 대안 시나리오. 2207871의2025.4전망과 동일 원자료라고 확정하지 않음. 고용부담금 총액·대상인원은 재사용하지 않음"},
        evidence_key="2207081:minimum_hourly_forecast:202411:worker_gap",
        variable_key="minimum_wage_hourly_forecast_levels",value={str(y):v/209 for y,v in zip(range(2026,2031),[2177009,2259346,2344434,2432823,2526270])},unit="year_to_KRW/hour",
        worker_forecast_basis="reviewed_2024_11_levels",forecast_vintage="2024-11"))
    return rows


def disabled_worker_wage_rows():
    common = dict(source_bill_no="2200664", available_at="2024-07-26", reviewed_at="2026-10-10",
        source_ref="2200664 비용추계서24B1101 PDF3~7쪽, 복지부2019~2023직업재활시설 실적 및NABO2024.7 최저임금전망",
        agency="보건복지부", policy_domain="장애인 직업재활시설 임금지원", scope="직업재활시설 최저임금 적용제외 근로자, 다른사업체 제외",
        service_function=PROFILE, support_derivation=PROFILE, disabled_worker_scope="vocational_facility_exempt_workers",
        variable_role="disabled_worker_historical_operand", allowed_routes=[PROFILE],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="적용제외집단 시급·시간자료 부재로 시설전체평균 대리사용, 타사업체제외. 역사적추세·전망이고 최신실적 아님")
    values = [("exempt_worker_history", {str(y): n for y, n in zip(range(2019, 2024), [7812, 8016, 8393, 8741, 8975])}, "year_to_person"),
        ("facility_hourly_wage_history", {str(y): n for y, n in zip(range(2019, 2024), [4897, 5005, 4528, 5447, 5644])}, "year_to_KRW/hour"),
        ("facility_monthly_hours_history", {str(y): n for y, n in zip(range(2019, 2024), [126, 105, 112, 119, 118])}, "year_to_hour/month"),
        ("worker_payment_months", 12, "month/year"),
        ("minimum_wage_forecast_rates", {"2026": .032, "2027": .032, "2028": .032, "2029": .032, "2030": .031}, "year_to_ratio")]
    rows = [evidence_row(evidence_key=f"2200664:{key}:reviewed", variable_key=key, value=value, unit=unit,
                         **common) for key, value, unit in values]
    rows.append(evidence_row(evidence_key="official:moel:minimum_hourly:2025:disabled_gap",
        variable_key="minimum_wage_hourly_base", value=10030, unit="KRW/hour",
        **{**common, "source_bill_no": "official:moel:minimum_2025", "available_at": "2024-08-05",
           "source_ref": "고용노동부2024-50호, 2025적용 최저임금 시간급10,030원",
           "source_url": "https://www.minimumwage.go.kr/customer/notice/view.do?bultnId=4555",
           "source_class": "official_standard", "independently_verified": True, "obtained_from": "official_public_data",
           "observation_year": 2025, "limitation": "2025년 공식 기준. 이후년은 별도전망·확정임금을 구분해야 함"}))
    for scenario, share in (("share30", .3), ("share50", .5), ("share100", 1)):
        rows.append(evidence_row(evidence_key=f"2200664:wage_gap_subsidy_share:{scenario}",
            variable_key="wage_gap_subsidy_share", value=share, unit="ratio", wage_gap_scenario=scenario,
            **{**common, "variable_role": "policy_share_scenario",
               "limitation": "법정확정지원률 아님. 최저임금과 실제시급 차액에 적용하는30/50/100% 참고시나리오"}))
    return rows


def prepare_disabled_worker_gap(payload):
    if payload.get("route_key") != PROFILE or payload.get("disabled_worker_scope") != "vocational_facility_exempt_workers":
        raise ValueError("disabled worker facility/exemption scope mismatch")
    model=payload.get("worker_support_model","linked_minimum_wage_reform")
    if model not in {"linked_minimum_wage_reform",DIRECT_MODEL}:
        raise ValueError("unknown wage-gap legal model")
    notes = ("worker_scope_note", "worker_proxy_note", "worker_projection_note", "worker_scenario_note", "worker_start_note")
    if payload.get("worker_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["disabled_worker_gap_confirmation"], "support_derivation_trace": []}
    if model != DIRECT_MODEL and payload.get("linked_minimum_wage_bill_assumed_passed") is not True:
        return {**payload, "support_missing_operands": ["linked_bill_scope_confirmation"], "support_derivation_trace": []}
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or start < 2026 or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("historical forecast starts after its2025 minimum-wage basis")
    units = dict(exempt_worker_history="year_to_person", facility_hourly_wage_history="year_to_KRW/hour",
        facility_monthly_hours_history="year_to_hour/month", worker_payment_months="month/year",
        minimum_wage_forecast_rates="year_to_ratio", minimum_wage_hourly_base="KRW/hour", wage_gap_subsidy_share="ratio")
    forecast_basis=payload.get("worker_forecast_basis","published_2025_04_rates" if model==DIRECT_MODEL else "legacy_rates")
    use_levels=model==DIRECT_MODEL and forecast_basis=="reviewed_2024_11_levels"
    if model==DIRECT_MODEL and forecast_basis not in {"published_2025_04_rates","reviewed_2024_11_levels"}:
        raise ValueError("unknown direct wage forecast basis")
    if use_levels:
        units.pop("minimum_wage_forecast_rates")
        units["minimum_wage_hourly_forecast_levels"]="year_to_KRW/hour"
        if not str(payload.get("worker_forecast_vintage_note") or "").strip():
            return {**payload,"support_missing_operands":["worker_forecast_vintage_confirmation"],"support_derivation_trace":[]}
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "subsidy_rate", "participation_rate")):
        raise ValueError("no duplicate wage growth or subsidy factor")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    for key, row in r.items():
        xs = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid wage-gap operand/unit")
    v = {key: row.value for key, row in r.items()}
    histories = [v[k] for k in ("exempt_worker_history", "facility_hourly_wage_history", "facility_monthly_hours_history")]
    first,last=(2020,2024) if model==DIRECT_MODEL else (2019,2023)
    if any(not isinstance(h, dict) or set(h) != set(map(str, range(first,last+1))) for h in histories):
        raise ValueError("worker histories must cover reviewed years")
    counts, wages, hours = histories
    if counts[str(first)] <= 0 or wages[str(first)] <= 0 or not 0 < v["worker_payment_months"] <= 12 or not 0 <= v["wage_gap_subsidy_share"] <= 1:
        raise ValueError("invalid history base/months/share")
    count_growth = (counts[str(last)] / counts[str(first)]) ** .25 - 1
    wage_growth = (wages[str(last)] / wages[str(first)]) ** .25 - 1
    mean_hours = sum(hours.values()) / 5
    rates = v["minimum_wage_hourly_forecast_levels"] if use_levels else v["minimum_wage_forecast_rates"]; annual = []; trace = []
    for i in range(years):
        year = start + i
        required_years=[year] if use_levels else range(2026,year+1)
        if not isinstance(rates, dict) or any(str(y) not in rates for y in required_years):
            return {**payload, "support_missing_operands": ["minimum_wage_forecast_year_coverage"], "support_derivation_trace": []}
        count = round(counts[str(last)] * (1 + count_growth) ** (year - last))
        current = wages[str(last)] * (1 + wage_growth) ** (year - last)
        minimum = rates[str(year)] if use_levels else v["minimum_wage_hourly_base"] * prod(1 + rates[str(y)] for y in range(2026, year + 1))
        gap = max(minimum - current, 0)
        amount = count * gap * mean_hours * v["worker_payment_months"] * v["wage_gap_subsidy_share"]
        annual.append(amount)
        trace.append(dict(year=year, excluded_worker_count=count, projected_hourly_wage=current,
            minimum_hourly_wage=minimum, hourly_gap=gap, monthly_hours=mean_hours,
            payment_months=v["worker_payment_months"], subsidy_share=v["wage_gap_subsidy_share"], annual_won=amount,
            worker_cagr=count_growth, hourly_wage_cagr=wage_growth, proxy_note=payload["worker_proxy_note"]))
        trace[-1].update(legal_model=model,forecast_basis=forecast_basis,history_start=first,history_end=last,
            forecast_vintage_note=payload.get("worker_forecast_vintage_note",""))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
