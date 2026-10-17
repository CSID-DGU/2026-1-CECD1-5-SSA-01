"""Mobile identity lifecycle: build, active operation, and warranty maintenance."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "mobile_identity_lifecycle"
ROUTE = "mobile_identity_system_lifecycle"


def mobile_identity_rows():
    common = dict(source_bill_no="2205097", available_at="2024-11-22", reviewed_at="2026-10-10",
        source_ref="2205097 비용추계서24C4867 PDF3~5쪽; 2025복지부 구축예산안·2023행안부 모바일공무원증 운영예산",
        agency="보건복지부", policy_domain="모바일장애인등록증", scope="모바일신분증 발급·접수·검증·전자회수 사업계획 참고",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="mobile_identity_operand",
        allowed_routes=[ROUTE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer", implementation_scale="장애인등록증·주민센터3586개 발급장비·모바일공무원증 운영참고",
        limitation="동일 발급플랫폼·과업·규모 검토 필요. 2025사업예산과2023운영단가 준용, 모든신분증의 보편가격이나 최신실적 아님")
    values = [("mobile_build_components", {"development": 3267000000, "hardware_software": 2422000000,
                    "issuance_devices": 876000000, "audit": 140000000, "privacy": 64000000, "procurement": 9000000}, "component_to_KRW"),
        ("mobile_operation_base", 837000000, "KRW/year"), ("mobile_maintenance_base", 233000000, "KRW/year"),
        ("mobile_recurring_price_year", 2023, "year"), ("mobile_operation_start_offset", 1, "year"),
        ("mobile_maintenance_start_offset", 2, "year"),
        ("mobile_cpi", {"2024": .025, "2025": .021, "2026": .02, "2027": .02, "2028": .02, "2029": .02}, "year_to_ratio")]
    return [evidence_row(evidence_key=f"2205097:{key}:reviewed", variable_key=key,
        value=value, unit=unit, **common) for key, value, unit in values]


def prepare_mobile_identity(payload):
    if payload.get("route_key") != ROUTE:
        raise ValueError("mobile identity lifecycle route mismatch")
    notes = ("mobile_build_scope_note", "mobile_operation_scope_note", "mobile_warranty_note", "mobile_price_timing_note")
    if payload.get("mobile_plan_scope_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in notes):
        return {**payload, "support_missing_operands": ["mobile_identity_scope_confirmation"], "support_derivation_trace": []}
    start = payload.get("start_year"); years = payload.get("years", 5)
    if start is None:
        return {**payload, "support_missing_operands": ["start_year"], "support_derivation_trace": []}
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("invalid mobile identity horizon")
    units = dict(mobile_build_components="component_to_KRW", mobile_operation_base="KRW/year",
        mobile_maintenance_base="KRW/year", mobile_recurring_price_year="year", mobile_operation_start_offset="year",
        mobile_maintenance_start_offset="year", mobile_cpi="year_to_ratio")
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate", "system_maintenance_rate", "subsidy_rate")):
        raise ValueError("mobile lifecycle cannot add duplicate CPI, maintenance percentage or subsidy")
    r, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    def valid(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and isfinite(x) and x >= 0
    for key, row in r.items():
        xs = list(row.value.values()) if isinstance(row.value, dict) else [row.value]
        if row.unit != units[key] or not row.source_ref or any(not valid(x) for x in xs):
            raise ValueError("invalid mobile lifecycle operand/unit")
    v = {key: row.value for key, row in r.items()}
    build = v["mobile_build_components"]; rates = v["mobile_cpi"]
    if not isinstance(build, dict) or not build or not isinstance(rates, dict):
        raise ValueError("build components and dated CPI required")
    base = v["mobile_recurring_price_year"]; operation_offset = v["mobile_operation_start_offset"]; maintenance_offset = v["mobile_maintenance_start_offset"]
    if any(x != int(x) for x in (base, operation_offset, maintenance_offset)) or base >= start or operation_offset < 1 or maintenance_offset <= operation_offset:
        raise ValueError("operation and post-warranty maintenance phases must be distinct")
    annual = []; trace = []
    for i in range(years):
        year = start + i; operation = 0; maintenance = 0
        if i >= operation_offset:
            required = range(int(base) + 1, year + 1)
            if any(str(y) not in rates for y in required):
                return {**payload, "support_missing_operands": ["mobile_cpi_year_coverage"], "support_derivation_trace": []}
            factor = prod(1 + rates[str(y)] for y in required)
            operation = v["mobile_operation_base"] * factor
            if i >= maintenance_offset:
                maintenance = v["mobile_maintenance_base"] * factor
        build_cost = sum(build.values()) if i == 0 else 0
        annual.append(build_cost + operation + maintenance)
        trace.append(dict(year=year, build_won=build_cost, operation_won=operation, maintenance_won=maintenance,
            operation_start_year=start + int(operation_offset), maintenance_start_year=start + int(maintenance_offset),
            maintenance_warranty_year=operation_offset <= i < maintenance_offset,
            recurring_price_year=base, build_scope_note=payload["mobile_build_scope_note"]))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual, unit="KRW/year", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [], "support_derivation_trace": trace}
