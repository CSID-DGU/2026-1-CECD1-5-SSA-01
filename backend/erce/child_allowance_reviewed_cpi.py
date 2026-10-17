"""Opt-in reviewed CPI scenario; never a global hard-coded 2% increase."""
from math import isfinite, prod
from backend.erce.child_allowance_birth_order_evidence import birth_order_rows
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE="child_allowance_reviewed_cpi"


def reviewed_child_cpi_rows():
    rate=next(r for r in birth_order_rows() if r["variable_key"]=="child_execution_factor")
    # Same observed take-up assumption, not a newly observed rate or target-derived operand.
    alias={**rate,"evidence_key":rate["evidence_key"]+":reviewed_cpi","alias_of":rate["evidence_key"],
        "support_derivation":PROFILE,"service_function":PROFILE}
    alias.pop("birth_order_population_basis",None)
    cpi=evidence_row(evidence_key="2212685:child_cpi:2026-2030:202507",
        variable_key="reviewed_cpi_rates",value=[.02]*5,unit="ratio/year",
        source_bill_no="2212685",available_at="2025-09-22",reviewed_at="2026-10-06",
        source_ref="2212685 비용추계서25C4808 PDF4쪽 각주4; 국회예산정책처2025.7전망2026~2030 CPI 각2%",
        agency="국회예산정책처",policy_domain="아동수당",scope="2025.7전망2026~2030전국CPI",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2212685/cost_estimate.pdf",
        service_function=PROFILE,support_derivation=PROFILE,variable_role="dated_forecast",
        value_years=list(range(2026,2031)),allowed_routes=["transfer_population_amount_delta"],
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        forecast_vintage="2025-07",limitation="의안 정답이 인용한 당시전망. 원전망보고서 독립검증미완료; 다른기간 최신전망으로전용금지")
    return [alias,cpi]


def prepare_reviewed_child_cpi(payload):
    if payload.get("route_key")!="transfer_population_amount_delta" or payload.get("cpi_application_confirmed") is not True:
        raise ValueError("reviewed CPI routing requires confirmed applicability")
    if not all(str(payload.get(k) or "").strip() for k in
        ("cpi_application_note","population_proxy_note","support_derivation_note","estimation_start_note")):
        raise ValueError("reviewed CPI needs sourced scenario, population and timing notes")
    start=payload.get("start_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"]}
    if payload.get("cpi_first_year_included") is not True or payload.get("existing_benefit_price_policy")!="freeze":
        raise ValueError("CPI base/current-price policies must be confirmed")
    if payload.get("benefit_index_base_year")!=start-1:
        raise ValueError("CPI forecast must follow base year")
    if payload.get("population_geography")!="전국" or payload.get("statistical_sex")!="total":
        raise ValueError("reviewed child CPI requires national total population")
    units={"under13_population":"person","under8_population":"person","child_execution_factor":"ratio",
        "reviewed_cpi_rates":"ratio/year","base_monthly_benefit":"KRW/person/month",
        "existing_benefit_per_recipient":"KRW/person/month","payments_per_year":"month/year"}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    years=payload.get("years",5);v={}
    for key,row in r.items():
        seq=list(row.value) if isinstance(row.value,(list,tuple)) else [row.value]*years
        if row.unit!=units[key] or not row.source_ref or len(seq)!=years or any(
            isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x)
            or (x<=-1 if key=="reviewed_cpi_rates" else x<0)
            or (key=="child_execution_factor" and x>1) for x in seq):
            raise ValueError("reviewed CPI operand/unit/period mismatch")
        v[key]=seq
    if any(o>n for o,n in zip(v["under8_population"],v["under13_population"])):
        raise ValueError("invalid child cohort inclusion")
    if any(key in (payload.get(layer) or {}) for layer in ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs")
        for key in ("benefit_per_recipient","growth_rate","growth_rates_by_year","participation_rate")):
        raise ValueError("reviewed CPI forbids already-indexed amounts or duplicate growth")
    prices=[v["base_monthly_benefit"][i]*prod(1+x for x in v["reviewed_cpi_rates"][:i+1]) for i in range(years)]
    inputs={"new_recipient_count":([n*f for n,f in zip(v["under13_population"],v["child_execution_factor"])],"person"),
        "existing_recipient_count":([n*f for n,f in zip(v["under8_population"],v["child_execution_factor"])],"person"),
        "benefit_per_recipient":(prices,"KRW/person/month")}
    source="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    calculated=dict(payload.get("calculated_inputs") or {})
    for k,(values,unit) in inputs.items():
        calculated[k]=dict(value=values,unit=unit,source_ref=source,is_assumption=True)
    trace=[dict(year=start+i,cpi=v["reviewed_cpi_rates"][i],indexed_monthly_benefit=p,
        base_monthly_benefit=v["base_monthly_benefit"][i],new_population=v["under13_population"][i],
        existing_population=v["under8_population"][i],execution_factor=v["child_execution_factor"][i],
        existing_monthly_benefit=v["existing_benefit_per_recipient"][i],
        note="물가반영확인 후 신규급여만 누적반영; 현행급여동결") for i,p in enumerate(prices)]
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
