"""Regional resident stock trend and explicitly approved eligibility proxies."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "regional_resident_benefit_trend"
SCOPE = "declining_regions_89_notice_2024_15"
NOTES = ("regional_population_scope_note", "regional_residence_proxy_note",
         "regional_trend_note", "regional_benefit_note")


def regional_resident_benefit_rows():
    return [evidence_row(evidence_key="2214355:regional_population_history:2021-2024",
        variable_key="regional_population_history",
        value={"2021":4785658,"2022":4745423,"2023":4744755,"2024":4715326},
        unit="year_to_person",source_bill_no="2214355",available_at="2025-12-23",reviewed_at="2026-10-13",
        source_ref="2214355 비용추계서25D6242 PDF3~4쪽 표2·PDF8~9쪽 시군구 관측인구",
        agency="통계청",policy_domain="인구감소지역 주민급여",
        scope="2024-15 지정고시89개지역 전연령 인구총조사 관측집계",
        regional_population_scope=SCOPE,service_function=PROFILE,support_derivation=PROFILE,
        variable_role="observed_regional_population_history",allowed_routes=[PROFILE],
        observation_years=[2021,2022,2023,2024],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="정답에 인용된 통계청 인구총조사 관측집계. 원KOSIS 독립확인 아님. 주민등록인구·2년계속거주자수 아님. 지역재지정·연령·통계기준 변경시전용금지")]


def prepare_regional_resident_benefit(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("regional resident benefit route required")
    if (payload.get("regional_model_confirmed") is not True
            or payload.get("regional_residence_filter_omission_approved") is not True
            or payload.get("regional_exclusion_filter_omission_approved") is not True
            or payload.get("regional_benefit_price_mode") != "freeze_legal_floor"
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["regional_population_proxy_confirmation"],
                "support_derivation_trace":[]}
    units = {"regional_population_history":"year_to_person",
             "regional_annual_benefit":"KRW/person/year","regional_national_share":"ratio"}
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values()
           for k in ("growth_rate","growth_rates_by_year","payments_per_year","participation_rate")):
        raise ValueError("regional population trend and annual benefit already account for timing/coverage")
    r,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        vals = list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if (row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool)
                or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in vals)):
            raise ValueError("invalid regional resident operand")
    history = r["regional_population_history"].value
    if not isinstance(history,dict) or len(history)<3:
        raise ValueError("regional population requires consecutive historical observations")
    pairs = sorted((int(y),n) for y,n in history.items())
    if (len(set(y for y,n in pairs))!=len(pairs)
            or any(b[0]!=a[0]+1 for a,b in zip(pairs,pairs[1:]))
            or any(n<=0 or int(n)!=n for y,n in pairs)):
        raise ValueError("invalid historical region years or counts")
    raw_rate = sum(b[1]/a[1]-1 for a,b in zip(pairs,pairs[1:]))/(len(pairs)-1)
    mode = payload.get("regional_trend_precision_mode","raw_mean")
    if mode not in {"raw_mean","published_percent_two_decimals"}:
        raise ValueError("unsupported trend precision")
    rate = round(raw_rate,4) if mode=="published_percent_two_decimals" else raw_rate
    if mode!="raw_mean" and not str(payload.get("regional_trend_precision_note") or "").strip():
        return {**payload,"support_missing_operands":["regional_trend_precision_note"],"support_derivation_trace":[]}
    start,years = payload.get("start_year"),payload.get("years",5)
    base,count = pairs[-1]
    if (isinstance(start,bool) or not isinstance(start,int) or start<=base
            or isinstance(years,bool) or not isinstance(years,int) or years<1):
        raise ValueError("historical observations must predate forecast")
    benefit,share = r["regional_annual_benefit"].value,r["regional_national_share"].value
    if not 0<=share<=1:
        raise ValueError("national share must be a ratio")
    component = payload.get("regional_fiscal_component")
    factors = {"public_total":1,"national":share,"local":1-share}
    if component not in factors:
        raise ValueError("choose total or a funding component; never sum total twice")
    annual,trace = [],[]
    for year in range(start,start+years):
        population = round(count*(1+rate)**(year-base))
        total = population*benefit
        annual.append(total*factors[component])
        trace.append(dict(year=year,population=population,population_base_year=base,
            population_base_count=count,raw_mean_growth_rate=raw_rate,applied_growth_rate=rate,
            trend_precision=mode,public_total_won=total,national_won=total*share,
            local_won=total*(1-share),selected_component=component,
            residence_filter_omitted=True,exclusion_filters_omitted=True))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(x.source_ref for x in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
            "support_derivation_trace":trace}
