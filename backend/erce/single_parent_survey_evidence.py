"""Single-parent legal child cohort from households, not income-support recipients."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.child_allowance_birth_order_evidence import birth_order_rows
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE="single_parent_survey_children"
SCOPE="under18_children_residing_with_single_parent"


def single_parent_rows():
    rows=[]
    for key,value,unit in (("single_parent_households",322000,"household"),
                           ("children_per_household",1.5,"person/household")):
        rows.append(evidence_row(evidence_key=f"2212823:{key}:survey2024",
            variable_key=key,value=value,unit=unit,source_bill_no="2212823",available_at="2025-09-22",
            reviewed_at="2026-10-06",source_ref="2212823 비용추계서25C4933 PDF4쪽;2024한부모가족실태조사 인용",
            agency="여성가족부",policy_domain="한부모가족아동",scope="18세미만자녀와동거하는한부모가구",
            service_function=PROFILE,support_derivation=PROFILE,variable_role="survey_population_operand",
            single_parent_population_scope=SCOPE,single_parent_projection="freeze_2024_survey",
            observation_year=2024,allowed_routes=["transfer_recipient"],requires_applicability_note=True,
            independently_verified=False,obtained_from="reviewed_answer",
            limitation="322천가구×평균1.5명의대리추정.소득기준한부모복지급여수급자수와다름;원실태조사독립검증미완료.미래동결별도가정"))
    original=next(r for r in birth_order_rows() if r["variable_key"]=="child_execution_factor")
    alias={**original,"evidence_key":original["evidence_key"]+":single_parent","alias_of":original["evidence_key"],
        "allowed_routes":["transfer_recipient"],"support_derivation":PROFILE,"service_function":PROFILE}
    alias.pop("birth_order_population_basis",None)
    rows.append(alias)
    return rows


def prepare_single_parent(payload):
    if payload.get("route_key")!="transfer_recipient" or payload.get("single_parent_population_scope")!=SCOPE:
        raise ValueError("single-parent legal cohort/route mismatch")
    if payload.get("single_parent_projection")!="freeze_2024_survey" or payload.get("single_parent_support_additive") is not True:
        raise ValueError("single-parent projection and additive scope must be confirmed")
    if not all(str(payload.get(k) or "").strip() for k in ("support_derivation_note","additive_support_note","survey_scope_note")):
        raise ValueError("single-parent survey/applicability notes required")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("single-parent duplicate execution/growth forbidden")
    upper,_=resolve_formula_variables(("recipient_count",),**layers)
    if upper:return payload
    units={"single_parent_households":"household","children_per_household":"person/household","child_execution_factor":"ratio"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        value=row.value
        if row.unit!=units[k] or not row.source_ref or isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:
            raise ValueError("single-parent unit/source/value mismatch")
    v={k:row.value for k,row in r.items()}
    if v["child_execution_factor"]>1:raise ValueError("invalid child execution factor")
    gross=v["single_parent_households"]*v["children_per_household"]
    recipient=gross*v["child_execution_factor"]
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["recipient_count"]=dict(value=recipient,unit="person",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
        "support_derivation_trace":[dict(households=v["single_parent_households"],children_per_household=v["children_per_household"],
            gross_children=gross,execution_factor=v["child_execution_factor"],effective_recipients=recipient,
            expression="18세미만동거자녀한부모가구×평균자녀수×집행계수",projection="freeze_2024_survey")]}
