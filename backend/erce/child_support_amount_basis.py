from math import isfinite
from backend.erce.child_support_advance_evidence import ADVANCE,child_support_rows,prepare_child_support
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

STANDARD="child_support_income_age_standard"


def amount_basis_rows():
    rows=[{**r,"evidence_key":r["evidence_key"]+":standard_table","alias_of":r["evidence_key"],
        "support_derivation":STANDARD,"child_support_model":STANDARD,"service_function":STANDARD}
        for r in child_support_rows() if r["support_derivation"]==ADVANCE and r["variable_key"]!="advance_monthly_amount"]
    rows.append(evidence_row(evidence_key="2203287:advance_monthly_amount:policy_proxy",
        variable_key="advance_monthly_amount",value=200000,unit="KRW/person/month",
        source_bill_no="2203287",available_at="2024-08-28",reviewed_at="2026-10-09",
        source_ref="2203287 비용추계서24C3127 PDF5쪽;정부2024선지급추진계획월20만원준용",
        agency="여성가족부",policy_domain="양육비선지급",scope="표준양육비대신사용한정액정책참고시나리오",
        service_function=ADVANCE,support_derivation=ADVANCE,child_support_model=ADVANCE,
        advance_amount_basis="policy_fixed_proxy",statutory_standard_table_required=True,
        variable_role="approved_proxy_candidate",allowed_routes=["direct_annual_amount"],
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="원문표준양육비로계산된확정액아님.가정승인과원문기준차이메모없이자동사용금지"))
    return rows


def prepare_standard_amount(payload):
    if payload.get("route_key")!="direct_annual_amount" or payload.get("advance_amount_basis")!="standard_income_age_table":
        raise ValueError("income-age standard basis/route mismatch")
    if not str(payload.get("standard_table_scope_note") or "").strip():
        raise ValueError("standard support table needs source/applicability review")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any("advance_monthly_amount" in (layer or {}) for layer in layers.values()):
        raise ValueError("standard-table mode must derive the amount, not use a flat override")
    r,missing=resolve_formula_variables(("standard_support_cells","standard_cell_weights"),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    if r["standard_support_cells"].unit!="income_age_support_cells" or r["standard_cell_weights"].unit!="cell_to_ratio" or not all(v.source_ref for v in r.values()):
        raise ValueError("standard table unit/source mismatch")
    cells=r["standard_support_cells"].value;weights=r["standard_cell_weights"].value
    if not isinstance(cells,dict) or not cells or not isinstance(weights,dict) or set(cells)!=set(weights):
        raise ValueError("standard support cohorts/weights mismatch")
    def number(x):return not isinstance(x,bool) and isinstance(x,(int,float)) and isfinite(x)
    if any(not number(w) or not 0<=w<=1 for w in weights.values()) or abs(sum(weights.values())-1)>1e-9:
        raise ValueError("standard cohort weights must sum to one; no silent normalization")
    details=[];mean=0
    for key,cell in cells.items():
        if not isinstance(cell,dict) or not all(str(cell.get(k) or "").strip() for k in ("age_band","income_band")):
            raise ValueError("standard table age/income bands required")
        b=cell.get("base_monthly_support");a=cell.get("adjustment_won");parent=cell.get("parents_combined_income");debtor=cell.get("debtor_income")
        if not all(number(v) for v in (b,a,parent,debtor)) or b<0 or b+a<0 or parent<=0 or not 0<=debtor<=parent:
            raise ValueError("standard amount/adjustments/income share require valid data")
        amount=(b+a)*debtor/parent;mean+=amount*weights[key]
        details.append(dict(cell=key,age_band=cell["age_band"],income_band=cell["income_band"],
            adjusted_support=b+a,debtor_income_share=debtor/parent,monthly_amount=amount,weight=weights[key]))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["advance_monthly_amount"]=dict(value=mean,unit="KRW/person/month",is_assumption=True,
        source_ref="; ".join(v.source_ref for v in r.values()))
    inner={**payload,"support_derivation":ADVANCE,"child_support_model":ADVANCE,
        "statutory_standard_table_required":False,"calculated_inputs":calculated}
    result=prepare_child_support(inner)
    return {**result,"support_derivation":STANDARD,"child_support_model":STANDARD,
        "statutory_standard_table_required":True,
        "support_derivation_trace":[dict(amount_basis="standard_income_age_table",weighted_monthly_amount=mean,
            cell_details=details,source_ref=calculated["advance_monthly_amount"]["source_ref"]),
            *result.get("support_derivation_trace",[])]}
