"""Disjoint income bands and staged pensions; unknown payment factors stay missing."""
from math import isfinite
from backend.erce.common_population_evidence import population_series
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE="basic_pension_staged_increase"
BANDS={"lower30":.3,"between30_50":.2}


def staged_reference_amounts():
    # Round only the final annual amount, not the intermediate indexed base.
    old=[round(334810*1.025*1.021*(1.02**i)) for i in range(5)]
    new={"lower30":[round(400000*(1.02**i)) for i in range(5)],
         "between30_50":[old[0]]+[round(400000*(1.02**i)) for i in range(4)]}
    return old,new


def basic_pension_staged_rows():
    old,new=staged_reference_amounts()
    rows=[]
    for band in BANDS:
        for variable,value in (("benefit_per_recipient",new[band]),("existing_benefit_per_recipient",old)):
            rows.append(evidence_row(evidence_key=f"2203602:{band}:{variable}:2026-2030",
                variable_key=variable,value=value,unit="KRW/person/month",
                source_bill_no="2203602",available_at="2024-11-12",reviewed_at="2026-10-06",
                source_ref="2203602 비용추계서24C3532 PDF5쪽표3;2024.10물가전망및전년도물가연동",
                agency="국회예산정책처",policy_domain="기초연금",scope="국비지방비합산 기준연금액 증액",
                service_function=PROFILE,variable_role="indexed_base_rate",value_years=list(range(2026,2031)),
                support_derivation=PROFILE,pension_income_band=band,allowed_routes=["transfer_recipient_delta"],
                requires_applicability_note=True,obtained_from="reviewed_answer",independently_verified=False,
                rate_basis="gross_indexed_reference",
                calculation_basis="2024기준334810원×2024물가2.5%×2025물가2.1%로2026액산정;이후연2%누적.2026또는2027신규400000원 이후연2%;중간반올림없이최종연도액반올림",
                limitation="기준액이지감액후실수령액아님.해당시작연도·소득구간인상후물가연동 가정.수급률·평균차액지급계수는별도로필요.연2%는역사적표계속인상가정이며최신물가전망아님"))
        rows.append(evidence_row(evidence_key=f"kosis_202312:age65_population:{band}:2026-2030:pension",
            variable_key="pension_elderly_population",value=population_series("age65_population",2026,5),unit="person",
            source_bill_no="official:kosis:DT_1BPA001:202312",available_at="2023-12-14",reviewed_at="2026-10-06",
            source_ref="공식KOSIS2023.12중위전망 성연령별인구65세이상 합계",
            source_url="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1BPA001",
            agency="통계청",policy_domain="기초연금",scope="전국65세이상 인구",
            service_function=PROFILE,variable_role="population",source_class="official_standard",
            value_years=list(range(2026,2031)),support_derivation=PROFILE,pension_income_band=band,
            allowed_routes=["transfer_recipient_delta"],independently_verified=True,
            limitation="인구는수급자가아님.구간폭·실제수급률·차액지급계수1회적용.2023.12전망버전"))
    return rows


def prepare_basic_pension_staged(payload):
    band=payload.get("pension_income_band")
    if payload.get("route_key")!="transfer_recipient_delta" or band not in BANDS or payload.get("start_year")!=2026 or payload.get("years")!=5:
        raise ValueError("basic pension staged period, route or band mismatch")
    if payload.get("pension_payment_model")!="proportional_increment_reviewed" or any(
        not str(payload.get(k) or "").strip() for k in ("support_derivation_note","pension_payment_factor_note","estimation_start_note")):
        raise ValueError("basic pension needs reviewed differential payment and start assumptions")
    if payload.get("pension_rate_basis")=="national_2021_2023_average_proxy" and (
            payload.get("use_national_pension_proxy") is not True or not str(payload.get("pension_proxy_confirmation_note") or "").strip()):
        raise ValueError("national pension proxy must be explicitly selected and explained")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("basic pension duplicate adjustments forbidden")
    units={"pension_elderly_population":"person","pension_take_up":"ratio","pension_delta_payment_factor":"ratio"}
    r,missing=resolve_formula_variables(tuple(units),**layers);data={}
    for k,v in r.items():
        vals=list(v.value) if isinstance(v.value,(list,tuple)) else [v.value]*5
        if v.unit!=units[k] or not v.source_ref or len(vals)!=5 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 or (units[k]=="ratio" and x>1) for x in vals):
            raise ValueError("invalid pension population or rate")
        data[k]=vals
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    upper,_=resolve_formula_variables(("recipient_count",),**layers)
    if not missing:
        vals=[data["pension_elderly_population"][i]*BANDS[band]*data["pension_take_up"][i]*data["pension_delta_payment_factor"][i] for i in range(5)]
        refs="; ".join(dict.fromkeys(v.source_ref for v in r.values()))
        if "recipient_count" not in upper:calculated["recipient_count"]=dict(value=vals,unit="person",source_ref=refs,is_assumption=True)
        trace.append(dict(variable_key="recipient_count",values=vals,unit="person",dependencies=list(units),
            expression=f"65세이상인구×분리소득구간폭{BANDS[band]}×수급률×평균차액지급계수;회복액가중인원",source_ref=refs,applied="recipient_count" not in upper))
    return {**payload,"calculated_inputs":calculated,"support_derivation_trace":trace,
        "support_missing_operands":[] if "recipient_count" in upper else list(missing)}
