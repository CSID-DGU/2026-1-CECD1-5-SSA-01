from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="housing_moving_brokerage_bundle"
TENANTS=[1432427,1444614,1455971,1466533,1476445]


def housing_updated_rows():
    common=dict(source_bill_no="2209844",available_at="2025-08-22",reviewed_at="2026-10-08",
        source_ref="2209844 비용추계서25B2324 PDF7~13쪽",agency="국토교통부",policy_domain="주거급여",
        scope="중위48%임차일반+청년분리가구2027~2031",requires_applicability_note=True,
        obtained_from="reviewed_answer",independently_verified=False,
        housing_income_cutoff="median_income_48_percent",
        limitation="정답참고가정/표전망.새고시·최신공식전망이아님;정답전체금액역산안함")
    rows=[]
    for profile in ("housing_management_fee",PROFILE):
        route="transfer_recipient"
        data=[("tenant_households",TENANTS,"household",{}),
              ("management_cpi_forecast",{"2025":.019,**{str(y):.02 for y in range(2026,2032)}},"year_to_ratio",{})]
        if profile=="housing_management_fee":
            data += [("arrears_share",.102,"ratio",dict(management_fee_scenario="arrears_shared")),
                ("management_public_share",.5,"ratio",dict(management_fee_scenario="arrears_shared")),
                ("reported_monthly_common_fee",68000,"KRW/household/month",dict(management_fee_scenario="arrears_shared",management_price_base_year=2024)),
                ("flat_monthly_fee",30000,"KRW/household/month",dict(management_fee_scenario="all_tenants_flat",management_price_base_year=2027))]
        else:
            data += [("moving_plan_share",.02,"ratio",{}),("baseline_supported_households",15000,"household/year",{}),
                ("moving_bundle_unit",400000,"KRW/household/event",dict(moving_price_base_year=2025))]
        for key,value,unit,extra in data:
            rows.append(evidence_row(evidence_key=f"2209844:{profile}:{key}:reviewed",variable_key=key,value=value,unit=unit,
                service_function=profile,support_derivation=profile,variable_role="scenario_operand",allowed_routes=[route],
                **common,**extra,**({"value_years":list(range(2027,2032))} if key=="tenant_households" else {})))
    return rows


def prepare_housing_moving(payload):
    if payload.get("route_key")!="transfer_recipient" or payload.get("moving_cost_bundle_confirmed") is not True:
        raise ValueError("moving and brokerage must be one confirmed bundle")
    if payload.get("moving_repeat_exclusion_years")!=2 or not all(str(payload.get(k) or "").strip() for k in
            ("moving_scope_note","baseline_support_note","moving_history_note","support_derivation_note")):
        raise ValueError("moving eligibility/baseline/history confirmations required")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","participation_rate","subsidy_rate","payments_per_year")):
        raise ValueError("moving duplicate price/share/payment forbidden")
    units={"tenant_households":"household","management_cpi_forecast":"year_to_ratio","moving_plan_share":"ratio",
        "baseline_supported_households":"household/year","moving_bundle_unit":"KRW/household/event"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    v={k:row.value for k,row in r.items()}
    if any(not isinstance(v[k],(int,float)) or isinstance(v[k],bool) for k in
           ("moving_plan_share","baseline_supported_households","moving_bundle_unit")):
        raise ValueError("moving scalar operands required")
    for k,row in r.items():
        arr=list(row.value.values()) if isinstance(row.value,dict) else row.value if isinstance(row.value,list) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x)
                or (x<=-1 if k=="management_cpi_forecast" else x<0) or (units[k]=="ratio" and x>1) for x in arr):
            raise ValueError("moving operand mismatch")
    start=payload.get("start_year");years=payload.get("years",5);base=payload.get("moving_price_base_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"],"support_derivation_trace":[]}
    if not isinstance(base,int) or isinstance(base,bool) or base>start:raise ValueError("moving price base year mismatch")
    pops=v["tenant_households"];rates=v["management_cpi_forecast"]
    if not isinstance(pops,list) or len(pops)!=years or not isinstance(rates,dict):raise ValueError("moving horizon mismatch")
    if any(str(y) not in rates for y in range(base+1,start+years)):
        return {**payload,"support_missing_operands":["cpi_year_coverage"]}
    history=payload.get("prior_moving_supported_households")
    if history is None:return {**payload,"support_missing_operands":["prior_moving_supported_households"]}
    if not isinstance(history,list) or len(history)!=2 or any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in history):
        raise ValueError("moving history needs two actual integer cohorts")
    gross=[];net=[];prices=[];trace=[]
    for i,n in enumerate(pops):
        excluded=sum((history+gross)[-2:])
        supported=int(round(max(0,n-excluded)*v["moving_plan_share"]))
        eligible=max(0,supported-v["baseline_supported_households"])
        price=v["moving_bundle_unit"]*prod(1+rates[str(y)] for y in range(base+1,start+i+1))
        gross.append(supported);net.append(eligible);prices.append(price)
        trace.append(dict(year=start+i,households=n,prior_two_years_supported=excluded,gross_moving_households=supported,
            baseline_households=v["baseline_supported_households"],incremental_households=eligible,unit_price=price,
            expression="round((가구−직전2년지원가구)×이사비율)−기지원가구,회당패키지1회"))
    calculated=dict(payload.get("calculated_inputs") or {});source="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    for k,value,unit in (("recipient_count",net,"person"),("benefit_per_recipient",prices,"KRW/person/event"),("payments_per_year",1,"event/year")):
        calculated[k]=dict(value=value,unit=unit,source_ref=source,is_assumption=True)
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
