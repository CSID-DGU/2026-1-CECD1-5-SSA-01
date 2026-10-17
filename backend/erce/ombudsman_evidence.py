"""Non-salaried appointee and professional secretariat, using existing formulas."""
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="appointed_ombudsman_secretariat"
ROUTES=dict(meeting="interagency_meeting_operation",personnel="personnel_average",operation="quantity_unit",initial_asset="personnel_asset")
NOTES=("ombudsman_scope_note","ombudsman_staffing_note","ombudsman_unit_note","ombudsman_start_note")


def ombudsman_rows():
    common=dict(source_bill_no="2205719",available_at="2024-12-12",reviewed_at="2026-10-11",
        source_ref="2205719 비용추계서24C5380 PDF3~5쪽,중소기업옴부즈만2024사업설명자료준용",
        agency="보건복지부",policy_domain="위촉옴부즈만 사무기구",scope="비상근무보수위촉자+전문위원 사무기구,기존부서행정지원 중복제외",
        service_function=PROFILE,support_derivation=PROFILE,variable_role="ombudsman_operand",
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="과거배치·패키지·회의규모 가정. 공무원조직정원·직급별봉급·최신공식비용 아님")
    specs=[("ombudsman_offices",1,"office",list(ROUTES)),
        ("ombudsman_heads_per_office",1,"person/office",["meeting","initial_asset"]),
        ("ombudsman_meetings_per_year",48,"meeting/year",["meeting"]),
        ("ombudsman_meeting_unit",400000,"KRW/person/meeting",["meeting"]),
        ("ombudsman_professional_per_office",16,"person/office",["personnel","initial_asset"]),
        ("ombudsman_reference_professionals",16,"person",["personnel"]),
        ("ombudsman_reference_payroll",964000000,"KRW/year",["personnel"]),
        ("ombudsman_reference_operations",2168000000,"KRW/office/year",["operation"]),
        ("ombudsman_asset_unit_reference",4200000,"KRW/person",["initial_asset"]),
        ("ombudsman_nominal_rates",{"2025":.036,"2026":.039,"2027":.038,"2028":.038,"2029":.038,"2030":.038},"year_to_ratio",["personnel"]),
        ("ombudsman_cpi_rates",{"2025":.021,"2026":.02,"2027":.02,"2028":.02,"2029":.02,"2030":.02},"year_to_ratio",["operation","initial_asset"]),
        ("ombudsman_package_base_year",2024,"year",["personnel","operation","initial_asset"])]
    rows=[]
    for k,value,unit,components in specs:
        row=evidence_row(**common,evidence_key=f"2205719:{k}:reviewed",variable_key=k,value=value,unit=unit,
            allowed_routes=[ROUTES[c] for c in components],ombudsman_components=components)
        if k=="ombudsman_asset_unit_reference":
            row.update(source_study_year=2020,price_assumption_year=2024,
                limitation="2020연구420만원을2024참고액으로준용후2025부터물가적용하는정답가정.2021~2024가격보정 미확인,최신공식집기단가아님")
        if k=="ombudsman_meeting_unit":
            row.update(price_policy="추계기간동결",cost_basis="국가업무조력자사례금 참석비·교통비·식비포함, 일반위원회수당과구분")
        if k in {"ombudsman_nominal_rates","ombudsman_cpi_rates"}:
            row["forecast_vintage"]="2024-10"
        rows.append(row)
    return rows


def prepare_ombudsman(payload):
    component=payload.get("ombudsman_component")
    if component not in ROUTES or payload.get("route_key")!=ROUTES[component]:
        raise ValueError("ombudsman component/formula mismatch")
    if payload.get("ombudsman_model_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["ombudsman_confirmation"],"support_derivation_trace":[]}
    if component=="initial_asset" and not str(payload.get("ombudsman_asset_price_note") or "").strip():
        return {**payload,"support_missing_operands":["ombudsman_asset_price_confirmation"],"support_derivation_trace":[]}
    start,years=payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("ombudsman horizon required")
    units={r["variable_key"]:r["unit"] for r in ombudsman_rows() if component in r["ombudsman_components"]}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","duration","payments_per_year")):
        raise ValueError("no duplicate inflation/duration/monthly multiplier")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        xs=list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in xs):
            raise ValueError("invalid ombudsman operand/unit")
    v={k:row.value for k,row in r.items()};offices=v["ombudsman_offices"]
    for k in ("ombudsman_offices","ombudsman_heads_per_office","ombudsman_professional_per_office","ombudsman_reference_professionals"):
        if k in v and v[k]!=int(v[k]):
            raise ValueError("office and personnel counts must be integers")
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    source="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    def operand(value,unit):
        return dict(value=value,unit=unit,source_ref=source,is_assumption=True)
    if component=="meeting":
        calculated.update(service_quantity=operand(offices*v["ombudsman_heads_per_office"],"person"),
            service_unit_cost=operand(v["ombudsman_meeting_unit"],"KRW/person/meeting"),frequency_per_year=operand(v["ombudsman_meetings_per_year"],"meeting/year"))
        amount=offices*v["ombudsman_heads_per_office"]*v["ombudsman_meeting_unit"]*v["ombudsman_meetings_per_year"]
        trace=[dict(year=y,component=component,amount_won=amount,appointee_salary_included=False) for y in range(start,start+years)]
    else:
        base=v["ombudsman_package_base_year"]
        if base!=2024 or start<=base:
            raise ValueError("reviewed2024 package basis required")
        rates=v["ombudsman_nominal_rates"] if component=="personnel" else v["ombudsman_cpi_rates"]
        end=start if component=="initial_asset" else start+years-1
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(base+1,end+1)):
            return {**payload,"support_missing_operands":["ombudsman_forecast_year_coverage"],"support_derivation_trace":[]}
        factors=[prod(1+rates[str(y)] for y in range(base+1,year+1)) for year in range(start,end+1)]
        if component=="personnel":
            if v["ombudsman_reference_professionals"]<=0:
                raise ValueError("professional reference staffing required")
            n=offices*v["ombudsman_professional_per_office"]
            prices=[v["ombudsman_reference_payroll"]/v["ombudsman_reference_professionals"]*f for f in factors]
            calculated.update(headcount=operand(n,"person"),salary_per_person=operand(prices,"KRW/person/year"))
            amounts=[n*p for p in prices]
        elif component=="operation":
            prices=[v["ombudsman_reference_operations"]*f for f in factors]
            calculated.update(quantity=operand(offices,"office"),unit_cost=operand(prices,"KRW/office/year"))
            amounts=[offices*p for p in prices]
        else:
            n=offices*(v["ombudsman_heads_per_office"]+v["ombudsman_professional_per_office"])
            price=v["ombudsman_asset_unit_reference"]*factors[0]
            calculated.update(headcount=operand(n,"person"),asset_unit_price_per_person=operand(price,"KRW/person"),duration=operand(1,"year"))
            amounts=[n*price]+[0]*(years-1)
        trace=[dict(year=start+i,component=component,amount_won=a,base_year=base,professional_pay_not_civil_grade=component=="personnel") for i,a in enumerate(amounts)]
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}


def ombudsman_display_table(components):
    """Preserve raw KRW-thousand values and separately build the source-style table."""
    if set(components)!=set(ROUTES):
        raise ValueError("all four ombudsman components required for combined display")
    lengths={len(v) for v in components.values()}
    if len(lengths)!=1 or not lengths or next(iter(lengths))<1:
        raise ValueError("component horizons must match")
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for values in components.values() for x in values):
        raise ValueError("computed nonnegative component amounts required")
    years=next(iter(lengths))
    displayed={k:[round(x/1000) for x in v] for k,v in components.items() if k!="meeting"}
    meetings=[x/1000 for x in components["meeting"]]
    totals=[round(sum(v[i] for v in displayed.values())+meetings[i]) for i in range(years)]
    return dict(component_million=displayed,meeting_million=meetings,annual_total_million=totals,
        summed_display_total_million=sum(totals),
        rounded_components_plus_meeting_total_million=sum(sum(v) for v in displayed.values())+sum(meetings))
