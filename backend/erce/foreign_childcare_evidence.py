"""Foreign-child parent fees: reusable operands, isolated target-only replay."""
from math import isfinite, prod
from backend.erce.common_population_evidence import single_age_population_matrix
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "foreign_child_parent_fee"


def foreign_childcare_rows():
    common = dict(source_bill_no="2201907", available_at="2024-08-14", reviewed_at="2026-10-10",
        source_ref="2201907 비용추계서24C2118 PDF3~6쪽; 교육부2023.12 이용률·2024부모보육료",
        agency="교육부", policy_domain="외국국적 영유아 부모보육료", scope="합법 장기체류 외국아동 부모보육료, 기존지원 제외",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="foreign_childcare_operand",
        allowed_routes=["direct_annual_amount"], requires_applicability_note=True,
        independently_verified=False, obtained_from="reviewed_answer",
        limitation="국적별 실제 이용률 부재로 전체 이용률 준용. 국비율 동결·지자체 기존지원 미차감 참고 가정. 최신 가격 아님")
    rows = []
    for key, value, unit in (
        ("age_to_nursery_class", {"0": 0, "1": 0, "2": 1, "3": 2}, "age_to_class"),
        ("nursery_use_rates", {"0": .257, "1": .892, "2": .943}, "class_to_ratio"),
        ("parent_fee_monthly_base", {"0": 540000, "1": 475000, "2": 394000}, "class_to_KRW/month"),
        ("foreign_child_payment_months", 12, "month/year"), ("parent_fee_national_share", .694, "ratio")):
        rows.append(evidence_row(evidence_key=f"2201907:{key}:reviewed", variable_key=key, value=value, unit=unit, **common))
    rows.append(evidence_row(evidence_key="2200987:nabo_cpi:202403:foreign_fee",
        variable_key="parent_fee_cpi", value={"2025": .022, "2026": .022, "2027": .021,
            "2028": .021, "2029": .021, "2030": .02}, unit="year_to_ratio",
        **{**common, "source_bill_no": "2200987", "available_at": "2024-07-05",
           "source_ref": "2200987 비용추계서24C1050 PDF7쪽 각주4, NABO2024.3 전망CPI",
           "agency": "국회예산정책처", "limitation": "2024.3 역사적 전망, 최신2026 관측물가 아님. 가격 기준2024년 이후 한 번만 적용"}))
    # 공식 각세 인구를 재사용하되 외국국적 모집단으로 직접 치환하지 않는다.
    for key, value, unit, years in (
        ("child_population_base_by_age", {k: v[0] for k, v in single_age_population_matrix(0, 3, 2023, 1).items()}, "age_to_person", [2023]),
        ("child_population_future_by_age", single_age_population_matrix(0, 3, 2026, 5), "age_to_person_series", list(range(2026, 2031)))):
        rows.append(evidence_row(evidence_key=f"official:kosis:{key}:foreign_fee", variable_key=key,
            value=value, unit=unit, **{**common, "source_bill_no": "official:kosis:DT_1BPA001:202312",
                "available_at": "2023-12-14", "source_ref": "기존KOSIS2023.12 전국중위 각세 남녀합산 원자료",
                "source_class": "official_standard", "independently_verified": True,
                "value_years": years if len(years) > 1 else None,
                "limitation": "내외국인 전체 인구, 기준 외국아동 실적 비율을 별도로 적용해야 함"}))
    counts = {"0": [1193, 1252, 1308, 1359, 1403], "1": [1340, 1340, 1406, 1468, 1525],
              "2": [4825, 4578, 4575, 4801, 5014], "3": [5805, 5445, 5167, 5165, 5419]}
    rows.append(evidence_row(evidence_key="2201907:foreign_nursery_counts:target_only",
        variable_key="foreign_nursery_counts", value=counts, unit="age_to_person_series",
        reuse_policy="target_only", value_years=list(range(2026, 2031)),
        **{**common, "variable_role": "target_quantity", "foreign_parent_fee_basis": "reviewed_target",
            "source_ref": "2201907 비용추계서24C2118 PDF5쪽 표2, 대상 의안 전망치",
            "limitation": "자기 의안 개발 회귀 전용. 원기준인원으로 역산하거나 새 의안 재사용용 단가로 검색하지 않음"}))
    return rows


def prepare_foreign_childcare(payload):
    if payload.get("route_key") != "direct_annual_amount" or payload.get("foreign_parent_fee_basis") not in {"stock_share", "reviewed_target"}:
        raise ValueError("foreign parent-fee route/basis mismatch")
    notes = ("foreign_eligibility_note", "foreign_use_proxy_note", "parent_fee_price_note", "foreign_estimation_start_note")
    if payload.get("foreign_scope_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["foreign_parent_fee_confirmation"], "support_derivation_trace": []}
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid foreign childcare period")
    if payload.get("parent_fee_base_year") != 2024 or payload.get("foreign_population_base_year") != 2023:
        raise ValueError("versioned foreign childcare price/population basis mismatch")
    units = dict(age_to_nursery_class="age_to_class", nursery_use_rates="class_to_ratio",
                 parent_fee_monthly_base="class_to_KRW/month", foreign_child_payment_months="month/year",
                 parent_fee_national_share="ratio", parent_fee_cpi="year_to_ratio")
    if payload["foreign_parent_fee_basis"] == "stock_share":
        units.update(foreign_base_counts_by_age="age_to_person", child_population_base_by_age="age_to_person",
                     child_population_future_by_age="age_to_person_series")
    else:
        if payload.get("evidence_mode") != "development_review" or payload.get("bill_no") != "2201907":
            raise ValueError("target projection replay is not a reusable new-bill estimate")
        units["foreign_nursery_counts"] = "age_to_person_series"
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
                  official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
                  precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "subsidy_rate", "participation_rate")):
        raise ValueError("foreign parent fee forbids duplicate growth or subsidy")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    v = {k: row.value for k, row in r.items()}
    for k, row in r.items():
        if row.unit != units[k] or not row.source_ref:
            raise ValueError("foreign childcare operand unit/source mismatch")
    def number(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    classes = {"0", "1", "2"}; ages = {"0", "1", "2", "3"}
    if v["age_to_nursery_class"] != {"0": 0, "1": 0, "2": 1, "3": 2}:
        raise ValueError("chronological age and nursery class must not be conflated")
    for key in ("nursery_use_rates", "parent_fee_monthly_base"):
        if not isinstance(v[key], dict) or set(v[key]) != classes or any(not number(x) for x in v[key].values()):
            raise ValueError("invalid nursery class rates/prices")
    if (any(x > 1 for x in v["nursery_use_rates"].values()) or not number(v["parent_fee_national_share"])
            or v["parent_fee_national_share"] > 1 or not number(v["foreign_child_payment_months"])
            or v["foreign_child_payment_months"] > 12):
        raise ValueError("invalid childcare share/months")
    rates = v["parent_fee_cpi"]
    if not isinstance(rates, dict) or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) or x <= -1 for x in rates.values()):
        raise ValueError("invalid parent fee CPI")
    counts = v.get("foreign_nursery_counts")
    if counts is None:
        base = v["foreign_base_counts_by_age"]; whole = v["child_population_base_by_age"]
        future = v["child_population_future_by_age"]
        if any(not isinstance(x, dict) or set(x) != ages for x in (base, whole, future)):
            raise ValueError("individual age counts required; no arbitrary five-year-band split")
        counts = {}
        for age in ages:
            if (not number(base[age]) or not number(whole[age]) or whole[age] <= 0 or base[age] > whole[age]
                    or not isinstance(future[age], list) or len(future[age]) != years or any(not number(x) for x in future[age])):
                raise ValueError("invalid foreign base/population series")
            rate = v["nursery_use_rates"][str(v["age_to_nursery_class"][age])]
            counts[age] = [x * base[age] / whole[age] * rate for x in future[age]]
    if (not isinstance(counts, dict) or set(counts) != ages
            or any(not isinstance(xs, list) or len(xs) != years or any(not number(x) for x in xs) for xs in counts.values())):
        raise ValueError("invalid childcare counts horizon")
    annual = []; trace = []
    for i in range(years):
        year = start + i
        required_years = range(2025, year + 1)
        if any(str(y) not in rates for y in required_years):
            return {**payload, "support_missing_operands": ["parent_fee_cpi_year_coverage"], "support_derivation_trace": []}
        factor = prod(1 + rates[str(y)] for y in required_years)
        prices = {c: v["parent_fee_monthly_base"][c] * factor * v["foreign_child_payment_months"] for c in classes}
        parts = {age: counts[age][i] * prices[str(v["age_to_nursery_class"][age])] for age in ages}
        amount = sum(parts.values()); annual.append(amount)
        trace.append(dict(year=year, age_child_counts={age: counts[age][i] for age in ages}, annual_price_by_class=prices,
                          expenditure_won=amount, national_won=amount * v["parent_fee_national_share"],
                          local_won=amount * (1 - v["parent_fee_national_share"]),
                          count_basis=payload["foreign_parent_fee_basis"], source_notes={k: payload[k] for k in notes}))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
