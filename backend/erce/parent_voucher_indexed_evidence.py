"""Annual voucher increment with a separately dated retroactive payment."""
from datetime import date
from math import isfinite
from backend.erce.common_population_evidence import population_series
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "parent_benefit_voucher_annual_increment"


def parent_voucher_rows():
    rows=[]
    for age,base,rate,retro in ((0,567000,.0435,27000),(1,500000,.0443,25000)):
        common=dict(source_bill_no="2212022",available_at="2025-09-22",reviewed_at="2026-10-06",
            source_ref="2212022 비용추계서25C4271 PDF3~4쪽;2025보육바우처 및2022~2025평균상승률",
            source_url="backend/generated/assembly_22_pdfs/by_bill/2212022/cost_estimate.pdf",
            agency="보건복지부",policy_domain="부모급여 보육료연동",scope=f"전국 {age}세 바우처단가 증가분",
            service_function=PROFILE,support_derivation=PROFILE,parent_benefit_age=age,
            variable_role="voucher_increment_assumption",allowed_routes=["direct_annual_amount"],
            requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
            limitation="정답의2025바우처/과거평균상승률·집행계수. 최신공식단가 아님. 부모급여 전체100/50만원 또는 CPI에 곱하지 않음")
        for key,value,unit in (("voucher_base_monthly",base,"KRW/person/month"),
                ("voucher_growth_rate",rate,"ratio/year"),("execution_rate",.985,"ratio"),
                ("retro_monthly_increment",retro,"KRW/person/month")):
            rows.append(evidence_row(evidence_key=f"2212022:voucher:age{age}:{key}:reviewed",
                variable_key=key,value=value,unit=unit,**common,
                observation_year=2025,benefit_index_base_year=2025,
                **({"retro_increment_year":2025} if key=="retro_monthly_increment" else {})))
        rows.append(evidence_row(evidence_key=f"kosis_202312:age{age}:retro_population:2025:voucher",
            variable_key="retro_population",value=population_series(f"age{age}_population",2025,1)[0],unit="person",
            source_bill_no="official:kosis:DT_1BPA001:202312",available_at="2023-12-14",
            reviewed_at="2026-10-06",source_ref="KOSIS 전국2023.12중위2025연령별 전망인구",
            agency="통계청",policy_domain="공통인구",scope=f"전국 {age}세 2025년 소급대상 인구후보",
            service_function=PROFILE,support_derivation=PROFILE,parent_benefit_age=age,
            variable_role="population_proxy",source_class="official_standard",observation_year=2025,
            population_geography="전국",statistical_sex="total",population_vintage="2023-12",
            allowed_routes=["direct_annual_amount"],independently_verified=True,requires_applicability_note=True))
    return rows


def prepare_parent_voucher(payload):
    age=payload.get("parent_benefit_age")
    if isinstance(age,bool) or age not in (0,1) or payload.get("route_key")!="direct_annual_amount":
        raise ValueError("voucher age/route mismatch")
    if payload.get("voucher_projection_basis")!="annual_increment_not_cumulative" or payload.get("fiscal_scope")!="national_and_local_combined":
        raise ValueError("voucher projection/accounting basis must be confirmed")
    if not all(str(payload.get(k) or "").strip() for k in
               ("support_derivation_note","voucher_overlap_note","population_proxy_note","estimation_start_note")):
        raise ValueError("voucher applicability confirmations missing")
    start=payload.get("start_year");base=payload.get("benefit_index_base_year");years=payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(base,bool) or base!=start-1 or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("voucher forecast must start after base year")
    effective=date.fromisoformat(payload.get("law_effective_date",""))
    retro=date.fromisoformat(payload.get("retroactive_date",""))
    if effective.year!=start or effective.day!=1 or retro.year!=base or retro.day!=1:
        raise ValueError("only first-of-month commencement and preceding-year retro supported")
    units={f"age{age}_population":"person","voucher_base_monthly":"KRW/person/month",
        "voucher_growth_rate":"ratio/year","execution_rate":"ratio","retro_population":"person",
        "retro_monthly_increment":"KRW/person/month"}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        arr=row.value if isinstance(row.value,list) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not isfinite(v) or v<0 for v in arr):
            raise ValueError("voucher operand unit/value/source mismatch")
        if k!=f"age{age}_population" and isinstance(row.value,list):raise ValueError("voucher scalar required")
    v={k:row.value for k,row in r.items()};pops=v[f"age{age}_population"]
    if not isinstance(pops,list) or len(pops)!=years or not 0<=v["execution_rate"]<=1:
        raise ValueError("voucher population horizon/execution rate mismatch")
    selected={**(payload.get("selected_variable_inputs") or {}),**(payload.get("official_inputs") or {})}
    for key in ("retro_population","retro_monthly_increment"):
        source=selected.get(key,{})
        source_year=source.get("retro_increment_year",source.get("observation_year"))
        if source_year is not None and source_year!=retro.year:raise ValueError("retro source year mismatch")
    if any(k in (payload.get(layer) or {}) for layer in ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs")
           for k in ("growth_rate","participation_rate","subsidy_rate")):
        raise ValueError("voucher duplicate growth/execution/share forbidden")
    deltas=[v["voucher_base_monthly"]*(1+v["voucher_growth_rate"])**i*v["voucher_growth_rate"] for i in range(years)]
    retro_cost=v["retro_population"]*v["retro_monthly_increment"]*(13-retro.month)*v["execution_rate"]
    amounts=[];trace=[]
    for i,n in enumerate(pops):
        months=13-effective.month if i==0 else 12
        regular=n*deltas[i]*months*v["execution_rate"]
        extra=retro_cost if i==0 else 0
        amounts.append(regular+extra)
        trace.append(dict(year=start+i,age=age,population=n,monthly_increment=deltas[i],
            paid_months=months,execution_rate=v["execution_rate"],regular_won=regular,retro_won=extra,
            retro_months=13-retro.month if i==0 else 0,
            expression="인구×바우처기준월액×(1+상승률)^연차×상승률×개월×집행계수 + 첫해소급분"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=amounts,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(x.source_ref for x in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
