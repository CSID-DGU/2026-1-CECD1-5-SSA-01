"""Partial reinforcement: known conditional shares, missing type totals stay missing."""
import dataclasses
import json
from backend.erce.low_income_couple_pension import PROFILE,GROUPS,low_income_couple_rows
from backend.erce.variable_evidence_store import evidence_payload_from_db
from backend.erce.support_method_operands import prepare_support_operands
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs
from backend.erce.web_bridge import calculate_erce_web_item


def payload(group):
    rows=[r for r in low_income_couple_rows() if r.get("pension_group") in (None,group)]
    return dict(bill_no="2213794",route_key="transfer_recipient_delta",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2027,years=5,support_derivation=PROFILE,
        pension_group=group,low_income_scope="overall_elderly_bottom40",pension_standard_vintage="2025_09_reviewed_forecast",
        support_derivation_note="소득하위40%부부2인만.2027~2029감액15%·2030이후10%",
        pension_denominator_note="각NR/급여유형의전체인원에유형내저소득비율을곱함.전체부부인원으로대체하지않음",
        pension_increment_factor_note="NR연계·저소득경계감액후실제증액/기준액증액 비율.근거미확보로1자동입력안함",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"동일기간·소득조건·유형의사후자료 연결" for r in rows},
        explicit_inputs=dict(old_couple_reduction=dict(value=.2,unit="ratio",source_ref="현행제8조20%"),
            new_couple_reduction=dict(value=[.15,.15,.15,.1,.1],unit="ratio",source_ref="원문부칙2027~2029년15%이후10%"),
            payments_per_year=dict(value=12,unit="month/year",source_ref="원문2027-01-01시행 및매월급여")))


def run_regression():
    runs=[]
    for group in GROUPS:
        p=payload(group);h=prepare_support_operands(evidence_payload_from_db(p))
        r,missing=resolve_formula_variables(("recipient_count","benefit_per_recipient","existing_benefit_per_recipient"),
            target_explicit=h.get("explicit_inputs"),official_standard=h.get("official_inputs"),
            calculated_estimate=h.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(h))
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_LOW_COUPLE","evidence_mode":"holdout"})
        runs.append(dict(group=group,payload=p,resolved={k:dataclasses.asdict(v) for k,v in r.items()},
            missing_variables=list(missing),missing_operands=h["support_missing_operands"],synthetic_web_status=web["status"]))
    return dict(bill_no="2213794",post_answer_regression=True,independent_evaluation=False,
        runs=runs,reference_variable_slots_filled=10,reference_variable_slot_count=15,total_thousand=None,
        gold_total_thousand=2408900000,known_conditional_share_count=5,
        unresolved="각유형전체예측인원·실제감액후회복계수미확보.참조급여슬롯2개는기준금액이고실제소득조건에대한순증은미산출")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
