"""Observed cash-payment utilization, not service length, drives the extension."""
from math import isfinite
from backend.erce.jobseeker_livelihood_evidence import jobseeker_rows,prepare_jobseeker
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="jobseeker_cash_duration_extension"


def duration_rows():
    return [{**r,"evidence_key":r["evidence_key"]+":cash_duration","alias_of":r["evidence_key"],
        "allowed_routes":["transfer_recipient"],"support_derivation":PROFILE,"service_function":PROFILE}
        for r in jobseeker_rows() if r["source_bill_no"]=="2207706"]


def prepare_jobseeker_duration(payload):
    if payload.get("route_key")!="transfer_recipient" or payload.get("payment_behavior_rule")!="proportional_existing_payment_utilization":
        raise ValueError("cash extension route/behavior mismatch")
    if not all(str(payload.get(k) or "").strip() for k in ("payment_period_projection_note","cash_component_separation_note")):
        raise ValueError("cash extension needs behavior and non-duplication confirmation")
    if any("payments_per_year" in (payload.get(layer) or {}) for layer in
           ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs")):
        raise ValueError("cash extension uses additional months, not a second total payment period")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    units={"old_statutory_months":"month","new_statutory_months":"month","average_payment_months":"month/year"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    v={}
    for k,row in r.items():
        x=row.value
        if row.unit!=units[k] or not row.source_ref or isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0:
            raise ValueError("cash extension month operand mismatch")
        v[k]=x
    old,new,actual=(v[k] for k in units)
    if old<=0 or new<=old or actual>old:
        raise ValueError("cash extension needs increasing cap and valid observed months")
    additional=actual/old*(new-old)
    confirmed,_=resolve_formula_variables(("additional_payment_months",),**layers)
    if confirmed:
        row=confirmed["additional_payment_months"];x=row.value
        if row.unit!="month/year" or not row.source_ref or isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or not 0<=x<=new-old:
            raise ValueError("invalid confirmed additional cash months")
        additional=x
    base=prepare_jobseeker({**payload,"route_key":"transfer_recipient_delta"})
    if base.get("support_missing_operands"):return {**base,"route_key":"transfer_recipient"}
    calculated=dict(base.get("calculated_inputs") or {})
    calculated["payments_per_year"]=dict(value=additional,unit="month/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values()))+
            ("; "+confirmed["additional_payment_months"].source_ref if confirmed else ""))
    trace=list(base.get("support_derivation_trace") or [])
    trace.append(dict(variable_key="payments_per_year",old_cap=old,new_cap=new,observed_payment_months=actual,
        utilization=actual/old,extra_months=additional,total_implied_months=actual+additional,
        confirmed_additional_override=bool(confirmed),
        expression="실제평균지급개월/기존법정상한×법정기간증가분",
        note="서비스이용8.3개월·무조건12개월수령으로대체하지않음.기존기간단가인상분은별도항목"))
    return {**base,"route_key":"transfer_recipient","calculated_inputs":calculated,"support_derivation_trace":trace}
