"""Explicit post-answer cost-table replay. Never an unseen-bill estimator."""
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="published_pension_cost_replay"


def published_pension_replay_rows():
    table=[dict(year=y,current=c*10**11,amended=a*10**11,printed_increment=d*10**11)
           for y,c,a,d in ((2026,331,372,41),(2027,352,404,52),(2028,375,441,65),
                         (2029,395,464,69),(2030,418,491,73))]
    return [evidence_row(evidence_key="2211669:published_cost_table:reference_replay",
        variable_key="published_pension_cost_table",value=table,unit="published_cost_table",
        source_bill_no="2211669",available_at="2025-08-11",reviewed_at="2026-10-06",
        source_ref="2211669 비용추계서25C3952 PDF5쪽표4 공표현행·개정총비용",
        agency="국회예산정책처",policy_domain="기초연금",scope="2211669 정답열람후공표금액표재생전용",
        service_function=PROFILE,variable_role="answer_reference",reuse_policy="target_only",
        support_derivation=PROFILE,replay_purpose="post_answer_reference_only",
        allowed_routes=["direct_annual_amount"],value_years=list(range(2026,2031)),
        independently_verified=False,obtained_from="reviewed_answer",
        published_current_total=187100000000000,published_amended_total=217200000000000,
        published_increment_total=30100000000000,
        limitation="공표비용표를그대로재생하는참조이며변수추계·독립성능성과아님.다른의안재사용금지.2028년표시B−A6.6과표시차액6.5는0.1조원반올림차이로분리보존")]


def prepare_published_pension_replay(payload):
    if payload.get("route_key")!="direct_annual_amount" or payload.get("replay_purpose")!="post_answer_reference_only" or payload.get("evidence_mode")!="development_review":
        raise ValueError("published pension replay is post-answer development only")
    if payload.get("start_year")!=2026 or payload.get("years")!=5 or not str(payload.get("replay_source_note") or "").strip():
        raise ValueError("published replay needs exact period and source note")
    if any(k in (payload.get(l) or {}) for l in ("explicit_inputs","actual_inputs","official_inputs","calculated_inputs")
           for k in ("growth_rate","growth_rates_by_year","first_year_fraction","annual_amount")):
        raise ValueError("do not adjust or overwrite a published replay")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    r,missing=resolve_formula_variables(("published_pension_cost_table",),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing)}
    row=r["published_pension_cost_table"]
    if row.unit!="published_cost_table" or not row.source_ref or not isinstance(row.value,(list,tuple)) or len(row.value)!=5:
        raise ValueError("invalid published table")
    table=row.value
    if [v.get("year") for v in table]!=list(range(2026,2031)):raise ValueError("replay year mismatch")
    for v in table:
        if any(isinstance(v.get(k),bool) or not isinstance(v.get(k),int) or v[k]<0 for k in ("current","amended","printed_increment")):
            raise ValueError("invalid replay amount")
    values=[v["amended"]-v["current"] for v in table]
    return {**payload,"calculated_inputs":{"annual_amount":dict(value=values,unit="KRW/year",
        source_ref=row.source_ref,is_assumption=False)},"support_missing_operands":[],
        "support_derivation_trace":[dict(replay_only=True,expression="공표개정총비용−공표현행총비용",
            values=values,printed_increment_values=[v["printed_increment"] for v in table],source_ref=row.source_ref,
            limitation="같은정답의공표총비용차감재생.이결과가맞아도유형별감액변수가검증된것은아님")]}
