"""Reference scenarios for housing management fees; source bill version is unconfirmed."""
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="housing_management_fee"


def housing_management_rows():
    common=dict(source_bill_no="2207600",available_at="2026-10-08",reviewed_at="2026-10-08",
        source_ref="2207600 첨부24B5535 PDF5~9쪽;회답2024-12-23/발의2025-01-17버전불일치",
        agency="국토교통부",policy_domain="주거급여관리비",scope="전국임차급여일반+청년분리가구,중위소득48%이하",
        service_function=PROFILE,support_derivation=PROFILE,variable_role="reference_scenario_operand",
        source_bill_version_match=False,allowed_routes=["transfer_recipient"],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        housing_income_cutoff="median_income_48_percent",
        limitation="버전일치미확인첨부추계서의참고가정.최신공식대상·고시단가아님.전산/발굴조사비미포함")
    rows=[]
    data=[
        ("tenant_households",[1419292,1432427,1444613,1455971,1466533],"household",None),
        ("management_cpi_forecast",{"2025":.021,"2026":.02,"2027":.02,"2028":.02,"2029":.02,"2030":.02},"year_to_ratio",None),
        ("arrears_share",.108,"ratio","arrears_shared"),
        ("management_public_share",.5,"ratio","arrears_shared"),
        ("kapt_stock_2023",734547,"household","arrears_shared"),
        ("kapt_monthly_common_fees_2023",46801000000,"KRW/month","arrears_shared"),
        ("flat_monthly_fee",30000,"KRW/household/month","all_tenants_flat"),
    ]
    for key,value,unit,scenario in data:
        extra={}
        if key=="tenant_households":extra["value_years"]=list(range(2026,2031))
        if scenario:extra["management_fee_scenario"]=scenario
        if key=="flat_monthly_fee":extra["price_base_year"]=2024
        if "2023" in key:extra["observation_year"]=2023
        rows.append(evidence_row(evidence_key=f"2207600:management:{key}:reference",
            variable_key=key,value=value,unit=unit,**common,**extra))
    rows.append(evidence_row(evidence_key="official:kostat:cpi_actual_2024:housing",
        variable_key="cpi_2024_actual",value=.023,unit="ratio/year",source_bill_no="official:kostat:cpi_2024",
        available_at="2024-12-31",reviewed_at="2026-10-08",
        source_ref="통계청2024년12월및연간소비자물가동향,2024연간2.3%",
        source_url="https://www.kostat.go.kr/board.es?act=view&bid=213&list_no=434615&mid=a10301040200",
        agency="통계청",policy_domain="공통물가",scope="전국2024연간소비자물가상승률",
        service_function="official_cpi_actual",variable_role="historical_price_index",
        source_class="official_standard",observation_year=2024,independently_verified=True,
        requires_applicability_note=True,
        limitation="2024관측치.2024-12-23추계서가발간당시썼던전망값이라고표시하지않음"))
    return rows


def prepare_housing_management(payload):
    scenario=payload.get("management_fee_scenario")
    if payload.get("route_key")!="transfer_recipient" or scenario not in {"arrears_shared","all_tenants_flat"}:
        raise ValueError("housing scenario/route mismatch")
    if payload.get("housing_income_cutoff")!="median_income_48_percent" or payload.get("management_scope")!="common_fee_excluding_utilities":
        raise ValueError("housing eligibility or common-fee scope mismatch")
    if not all(str(payload.get(k) or "").strip() for k in ("support_derivation_note","housing_scenario_note","price_year_note","estimation_start_note")):
        raise ValueError("housing scenario/timing/price confirmations required")
    start=payload.get("start_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"]}
    years=payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("invalid housing forecast period")
    units={"tenant_households":"household","management_cpi_forecast":"year_to_ratio"}
    reported=payload.get("management_fee_unit_basis")=="reported_weighted_monthly"
    units.update({"arrears_share":"ratio","management_public_share":"ratio",
        "reported_monthly_common_fee":"KRW/household/month"} if scenario=="arrears_shared" and reported else
        {"arrears_share":"ratio","management_public_share":"ratio","kapt_stock_2023":"household",
        "kapt_monthly_common_fees_2023":"KRW/month","cpi_2024_actual":"ratio/year"} if scenario=="arrears_shared"
        else {"flat_monthly_fee":"KRW/household/month"})
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("participation_rate","growth_rate","growth_rates_by_year","subsidy_rate")):
        raise ValueError("housing duplicate adjustment/national share forbidden")
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        if row.unit!=units[k] or not row.source_ref:raise ValueError("housing source/unit mismatch")
    v={k:row.value for k,row in r.items()}
    pops=v["tenant_households"];forecast=v["management_cpi_forecast"]
    if not isinstance(pops,list) or len(pops)!=years or not isinstance(forecast,dict):
        raise ValueError("housing population/forecast shape mismatch")
    for k,x in v.items():
        values=list(x.values()) if isinstance(x,dict) else x if isinstance(x,list) else [x]
        if any(isinstance(a,bool) or not isinstance(a,(int,float)) or not isfinite(a)
               or (a<=-1 if "cpi" in k else a<0) or (units[k]=="ratio" and a>1) for a in values):
            raise ValueError("invalid housing operand")
    if scenario=="arrears_shared":
        if reported:
            monthly=v["reported_monthly_common_fee"];base_year=payload.get("management_price_base_year")
            if isinstance(base_year,bool) or not isinstance(base_year,int):raise ValueError("reported management price year required")
            rates=forecast
        else:
            if v["kapt_stock_2023"]<=0:raise ValueError("K-apt stock must be positive")
            monthly=v["kapt_monthly_common_fees_2023"]/v["kapt_stock_2023"]
            base_year=2023;rates={**forecast,"2024":v["cpi_2024_actual"]}
        count_share=v["arrears_share"];public_share=v["management_public_share"]
    else:
        monthly=v["flat_monthly_fee"];base_year=payload.get("management_price_base_year",2024);rates=forecast;count_share=public_share=1
    needed=list(range(base_year+1,start+years))
    if start<base_year or any(str(y) not in rates for y in needed):
        return {**payload,"support_missing_operands":["cpi_year_coverage"],"support_derivation_trace":[]}
    prices=[monthly*prod(1+rates[str(y)] for y in range(base_year+1,start+i+1))*public_share for i in range(years)]
    calculated=dict(payload.get("calculated_inputs") or {})
    source="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    for key,value,unit in (("recipient_count",[n*count_share for n in pops],"person"),
            ("benefit_per_recipient",prices,"KRW/person/month"),("payments_per_year",12,"month/year")):
        upper,_=resolve_formula_variables((key,),**layers)
        if key not in upper:calculated[key]=dict(value=value,unit=unit,source_ref=source,is_assumption=True)
    trace=[dict(year=start+i,scenario=scenario,base_price_year=base_year,base_monthly_common_fee=monthly,
        gross_households=pops[i],recipient_share=count_share,public_share=public_share,monthly_public_payment=prices[i],
        note="원단위에서물가보정,가구단위지원.국고83.61%분할은합산총액에재곱하지않음") for i in range(years)]
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
