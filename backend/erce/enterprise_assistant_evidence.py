"""Annual service packages for self-employed severe-disabled entrepreneurs."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "enterprise_assistant_annual_support"
NOTES = ("assistant_task_note", "enterprise_projection_note", "assistant_take_up_note", "assistant_price_note", "assistant_timing_note")
BUDGET_BASIS = "official_budget_components"
OFFICIAL_URL = "https://www.nabo.go.kr/board/file/bulkDown.do?bid=19&idx=8830"


def enterprise_assistant_rows():
    common = dict(source_bill_no="2207221",available_at="2025-03-05",reviewed_at="2026-10-11",
        source_ref="2207221 비용추계서25A0014 PDF3~4쪽",agency="중소벤처기업부",
        policy_domain="1인 중증장애인기업 업무지원인",scope="근로자 없는 중증장애인 사업자의 연간 업무지원 인력서비스",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],variable_role="annual_service_operand",
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="기업수 성장·지원율·유사사업 연간단가를 준용한 가정. 근로자 활동지원·현금급여·시간당 단가와 구분. 현재 실적 아님")
    specs = [("solo_enterprise_history",{"2018":4494,"2020":6051,"2022":9142},"year_to_enterprise"),
        ("solo_enterprise_growth",.194,"ratio/year"), ("assistant_take_up",.5,"ratio"),
        ("assistant_annual_price",21900000,"KRW/person/year"), ("assistant_price_base_year",2025,"year"),
        ("assistant_price_growth",.017,"ratio/year"), ("assistant_public_share",1,"ratio")]
    rows = [evidence_row(**common,evidence_key=f"2207221:{key}:reviewed",variable_key=key,value=value,unit=unit)
            for key,value,unit in specs]
    budget = {**common,"source_bill_no":"official:nabo:2024_settlement_labor:202507",
        "agency":"고용노동부","scope":"중증장애인 근로자 지원2024·2025 예산편성 구성요소를 자영업자 업무지원에 준용할 후보",
        "available_at":"2025-07-25","source_ref":"NABO2025.7 2024회계연도 결산 위원회별 분석 환경노동위원회 PDF324쪽(인쇄308쪽) 고용노동부 제출자료",
        "source_url":OFFICIAL_URL,"source_class":"official_standard","independently_verified":True,
        "obtained_from":"official_public_data","assistant_operand_basis":BUDGET_BASIS,
        "limitation":"2024·2025 실제 예산편성 구성요소. 신규 자영업자 사업에 준용·지원시간 및 집행률 고정은 별도 가정; 최신2026기준 아님"}
    for key,value,unit in (("assistant_hourly_price_2024",14843,"KRW/hour"),
        ("assistant_hourly_price_2025",15092,"KRW/hour"),("assistant_monthly_hours",125,"hour/month"),
        ("assistant_payment_months",12,"month/year"),("assistant_budget_execution_factor_2024",.98406,"ratio"),
        ("assistant_price_base_year",2024,"year")):
        rows.append(evidence_row(**budget,evidence_key=f"official:nabo:assistant:{key}:202507",
            variable_key=key,value=value,unit=unit))
    return rows


def prepare_enterprise_assistant(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("annual assistant service route required")
    if payload.get("assistant_continuation_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["assistant_continuation_confirmation"],"support_derivation_trace":[]}
    start, years = payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("assistant service forecast horizon required")
    offset = payload.get("reviewed_assistant_price_year_offset",0)
    if isinstance(offset,bool) or offset not in (0,1):
        raise ValueError("invalid assistant price year offset")
    if offset and (payload.get("bill_no")!="2207221" or payload.get("evidence_mode")!="development_review"
            or not str(payload.get("assistant_price_year_discrepancy_note") or "").strip()):
        raise ValueError("disputed annual price year is own-bill replay only")
    basis = payload.get("assistant_operand_basis","published_rounded")
    if basis not in {"published_rounded",BUDGET_BASIS}:
        raise ValueError("unknown assistant operand basis")
    if basis == BUDGET_BASIS and offset:
        raise ValueError("verified 2024 budget price year requires no extra replay offset")
    units = {r["variable_key"]:r["unit"] for r in enterprise_assistant_rows()
             if r.get("assistant_operand_basis") == (BUDGET_BASIS if basis == BUDGET_BASIS else None)}
    if basis == BUDGET_BASIS:
        units.update(solo_enterprise_history="year_to_enterprise",assistant_take_up="ratio",assistant_public_share="ratio")
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","payments_per_year")):
        raise ValueError("no duplicate inflation or monthly multiplier on annual service prices")
    r, missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        xs = list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in xs):
            raise ValueError("invalid assistant service operand/unit")
    v = {k:row.value for k,row in r.items()}; history=v["solo_enterprise_history"]
    if not isinstance(history,dict) or not history or any(not isinstance(k,str) or not k.isdigit() for k in history):
        raise ValueError("dated enterprise history required")
    base_year = max(map(int,history)); base_count=history[str(base_year)]; price_year=v["assistant_price_base_year"]
    if basis == BUDGET_BASIS:
        first_year=min(map(int,history)); first_count=history[str(first_year)]
        if first_year==base_year or first_count<=0 or v["assistant_hourly_price_2024"]<=0 or price_year!=2024:
            raise ValueError("dated history and verified budget base required")
        if not 0<v["assistant_payment_months"]<=12 or not 0<v["assistant_budget_execution_factor_2024"]<=1:
            raise ValueError("invalid annual budget components")
        v["solo_enterprise_growth"]=(base_count/first_count)**(1/(base_year-first_year))-1
        v["assistant_annual_price"]=v["assistant_hourly_price_2024"]*v["assistant_monthly_hours"]*v["assistant_payment_months"]*v["assistant_budget_execution_factor_2024"]
        v["assistant_price_growth"]=v["assistant_hourly_price_2025"]/v["assistant_hourly_price_2024"]-1
    if (base_year>start or price_year!=int(price_year) or price_year>start
            or not 0<=v["assistant_take_up"]<=1 or not 0<=v["assistant_public_share"]<=1
            or any(x!=int(x) for x in history.values())):
        raise ValueError("invalid enterprise count/price years or support shares")
    counts=[];prices=[];trace=[]
    for year in range(start,start+years):
        enterprises=base_count*(1+v["solo_enterprise_growth"])**(year-base_year)
        recipients=enterprises*v["assistant_take_up"]
        price=v["assistant_annual_price"]*(1+v["assistant_price_growth"])**(year-price_year+offset)
        counts.append(recipients);prices.append(price)
        trace.append(dict(year=year,projected_enterprises=enterprises,enterprise_base_year=base_year,
            take_up=v["assistant_take_up"],recipients=recipients,annual_price_won=price,price_base_year=price_year,
            price_year_offset=offset,amount_won=recipients*price*v["assistant_public_share"],
            estimation_scope="gross_public_service_support_scenario"))
        trace[-1].update(operand_basis=basis,enterprise_growth=v["solo_enterprise_growth"],
            annual_base_price_won=v["assistant_annual_price"],annual_price_growth=v["assistant_price_growth"])
    ref="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    def operand(value,unit):
        return dict(value=value,unit=unit,source_ref=ref,is_assumption=True)
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated.update(recipient_count=operand(counts,"person"),annual_service_cost_per_person=operand(prices,"KRW/person/year"),
        public_support_share=operand(v["assistant_public_share"],"ratio"),cost_adjustment_factors=operand([1]*years,"ratio"))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
