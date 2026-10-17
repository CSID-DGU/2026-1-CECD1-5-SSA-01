"""Sector-specific levy expenses and separately labelled reference receipts."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE="employment_levy_sector_delta"
EXPENSE="government_employment_levy_delta"
RECEIPTS="employment_levy_reference_receipts"
NOTES=("levy_sector_scope_note","levy_band_allocation_note","levy_sector_timing_note","levy_unpriced_zero_band_note")


def levy_sector_rows():
    common=dict(source_bill_no="2208360",available_at="2025-06-23",reviewed_at="2026-10-11",
        source_ref="2208360 비용추계서25B1029 PDF5·8~13쪽",agency="고용노동부",
        policy_domain="장애인고용부담금 부문별 증감",scope="정부 지출과 정부·공공기관·민간 납부에 따른 참고수입",
        service_function=PROFILE,support_derivation=PROFILE,levy_sector_model="direct_sector_counts",
        variable_role="levy_sector_operand",allowed_routes=[EXPENSE,RECEIPTS],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="2024부문별 미고용인원 동결·2025고시 및 과거전망 준용. 행태변화·감면 미반영; 공공기관·민간을 정부지출에 합치지 않음")
    sectors={k:{str(i+1):n for i,n in enumerate(v)} for k,v in dict(civil=[735,4301,5720,0,3],
        non_civil=[397,492,102,0,0],public_institution=[658,527,323,42,8],private=[6172,15056,13663,3948,3890]).items()}
    specs=[("levy_sector_unfilled",sectors,"sector_band_to_person"),
        ("levy_old_bands",dict(zip(map(str,range(1,6)),[1258000,1333480,1509600,1761200,2096270])),"band_to_KRW/month"),
        ("levy_minimum_monthly_base",2096270,"KRW/month"),("levy_price_base_year",2025,"year"),
        ("levy_old_floor_share",.6,"ratio"),("levy_new_floor_share",.8,"ratio"),
        ("levy_band_difference_weight",.5,"ratio"),("levy_zero_employment_share",1,"multiplier"),
        ("levy_payment_months",12,"month/year")]
    rows=[evidence_row(**common,evidence_key=f"2208360:{k}:reviewed",variable_key=k,value=v,unit=u) for k,v,u in specs]
    rows[0].update(observation_year=2024,scale_basis="2024년12월말 부문별 의무고용 미달인원 동결")
    rows[1].update(price_year=2025)
    rows.append(evidence_row(**{**common,"source_bill_no":"2207081","available_at":"2025-03-20",
        "source_ref":"2207081 비용추계서24B6384 PDF9쪽 표7 현행i=5 월최저임금전망;2025기준은고용부2024-99호 인용",
        "limitation":"2024.11동일전망시점의 다른검토선례 거시단가 재사용. 최신확정임금이나 새로운의안의미고용인원·총액 아님"},
        evidence_key="2207081:minimum_monthly_forecast:202411:sector_levy",
        variable_key="levy_monthly_forecast_levels",value=dict(zip(map(str,range(2025,2031)),[2096270,2177009,2259346,2344434,2432823,2526270])),
        unit="year_to_KRW/month",forecast_vintage="2024-11"))
    rows.append(evidence_row(**common,evidence_key="2208360:published_band_delta_price_card:2026",
        variable_key="levy_band_delta_price_card",unit="reviewed_band_delta_card",
        value=dict(reference_minimum_monthly=2177009,monthly_delta_by_band={"1":435155,"2":395972,"3":304547,"4":173938,"5":0},
                   old_floor=.6,new_floor=.8,difference_weight=.5,zero_share=1),
        levy_tariff_basis="published_unit_price_card",price_year=2026,forecast_vintage="2024-11",
        price_derivation="25B1029 표8 공개 월기초액 차액/같은2026월최저임금. 총수입·지출에서 역산하지 않음"))
    return rows


def prepare_levy_sectors(payload):
    route=payload.get("route_key")
    if route not in {EXPENSE,RECEIPTS} or payload.get("levy_sector_model")!="direct_sector_counts":
        raise ValueError("sector levy route/model required")
    if payload.get("levy_sector_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["levy_sector_confirmation"],"support_derivation_trace":[]}
    if payload.get("fiscal_reporting")!="separate_revenue_and_expenditure":
        raise ValueError("do not net reference receipts with government expenses")
    if route==RECEIPTS and (payload.get("estimate_purpose")!="reference_scenario" or not str(payload.get("reference_notice") or "").strip()):
        raise ValueError("levy receipts need explicit reference disclosure")
    start,years=payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("dated levy horizon required")
    basis=payload.get("levy_tariff_basis","derived_legal_floor")
    if basis not in {"derived_legal_floor","published_unit_price_card"}:
        raise ValueError("unknown levy tariff basis")
    if basis=="published_unit_price_card" and (payload.get("levy_price_card_reuse_confirmed") is not True
            or not str(payload.get("levy_price_card_scope_note") or "").strip()):
        return {**payload,"support_missing_operands":["levy_price_card_confirmation"],"support_derivation_trace":[]}
    units={r["variable_key"]:r["unit"] for r in levy_sector_rows()
           if not r.get("levy_tariff_basis") or r["levy_tariff_basis"]==basis}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("government_non_civil_share","growth_rate","revenue_netting")):
        raise ValueError("sector counts replace non-civil ratio proxies; no double growth or netting")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    def valid(x):
        if isinstance(x,dict):
            return all(valid(v) for v in x.values())
        return not isinstance(x,bool) and isinstance(x,(int,float)) and isfinite(x) and x>=0
    if any(row.unit!=units[k] or not row.source_ref or not valid(row.value) for k,row in r.items()):
        raise ValueError("invalid sector levy operand/unit")
    v={k:row.value for k,row in r.items()}; bands=list(map(str,range(1,6))); sectors=v["levy_sector_unfilled"]
    if not isinstance(sectors,dict) or set(sectors)!={"civil","non_civil","public_institution","private"}:
        raise ValueError("all four sector groups required")
    if any(not isinstance(c,dict) or set(c)!=set(bands) or any(n!=int(n) for n in c.values()) for c in sectors.values()):
        raise ValueError("five integer-count bands per sector required")
    old=v["levy_old_bands"];base=v["levy_minimum_monthly_base"]
    if (not isinstance(old,dict) or set(old)!=set(bands) or base<=0 or old["5"]!=base
        or v["levy_price_base_year"]!=2025 or v["levy_old_floor_share"]!=.6 or v["levy_new_floor_share"]!=.8 or v["levy_zero_employment_share"]!=1
        or not 0<=v["levy_band_difference_weight"]<=.5 or not 0<v["levy_payment_months"]<=12):
        raise ValueError("reviewed 60-to-80 floor with unpriced zero-band change required")
    old_share={b:old[b]/base for b in bands}
    new_share={b:v["levy_new_floor_share"]+v["levy_band_difference_weight"]*(old_share[b]-v["levy_old_floor_share"]) for b in bands}
    new_share["1"]=.8;new_share["5"]=1
    delta_share={b:new_share[b]-old_share[b] for b in bands}
    if basis=="published_unit_price_card":
        card=v["levy_band_delta_price_card"]
        if (not isinstance(card,dict) or card.get("reference_minimum_monthly",0)<=0
                or not isinstance(card.get("monthly_delta_by_band"),dict) or set(card["monthly_delta_by_band"])!=set(bands)
                or card.get("old_floor")!=v["levy_old_floor_share"] or card.get("new_floor")!=v["levy_new_floor_share"]
                or card.get("difference_weight")!=v["levy_band_difference_weight"] or card.get("zero_share")!=v["levy_zero_employment_share"]):
            raise ValueError("published unit card applies only to the matching reviewed amendment")
        delta_share={b:card["monthly_delta_by_band"][b]/card["reference_minimum_monthly"] for b in bands}
        new_share={b:old_share[b]+delta_share[b] for b in bands}
    prices=v["levy_monthly_forecast_levels"];annual=[];trace=[]
    for year in range(start,start+years):
        price_year=year-1
        if not isinstance(prices,dict) or str(price_year) not in prices:
            return {**payload,"support_missing_operands":["levy_price_year_coverage"],"support_derivation_trace":[]}
        values={sector:sum(c[b]*delta_share[b]*prices[str(price_year)]*v["levy_payment_months"] for b in bands) for sector,c in sectors.items()}
        amount=sum(values[k] for k in ("civil","non_civil")) if route==EXPENSE else sum(values.values())
        annual.append(amount)
        trace.append(dict(year=year,liability_year=price_year,sector_amounts_won=values,old_shares=old_share,new_shares=new_share,
            amount_won=amount,zero_band_increment_excluded=True,zero_band_effect_status="not_estimated",reference_receipts=route==RECEIPTS))
        trace[-1].update(tariff_basis=basis,monthly_delta_by_band={b:delta_share[b]*prices[str(price_year)] for b in bands},
                        price_card_scope_note=payload.get("levy_price_card_scope_note",""))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
