"""Child-domain education/media whole-budget proxy, not a universal ad tariff."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "child_awareness_education_budget"
NOTES = ("child_awareness_scope_note", "child_awareness_scale_note",
         "child_awareness_overlap_note", "child_awareness_price_note")


def child_awareness_budget_rows():
    common = dict(source_bill_no="2208744", available_at="2025-04-10", reviewed_at="2026-10-12",
        source_ref="2208744 비용추계서25C1366 PDF2~3쪽",
        agency="보건복지부", policy_domain="아동 인식개선 교육·홍보",
        scope="입양인식개선 매체홍보·교육·위탁기관 실무자교육 전체 연간사업",
        service_function=PROFILE, support_derivation=PROFILE, variable_role="education_media_budget_operand",
        allowed_routes=[PROFILE], requires_applicability_note=True, independently_verified=False,
        obtained_from="reviewed_answer",
        limitation="2025 입양사업 예산 선례. 최신 공식 광고요율 아님. 다른 대상에 같은 사업규모 준용은 가정. 강사양성·프로그램개발의 개별 실제 예산내역은 미확인")
    specs = [("child_awareness_annual_budget",777000000,"KRW/year"),
             ("child_awareness_budget_year",2025,"year"),
             ("child_awareness_cpi_rates",{str(y):.02 for y in range(2026,2031)},"year_to_ratio")]
    return [evidence_row(**common,evidence_key=f"2208744:{k}:reviewed",
                        variable_key=k,value=v,unit=u) for k,v,u in specs]


def prepare_child_awareness_budget(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("child awareness education route required")
    if (payload.get("child_awareness_package_confirmed") is not True
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["child_awareness_package_confirmation"],
                "support_derivation_trace":[]}
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","frequency_per_year","quantity","unit_cost")):
        raise ValueError("whole annual education/media package cannot add duplicate frequency/CPI/units")
    units = {r["variable_key"]:r["unit"] for r in child_awareness_budget_rows()}
    resolved,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for key,row in resolved.items():
        values = list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if (row.unit != units[key] or not row.source_ref or any(isinstance(x,bool)
                or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in values)):
            raise ValueError("invalid education/media budget operand")
    v = {k:r.value for k,r in resolved.items()}
    start,years,base = payload.get("start_year"),payload.get("years",5),v["child_awareness_budget_year"]
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1 or base!=int(base) or base>=start):
        raise ValueError("budget year must precede integer forecast horizon")
    rates,annual,trace = v["child_awareness_cpi_rates"],[],[]
    for year in range(start,start+years):
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(int(base)+1,year+1)):
            return {**payload,"support_missing_operands":["child_awareness_cpi_year_coverage"],
                    "support_derivation_trace":[]}
        amount = v["child_awareness_annual_budget"]*prod(1+rates[str(y)] for y in range(int(base)+1,year+1))
        annual.append(amount)
        trace.append(dict(year=year,reference_budget_won=v["child_awareness_annual_budget"],
            budget_year=int(base),annual_amount_won=amount,scope="education_media_whole_program",
            separately_priced_instructor_or_program=False))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(r.source_ref for r in resolved.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
            "support_derivation_trace":trace}
