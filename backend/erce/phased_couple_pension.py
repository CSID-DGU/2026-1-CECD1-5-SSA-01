"""Scoped annual reduction schedules and observation-based trend scenarios."""
from math import isfinite
from backend.erce.common_population_evidence import population_series
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="phased_couple_pension"


def phased_couple_rows():
    history=[dict(year=y,recipients=n,couple_both=c,mean_payment=p,standard=s) for y,n,c,p,s in (
        (2021,5973059,2564894,265571,300000),(2022,6238798,2694394,271852,307500),
        (2023,6508574,2835116,284804,323180),(2024,6758487,2968660,292380,334810))]
    return [
        evidence_row(evidence_key="mohw_pension_2024:recipient_history:2021-2024:phased",
            variable_key="pension_recipient_history",value=history,unit="recipient_history",
            source_bill_no="public:mohw:pension_statistics_2024",available_at="2026-01-21",reviewed_at="2026-10-06",
            source_ref="보건복지부 통계로본2024년기초연금 PDF11·12·42쪽;통계청2023.12연앙인구",
            source_url="https://www.jejubokji.net/jcsw/board/statistics/75690/38187",
            agency="보건복지부",policy_domain="기초연금",scope="전국수급자2021~2024명단위",
            service_function=PROFILE,variable_role="historical_actual",support_derivation=PROFILE,
            allowed_routes=["transfer_population_amount_delta"],requires_applicability_note=True,
            observation_years=[2021,2022,2023,2024],valid_from_year=2026,valid_to_year=2030,
            independently_verified=True,raw_source_file="backend/generated/erce_official_sources/mohw_basic_pension_2024.pdf",
            limitation="보건복지부원문을공개복지기관미러에서확인.2024자료공개일확인불완전으로미러게시2026-01-21부터허용.전국평균에서유형별비선형감액교차자료는복원되지않음"),
        evidence_row(evidence_key="2211669:standard_monthly:2026-2030:202503",
            variable_key="pension_standard_forecast",value=[349010,355990,363110,370372,377780],unit="KRW/person/month",
            source_bill_no="2211669",available_at="2025-08-11",reviewed_at="2026-10-06",
            source_ref="2211669 비용추계서25C3952 PDF4쪽표3:2025기준342510원+2025.3물가전망",
            agency="국회예산정책처",policy_domain="기초연금",scope="전국2026~2030역사적기준연금전망",
            service_function=PROFILE,variable_role="forecast_standard",support_derivation=PROFILE,
            allowed_routes=["transfer_population_amount_delta"],requires_applicability_note=True,
            value_years=list(range(2026,2031)),pension_standard_vintage="2025_03_reviewed_forecast",
            base_year=2025,base_monthly=342510,independently_verified=False,obtained_from="reviewed_answer",
            limitation="역사적전망기준액이지2026실제고시349700원등최신실측값아님.정답총액에서역산하지않음")]


def prepare_phased_couple(payload):
    if payload.get("route_key")!="transfer_population_amount_delta" or payload.get("start_year")!=2026 or payload.get("years")!=5:
        raise ValueError("phased pension period/route mismatch")
    mode=payload.get("pension_trend_model")
    if mode not in {"ols_2021_2024","freeze_2021_2024"} or payload.get("couple_recovery_model")!="standard_amount_proxy":
        raise ValueError("select explicit observation-based trend and recovery proxy")
    if any(not str(payload.get(k) or "").strip() for k in ("support_derivation_note","pension_trend_note","couple_recovery_note")):
        raise ValueError("phased pension assumptions need notes")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("duplicate phased pension adjustment")
    units=dict(pension_recipient_history="recipient_history",pension_standard_forecast="KRW/person/month",
        new_couple_reduction="ratio",old_couple_reduction="ratio",new_eligibility_share="ratio",old_eligibility_share="ratio")
    resolved,missing=resolve_formula_variables(tuple(units),**layers)
    for k,r in resolved.items():
        if r.unit!=units[k] or not r.source_ref:raise ValueError("phased pension unit/source mismatch")
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    h=resolved["pension_recipient_history"].value
    if not isinstance(h,(list,tuple)) or [r.get("year") for r in h]!=[2021,2022,2023,2024]:raise ValueError("need four historical years")
    for r in h:
        if any(isinstance(r.get(k),bool) or not isinstance(r.get(k),(int,float)) or not isfinite(r[k]) or r[k]<=0 for k in ("recipients","couple_both","mean_payment","standard")) or r["couple_both"]>r["recipients"] or r["mean_payment"]>r["standard"]:
            raise ValueError("invalid pension history")
    data={}
    for k,r in resolved.items():
        if k=="pension_recipient_history":continue
        vals=list(r.value) if isinstance(r.value,(list,tuple)) else [r.value]*5
        if len(vals)!=5 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0 or (r.unit=="ratio" and v>1) for v in vals):raise ValueError("invalid phased series")
        data[k]=vals
    if any(n>o for n,o in zip(data["new_couple_reduction"],data["old_couple_reduction"])) or any(n<o for n,o in zip(data["new_eligibility_share"],data["old_eligibility_share"])):
        raise ValueError("phased recovery or expansion is reversed")
    historic_pop=population_series("age65_population",2021,4)
    uptake=[r["recipients"]/(p*.7) for r,p in zip(h,historic_pop)]
    shares=[r["couple_both"]/r["recipients"] for r in h]
    retention=[r["mean_payment"]/r["standard"] for r in h]
    def trend(vals):
        mean=sum(vals)/4
        slope=sum((x-2022.5)*(v-mean) for x,v in zip(range(2021,2025),vals))/5
        return [mean+(slope*(year-2022.5) if mode=="ols_2021_2024" else 0) for year in range(2026,2031)]
    u,s,f=map(trend,(uptake,shares,retention))
    if any(not 0<=v<=1 for vs in (u,s,f) for v in vs):raise ValueError("trend outside ratio bounds, do not silently clip")
    pop=population_series("age65_population",2026,5);base=data["pension_standard_forecast"]
    newfactor=[x+share*(old-new) for x,share,old,new in zip(f,s,data["old_couple_reduction"],data["new_couple_reduction"])]
    if any(v>1 for v in newfactor):raise ValueError("recovery proxy exceeds reference amount")
    values=dict(new_recipient_count=([p*rate*t for p,rate,t in zip(pop,data["new_eligibility_share"],u)],"person"),
        existing_recipient_count=([p*rate*t for p,rate,t in zip(pop,data["old_eligibility_share"],u)],"person"),
        benefit_per_recipient=([b*r for b,r in zip(base,newfactor)],"KRW/person/month"),
        existing_benefit_per_recipient=([b*r for b,r in zip(base,f)],"KRW/person/month"))
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    ref="; ".join(dict.fromkeys(r.source_ref for r in resolved.values()))+";KOSIS2023.12"
    for k,(v,unit) in values.items():
        upper,_=resolve_formula_variables((k,),**{**layers,"calculated_estimate":calculated})
        if k not in upper:calculated[k]=dict(value=v,unit=unit,source_ref=ref,is_assumption=True)
        trace.append(dict(variable_key=k,values=v,unit=unit,applied=k not in upper,source_ref=ref))
    trace.append(dict(trend_model=mode,historical_take_up=uptake,historical_couple_share=shares,historical_payment_ratio=retention,
        projected_take_up=u,projected_couple_share=s,projected_current_payment_ratio=f,
        reduction_schedule=data["new_couple_reduction"],limitation="기준액차액회복후보.유형별NR·소득역전감액교차정보미재현"))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
