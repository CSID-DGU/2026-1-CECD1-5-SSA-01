"""Payment/household-specific trends, with explicit unresolved reduced-group split."""
from math import isfinite
from backend.erce.phased_couple_pension import phased_couple_rows,prepare_phased_couple
from backend.erce.common_population_evidence import population_series
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="phased_couple_pension_types"
KEYS=("full_single_or_couple_one","full_couple_two","reduced_single_or_couple_one","reduced_couple_two")


def phased_pension_type_rows():
    rows=[]
    for source in phased_couple_rows():
        r={**source,"evidence_key":source["evidence_key"]+":types",
            "alias_of":source["evidence_key"],"support_derivation":PROFILE,
            "pension_distribution_basis":"payment_household_types_2021_2024"}
        if source["variable_key"]=="pension_recipient_history":
            r["value"]=[{**h,"full_single_or_couple_one":s,"full_couple_two":c}
                for h,s,c in zip(source["value"],[3134850,3232240,3316185,3368571],[2242918,2342419,2444400,2484187])]
            r["source_ref"] += ";PDF13·40~42쪽전액·감액별수급자실적"
            r["limitation"] += ";감액수급자중NR연계와소득역전원인분리는미확인.감액집단내가구별급여정보가없어공통감액전지급비율준용을별도가정해야함"
        rows.append(r)
    return rows


def prepare_phased_pension_types(payload):
    if payload.get("pension_distribution_basis")!="payment_household_types_2021_2024" or any(
            not str(payload.get(k) or "").strip() for k in ("pension_type_trend_note","reduced_group_split_note")):
        raise ValueError("type-specific pension needs distribution and unresolved joint-data notes")
    model=payload.get("reduced_couple_recovery")
    if model not in {"shared_unreduced_proxy","standard_amount_ablation"}:
        raise ValueError("select reduced-couple recovery assumption explicitly")
    prepared=prepare_phased_couple(payload)
    if prepared.get("support_missing_operands"):return prepared
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    resolved,_=resolve_formula_variables(("pension_recipient_history","pension_standard_forecast","old_couple_reduction","new_couple_reduction","old_eligibility_share","new_eligibility_share"),**layers)
    history=resolved["pension_recipient_history"].value
    records=[];retentions=[]
    for h in history:
        for key in KEYS[:2]:
            v=h.get(key)
            if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError("missing or invalid observed payment type count")
        counts=[h[KEYS[0]],h[KEYS[1]],h["recipients"]-h[KEYS[0]]-h["couple_both"],h["couple_both"]-h[KEYS[1]]]
        if min(counts)<0 or sum(counts)!=h["recipients"]:raise ValueError("payment types overlap or do not reconcile")
        # A common *before-couple-reduction* factor for reduced groups is an
        # explicit identification assumption, not two observed group prices.
        remaining=h["recipients"]*h["mean_payment"]-counts[0]*h["standard"]-counts[1]*h["standard"]*.8
        denominator=h["standard"]*(counts[2]+counts[3]*.8)
        if denominator<=0:raise ValueError("no reduced population to identify common proxy")
        factor=remaining/denominator
        if not isfinite(factor) or not 0<=factor<=1:raise ValueError("historical payment margin inconsistent")
        records.append(counts);retentions.append(factor)
    mode=payload["pension_trend_model"]
    def trend(values):
        mean=sum(values)/4;slope=sum((y-2022.5)*(v-mean) for y,v in zip(range(2021,2025),values))/5
        result=[mean+(slope*(y-2022.5) if mode=="ols_2021_2024" else 0) for y in range(2026,2031)]
        if any(not 0<=v<=1 for v in result):raise ValueError("payment type trend outside bounds")
        return result
    shares=[trend([counts[j]/h["recipients"] for counts,h in zip(records,history)]) for j in range(4)]
    if any(abs(sum(s[i] for s in shares)-1)>1e-9 for i in range(5)):raise ValueError("type shares must sum to one without normalization")
    factor=trend(retentions);base=resolved["pension_standard_forecast"].value
    def series(key):
        raw=resolved[key].value;return list(raw) if isinstance(raw,(list,tuple)) else [raw]*5
    oldred=series("old_couple_reduction");newred=series("new_couple_reduction")
    if any(v!=.2 for v in oldred):raise ValueError("historical type dataset assumes 20% old couple reduction")
    uptake=prepared["support_derivation_trace"][-1]["projected_take_up"]
    pop=population_series("age65_population",2026,5);oldshare=series("old_eligibility_share");newshare=series("new_eligibility_share")
    oldtotal=[n*r*u for n,r,u in zip(pop,oldshare,uptake)];newtotal=[n*r*u for n,r,u in zip(pop,newshare,uptake)]
    if min(oldtotal+newtotal)<=0:raise ValueError("type average requires positive populations")
    oldcost=[0.0]*5;newcost=[0.0]*5;expanded_only=[0.0]*5;trace=[]
    for j,key in enumerate(KEYS):
        oldn=[n*s for n,s in zip(oldtotal,shares[j])];newn=[n*s for n,s in zip(newtotal,shares[j])]
        oldp=[];newp=[]
        for i,b in enumerate(base):
            retention=factor[i] if j in (2,3) else 1
            a=b*retention*(1-oldred[i] if j in (1,3) else 1)
            if j==3 and model=="standard_amount_ablation":z=a+b*(oldred[i]-newred[i])
            else:z=b*retention*(1-newred[i] if j in (1,3) else 1)
            if z>b:raise ValueError("type proxy exceeds standard")
            oldp.append(a);newp.append(z)
            oldcost[i]+=oldn[i]*a*12;newcost[i]+=newn[i]*z*12;expanded_only[i]+=newn[i]*a*12
        trace.append(dict(type_key=key,historical_counts=[r[j] for r in records],
            forecast_share=shares[j],existing_recipients=oldn,new_recipients=newn,
            existing_monthly=oldp,new_monthly=newp,
            eligibility_expansion_won=[(n-o)*p*12 for n,o,p in zip(newn,oldn,oldp)],
            reduction_recovery_won=[n*(p-o)*12 for n,p,o in zip(newn,newp,oldp)],
            direct_group_count_verified=True,group_price_is_proxy=j in (2,3)))
    values=dict(new_recipient_count=(newtotal,"person"),existing_recipient_count=(oldtotal,"person"),
        benefit_per_recipient=([c/n/12 for c,n in zip(newcost,newtotal)],"KRW/person/month"),
        existing_benefit_per_recipient=([c/n/12 for c,n in zip(oldcost,oldtotal)],"KRW/person/month"))
    calculated=dict(payload.get("calculated_inputs") or {})
    refs="; ".join(dict.fromkeys(r.source_ref for r in resolved.values()))+";유형별추세·공통감액전비율가정"
    for k,(v,unit) in values.items():
        upper,_=resolve_formula_variables((k,),**layers)
        if k not in upper:calculated[k]=dict(value=v,unit=unit,source_ref=refs,is_assumption=True)
    trace.append(dict(historical_shared_unreduced_factor=retentions,projected_shared_unreduced_factor=factor,
        eligibility_expansion_won=[n-o for n,o in zip(expanded_only,oldcost)],
        reduction_recovery_won=[n-o for n,o in zip(newcost,expanded_only)],
        total_increment_won=[n-o for n,o in zip(newcost,oldcost)],
        limitation="유형별가격은관측된전국총지급액에서조건부공통감액전비율을도출.정답총액역산아님.NR연계·소득역전원인분리는여전히미확인"))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
