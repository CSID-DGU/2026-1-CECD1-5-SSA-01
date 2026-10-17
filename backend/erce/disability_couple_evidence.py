"""Scoped disability basic-benefit recovery, with opt-in population scenarios."""
from math import isfinite, prod

from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "disability_couple_reduction_recovery"
SCOPE = "disabled_basic_18_64_home_livelihood_medical"


def disability_couple_rows():
    rows = []
    for name, value, unit, extra in (
        ("disability_reference_cohort", 120867, "person", {
            "disability_population_basis":"freeze_2023_cohort", "observation_year":2023,
            "valid_from_year":2025, "valid_to_year":2029,
            "historical_eligible_count_2023":508975,
            "historical_recipient_count_2023":355094,
            "historical_18_64_recipient_count_2023":219478,
            "full_forecast_recipe":{
                "adult_population":"2023.12 장래인구추계18세이상 인구",
                "eligibility_ratio":"2017~2023년 수급권자수/18세이상인구 비율 추세",
                "take_up_ratio":.7059,
                "age_share":"2018~2022년 연령별수급자비율 평균",
                "home_recipient_share_2023_display":.551,
                "couple_reduction_share":.029,
                "missing_source_series":["연도별18세이상인구","2017~2023수급권자비율","2018~2022연령별수급자비율"]},
            "limitation":"2023년 대상집단을 동결하는 선택적 대리 시나리오. 정답의 인구·수급권자비율 추세 전망을 복원한 인원이 아님"}),
        ("disability_couple_share", .029, "ratio", {
            "valid_from_year":2025, "valid_to_year":2029,
            "limitation":"2023년 대상집단 중 부부감액 적용 비율2.9%동결 선례; 수급자명 단위, 부부쌍아님"}),
        ("disability_lagged_cpi", [.025,.021,.02,.02,.02], "ratio/year", {
            "value_years":list(range(2025,2030)), "rate_observation_years":list(range(2024,2029)),
            "limitation":"2024.10 NABO 전망의 전년도 물가 적용. 값의 적용연도2025~2029, 실제 물가연도2024~2028. 최신전망 아님"}),
    ):
        rows.append(evidence_row(evidence_key=f"2204018:{name}:reference", variable_key=name,
            value=value, unit=unit, source_bill_no="2204018", available_at="2024-10-29",
            source_ref="2204018 비용추계서24C3784 PDF4쪽 표2 및 전제·물가전망",
            agency="국회예산정책처", policy_domain="장애인연금", scope=SCOPE,
            service_function=PROFILE, variable_role="assumption", reviewed_at="2026-10-04",
            support_derivation=PROFILE, disability_benefit_scope=SCOPE,
            allowed_routes=["transfer_recipient_delta"], requires_applicability_note=True,
            obtained_from="reviewed_answer", independently_verified=False, **extra))
    rows.append(evidence_row(evidence_key="mohw:disability_basic_monthly:2024",
        variable_key="disability_base_monthly", value=334810, unit="KRW/person/month",
        source_bill_no="official:mohw:2024-3", available_at="2024-01-10",
        source_ref="보건복지부고시제2024-3호 제3조 2024년도 기초급여액",
        source_url="https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000234880",
        agency="보건복지부", policy_domain="장애인연금", scope="2024년 기초급여 기준액",
        service_function=PROFILE, variable_role="base_rate", source_class="official_standard",
        reviewed_at="2026-10-04", independently_verified=True, benefit_index_base_year=2024,
        support_derivation=PROFILE, disability_benefit_scope=SCOPE,
        allowed_routes=["transfer_recipient_delta"], valid_from_year=2025, valid_to_year=2029,
        limitation="2024년 공식 기준액을 물가 연동의 기초로 사용. 2025~2029년 자체 고시액 또는 최신단가라고 주장하지 않음"))
    return rows


def prepare_disability_couple_operands(payload):
    if payload.get("route_key") != "transfer_recipient_delta":
        raise ValueError("disability recovery route mismatch")
    if payload.get("disability_benefit_scope") != SCOPE:
        raise ValueError("disability basic benefit cohort scope must be confirmed")
    if payload.get("disability_population_basis") != "freeze_2023_cohort" or not str(
            payload.get("population_proxy_note") or "").strip():
        raise ValueError("historical cohort freezing needs explicit scenario and note")
    if payload.get("benefit_index_base_year") != 2024 or payload.get("start_year") != 2025:
        raise ValueError("disability recovery needs 2024 base and prior-year CPI from 2025")
    if not str(payload.get("support_derivation_note") or "").strip() or not str(
            payload.get("estimation_start_note") or "").strip():
        raise ValueError("disability scope and start need applicability notes")
    if payload.get("supplementary_benefit_unchanged") is not True:
        raise ValueError("recovery applies to basic benefit only, not supplementary benefit")
    layers = dict(target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"), official_standard=payload.get("official_inputs"),
        calculated_estimate=payload.get("calculated_inputs"), precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("participation_rate", "growth_rate", "growth_rates_by_year")):
        raise ValueError("disability recovery duplicate adjustment forbidden")
    units = {"disability_reference_cohort":"person", "disability_couple_share":"ratio",
        "disability_base_monthly":"KRW/person/month", "disability_lagged_cpi":"ratio/year",
        "repealed_reduction_rate":"ratio"}
    resolved, missing = resolve_formula_variables(tuple(units), **layers)
    years = int(payload.get("years") or 5)
    if years < 1 or years > 5:
        raise ValueError("disability scenario supports 2025~2029 only")
    data = {}
    for key, row in resolved.items():
        if row.unit != units[key] or not row.source_ref:
            raise ValueError(f"{key}: incorrect unit or missing source")
        vals = list(row.value) if isinstance(row.value, (list,tuple)) else [row.value]*years
        if len(vals) != years or any(isinstance(v,bool) or not isinstance(v,(int,float))
                or not isfinite(v) or (v <= -1 if key == "disability_lagged_cpi" else v < 0)
                or (units[key] == "ratio" and v > 1) for v in vals):
            raise ValueError(f"{key}: invalid disability operand")
        if key in {"disability_reference_cohort", "disability_base_monthly"} and len(set(vals)) != 1:
            raise ValueError("fixed reference cohort and base must not be annual projections")
        data[key] = vals
    calculated = dict(payload.get("calculated_inputs") or {})
    trace = []
    deps = {"recipient_count":("disability_reference_cohort","disability_couple_share"),
        "benefit_per_recipient":("disability_base_monthly","disability_lagged_cpi"),
        "existing_benefit_per_recipient":("disability_base_monthly","disability_lagged_cpi","repealed_reduction_rate")}
    for key, dependencies in deps.items():
        if not all(d in data for d in dependencies):
            continue
        if key == "recipient_count":
            values = [data["disability_reference_cohort"][i]*data["disability_couple_share"][i] for i in range(years)]
            expression = "2023년18~64세재가수급자 동결×부부감액적용비율; 부부쌍2배 금지"
        else:
            values = [data["disability_base_monthly"][i]*prod(1+r for r in data["disability_lagged_cpi"][:i+1]) for i in range(years)]
            if key == "existing_benefit_per_recipient":
                values = [v*(1-data["repealed_reduction_rate"][i]) for i,v in enumerate(values)]
            expression = "2024년기초급여×전년도물가 누적" + ("×(1−폐지감액률)" if key == "existing_benefit_per_recipient" else "")
        upper, _ = resolve_formula_variables((key,), **{**layers,"calculated_estimate":calculated})
        ref = "; ".join(dict.fromkeys(resolved[d].source_ref for d in dependencies))
        unit = "person" if key == "recipient_count" else "KRW/person/month"
        if key not in upper:
            calculated[key] = dict(value=values, unit=unit, source_ref=ref, is_assumption=True)
        trace.append(dict(variable_key=key, dependencies=list(dependencies), values=values,
            unit=unit, expression=expression, source_ref=ref, applied=key not in upper))
    _, top_missing = resolve_formula_variables(tuple(deps), **{**layers,"calculated_estimate":calculated})
    needed = {d for top in top_missing for d in deps[top]}
    return {**payload, "calculated_inputs":calculated, "support_derivation_trace":trace,
        "support_missing_operands":[k for k in missing if k in needed]}
