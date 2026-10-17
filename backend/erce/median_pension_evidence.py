"""Historical median-income pension groups; replay and legal readings are separate."""
from math import isfinite
from backend.erce.common_population_evidence import population_series
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="median_income_pension_groups"


def median_pension_rows():
    groups=[
        dict(key="single_low",counts=[2880696,3009454,3045990,3179249,3235552],payments=[512102,527158,548349,583444,623368],couple=False,high=False),
        dict(key="single_high",counts=[147495,160655,220789,225976,265272],payments=[186086,186605,198854,208283,230079],incomes=[1380992,1416641,1478336,1569651,1684603],couple=False,high=True),
        dict(key="couple_low",counts=[1666297,1777615,1700695,1792170,1792538],payments=[409682,421726,438679,466755,498694],couple=True,high=False),
        dict(key="couple_high",counts=[398398,418097,490254,532404,569099],payments=[112257,113992,128772,134045,146375],incomes=[1409583,1449460,1517924,1612102,1725573],couple=True,high=True),
    ]
    rows=[]
    for key,value,unit in (
        ("median_pension_history_groups",groups,"pension_history_groups"),
        ("median_income_history",[1707008,1757194,1827831,1944812,2077892],"KRW/person/month"),
        ("published_current_pension_cost",[26900000000000,29100000000000,31000000000000,33000000000000,34800000000000],"KRW/year"),
    ):
        rows.append(evidence_row(evidence_key=f"2204828:{key}:reviewed",variable_key=key,value=value,unit=unit,
            source_bill_no="2204828",available_at="2026-10-06",reviewed_at="2026-10-06",
            source_ref="2204828 폴더 비용추계서24C1884 PDF4~7쪽 표2~4·9",
            agency="국회예산정책처·보건복지부",policy_domain="기초연금",scope="전국2025~2029중위소득연동변경·국비지방비합산",
            service_function=PROFILE,variable_role="historical_model_reference",support_derivation=PROFILE,
            allowed_routes=["transfer_population_amount_delta"],requires_applicability_note=True,
            pension_baseline_version="2024_03_reviewed_projection",
            source_reply_date="2024-08-08",source_bill_version_match=False,
            independently_verified=False,obtained_from="reviewed_answer",
            **({"value_years":list(range(2025,2030))} if key=="published_current_pension_cost" else {"observation_years":list(range(2019,2024)),"valid_from_year":2025,"valid_to_year":2029}),
            limitation="표4지급액식은감액액과혼동가능·2023낮은집단급여는30%인데본문32%.재생과법문해석분리.현행비용은해당경제전망의반올림된기준선예측이지최신실제예산아님.회답일이발의일보다빠른원문버전미일치참조"))
    return rows


def prepare_median_pension(payload):
    if payload.get("route_key")!="transfer_population_amount_delta" or payload.get("start_year")!=2025 or payload.get("years")!=5:
        raise ValueError("median pension route or period mismatch")
    mode=payload.get("median_pension_reading")
    if mode not in {"answer_table_replay","income_gap_32pct_review"}:
        raise ValueError("select table replay or reviewed statutory income-gap scenario")
    if mode=="income_gap_32pct_review" and (payload.get("median_income_unit")!="household_income_as_reported" or not str(payload.get("median_pension_gap_note") or "").strip()):
        raise ValueError("income-gap scenario requires household/per-person interpretation review")
    if payload.get("pension_baseline_version")!="2024_03_reviewed_projection" or any(not str(payload.get(k) or "").strip() for k in (
        "support_derivation_note","median_pension_conflict_note","published_baseline_note")):
        raise ValueError("median pension needs scope, conflicting-source and published-baseline notes")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (l or {}) for l in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("median pension already includes all group/count adjustments")
    units=dict(median_pension_history_groups="pension_history_groups",median_income_history="KRW/person/month",published_current_pension_cost="KRW/year")
    resolved,missing=resolve_formula_variables(tuple(units),**layers)
    for k,r in resolved.items():
        if r.unit!=units[k] or not r.source_ref:raise ValueError("median pension needs sourced operands")
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    groups=resolved["median_pension_history_groups"].value
    if not isinstance(groups,(list,tuple)) or {g.get("key") for g in groups}!={"single_low","single_high","couple_low","couple_high"} or len(groups)!=4:
        raise ValueError("need four disjoint median pension groups")
    def valid_series(x):
        return isinstance(x,(list,tuple)) and len(x)==5 and all(not isinstance(v,bool) and isinstance(v,(int,float)) and isfinite(v) and v>0 for v in x)
    median=resolved["median_income_history"].value;oldcost=resolved["published_current_pension_cost"].value
    if not valid_series(median) or not valid_series(oldcost):raise ValueError("invalid median or baseline series")
    def cagr(x):return (x[-1]/x[0])**.25-1
    rate=cagr(median);counts=[0.0]*5;costs=[0.0]*5;trace=[]
    for g in groups:
        if not valid_series(g.get("counts")) or not valid_series(g.get("payments")) or not isinstance(g.get("couple"),bool) or not isinstance(g.get("high"),bool):
            raise ValueError("invalid historical pension group")
        if g["high"] and not valid_series(g.get("incomes")):raise ValueError("high group needs income history")
        n_rate=cagr(g["counts"]);p_rate=cagr(g["payments"]) if g["high"] else rate
        ns=[];ps=[]
        for i in range(5):
            t=i+2;n=g["counts"][-1]*(1+n_rate)**t
            if mode=="answer_table_replay":p=g["payments"][-1]*(1+p_rate)**t
            else:
                m=median[-1]*(1+rate)**t
                p=m*.32*(.8 if g["couple"] else 1)
                if g["high"]:
                    income=g["incomes"][-1]*(1+cagr(g["incomes"]))**t
                    p=min(p,max(0,m-income)/(2 if g["couple"] else 1))
            ns.append(n);ps.append(p);counts[i]+=n;costs[i]+=n*p*12
        trace.append(dict(group=g["key"],count_growth=n_rate,payment_growth=p_rate,
            recipients=ns,monthly_payment=ps,reading=mode,
            limitation="표재생은역사적지급표값투영;법문후보는집단평균가구소득에min적용·부부2명균등배분 가정으로개인별min평균과다를수있음"))
    oldcounts=[p*.7*.991 for p in population_series("age65_population",2025,5)]
    values=dict(new_recipient_count=(counts,"person"),existing_recipient_count=(oldcounts,"person"),
        benefit_per_recipient=([c/n/12 for c,n in zip(costs,counts)],"KRW/person/month"),
        existing_benefit_per_recipient=([c/n/12 for c,n in zip(oldcost,oldcounts)],"KRW/person/month"))
    calculated=dict(payload.get("calculated_inputs") or {})
    ref="; ".join(dict.fromkeys(r.source_ref for r in resolved.values()))+";KOSIS2023.12공식65세이상전망·수급률99.1%"
    for k,(v,unit) in values.items():
        upper,_=resolve_formula_variables((k,),**{**layers,"calculated_estimate":calculated})
        if k not in upper:calculated[k]=dict(value=v,unit=unit,source_ref=ref,is_assumption=True)
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
