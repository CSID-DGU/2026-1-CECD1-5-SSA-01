"""Hospital communication support: annual official package vs disputed replay."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "hospital_communication_support_package"
ROUTE = "hospital_communication_support"
OFFICIAL_URL = "https://ms.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0069526.pdf?time=20260528111838"


def medical_communication_rows():
    common = dict(source_bill_no="2203688", available_at="2024-10-21", reviewed_at="2026-10-10",
        source_ref="2203688 비용추계서24C3571 PDF3~4쪽, 2025장애인 의료기관 이용편의 지원예산안 준용",
        agency="보건복지부", policy_domain="의료기관 장애인 의사소통", scope="상급종합병원 기존지원제외 추가기관 지원",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="medical_communication_operand",
        allowed_routes=[ROUTE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer", limitation="2024대상수·2025사업가정. 새 의안은 최신지정·기존지원겹침 확인 필요")
    rows = []
    for key, value, unit in (("tertiary_hospital_count", 47, "hospital"),
                             ("already_supported_hospital_count", 10, "hospital"),
                             ("communication_staff_per_hospital", 3, "person/hospital"),
                             ("communication_payment_months", 12, "month/year")):
        rows.append(evidence_row(evidence_key=f"2203688:{key}:reviewed", variable_key=key,
                                 value=value, unit=unit, **common))
    rows.append(evidence_row(evidence_key="official:seoul:communication:full_year_package:2025",
        variable_key="communication_annual_package", value=180000000, unit="KRW/hospital/year",
        **{**common, "source_bill_no": "official:seoul:communication_support_2025", "available_at": "2026-10-10",
           "source_ref": "서울시 제332회 업무보고 PDF39쪽(인쇄37쪽): 1차년도90백만원·2차년도180백만원/개소, 국비50%·시비50%",
           "source_url": OFFICIAL_URL, "source_class": "official_standard", "independently_verified": True,
           "obtained_from": "official_public_data", "medical_unit_basis": "official_annual_package",
           "limitation": "2025공식연차패키지. 1차년도90백만원과2차년도180백만원 구분 필요. 연간전체패키지에12개월을 다시 곱하지 않음"}))
    for key, value, unit in (("communication_staff_monthly_reference", 45800000, "KRW/person/month"),
                             ("communication_operation_monthly_reference", 42600000, "KRW/hospital/month")):
        rows.append(evidence_row(evidence_key=f"2203688:{key}:target_only", variable_key=key,
            value=value, unit=unit, reuse_policy="target_only",
            **{**common, "medical_unit_basis": "reviewed_monthly_replay", "variable_role": "disputed_target_unit",
               "limitation": "추계서월단가표기 재현전용. 공식사업연간패키지와상충, 다른의안의임금·운영단가로 재사용 금지"}))
    rows.append(evidence_row(evidence_key="2203688:nominal_wage_rates:20241011",
        variable_key="communication_nominal_wage_rates", value={"2025": .036, "2026": .039,
            "2027": .038, "2028": .038, "2029": .038, "2030": .038}, unit="year_to_ratio",
        **{**common, "source_ref": "2203688 비용추계서PDF4쪽 각주2, NABO2024.10.11 명목임금전망",
           "limitation": "역사적임금전망, CPI나최신실적아님. 기준단가년과첫적용년 확인 필요"}))
    return rows


def prepare_medical_communication(payload):
    basis = payload.get("medical_unit_basis")
    if payload.get("route_key") != ROUTE or basis not in {"official_annual_package", "reviewed_monthly_replay"}:
        raise ValueError("medical communication route/unit basis mismatch")
    notes = ("communication_scope_note", "communication_overlap_note", "communication_unit_note", "communication_timing_note")
    if payload.get("communication_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["communication_scenario_confirmation"], "support_derivation_trace": []}
    if payload.get("fiscal_scope") != "national_and_local_combined":
        raise ValueError("public combined expense must not be halved by national subsidy share")
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid communication support horizon")
    units = dict(tertiary_hospital_count="hospital", already_supported_hospital_count="hospital",
                 communication_staff_per_hospital="person/hospital", communication_payment_months="month/year")
    if basis == "official_annual_package":
        if payload.get("communication_package_phase") != "full_year_following_year" or payload.get("communication_price_policy") != "freeze_reference":
            raise ValueError("annual package phase and freeze scenario require review")
        units["communication_annual_package"] = "KRW/hospital/year"
    else:
        if (payload.get("bill_no") != "2203688" or payload.get("evidence_mode") != "development_review"
                or payload.get("disputed_monthly_replay_confirmed") is not True
                or not str(payload.get("communication_source_discrepancy_note") or "").strip()):
            raise ValueError("disputed monthly prices are own-bill development replay only")
        units.update(communication_staff_monthly_reference="KRW/person/month",
                     communication_operation_monthly_reference="KRW/hospital/month",
                     communication_nominal_wage_rates="year_to_ratio")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("subsidy_rate", "growth_rate")):
        raise ValueError("no duplicate subsidy share or generic growth")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    for key, row in r.items():
        xs = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid communication operand/unit")
    v = {key: row.value for key, row in r.items()}
    if (basis == "official_annual_package" and v["communication_staff_per_hospital"] != 3
            and "communication_annual_package" not in (payload.get("explicit_inputs") or {})):
        raise ValueError("three-staff comparable package requires a new quote for a different staffing scope")
    total = v["tertiary_hospital_count"]; old = v["already_supported_hospital_count"]
    if any(x != int(x) for x in (total, old, v["communication_staff_per_hospital"])) or old > total or not 0 <= v["communication_payment_months"] <= 12:
        raise ValueError("invalid hospital overlap/staff/months")
    count = total - old; annual = []; trace = []
    for i in range(years):
        year = start + i
        if basis == "official_annual_package":
            amount = count * v["communication_annual_package"] * v["communication_payment_months"] / 12
            staff_cost = None; operation_cost = None
        else:
            rates = v["communication_nominal_wage_rates"]
            if not isinstance(rates, dict) or any(str(y) not in rates for y in range(2025, year + 1)):
                return {**payload, "support_missing_operands": ["communication_wage_year_coverage"], "support_derivation_trace": []}
            factor = prod(1 + rates[str(y)] for y in range(2025, year + 1))
            staff_cost = v["communication_staff_monthly_reference"] * factor * v["communication_staff_per_hospital"]
            operation_cost = v["communication_operation_monthly_reference"]
            amount = count * (staff_cost + operation_cost) * v["communication_payment_months"]
        annual.append(amount)
        trace.append(dict(year=year, eligible_hospitals=count, total_hospitals=total, overlap_hospitals=old,
            unit_basis=basis, staff_monthly_cost=staff_cost, operation_monthly_cost=operation_cost,
            amount_won=amount, included_staff=v["communication_staff_per_hospital"],
            source_discrepancy_note=payload.get("communication_source_discrepancy_note")))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
