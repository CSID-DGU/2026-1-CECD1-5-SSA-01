import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def research_payload(kind):
    route="research_survey" if kind=="survey" else "research_plan"
    unit_key="survey_unit_cost" if kind=="survey" else "plan_unit_cost"
    keys=[f"2212766:{kind}:{unit_key}:reviewed",f"2212766:{kind}:recurrence:reviewed"]
    method="2212766:research_"+kind
    notes=dict(research_contract_scope_note="조사현장수행비750백만원아닌연구용역분만;계획은신규서비스정책연구",
        recurrence_phase_note="실태3년2027/2030,계획5년2027.지방계획은별도미검증",
        price_freeze_note="과거계약9000/4000만원준용동결,최신고시단가아님")
    return dict(bill_no="2212766",cutoff_date="2026-10-08",evidence_mode="development_review",
        route_key=route,start_year=2027,years=5,payer="government",agency="보건복지부",policy_domain="장애인활동지원",
        research_service_function="activity_support_"+kind,research_cost_scope="research_contract_only",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"계약과업·포함범위·법정주기와추계시점확인후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"동일과업에대한유사연구계약범위검토"},method_confirmations={method:notes})


def pay_review():
    return dict(bill_no="2212766",cutoff_date="2026-10-08",evidence_mode="development_review",
        decision_evidence_key="2212766:pay_standard_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(pay_standard_confirmed=False,benefit_reflection_method_confirmed=False),
        decision_confirmations=dict(pay_standard_scope_review="정답PDF3의당시적정인건비수준미확정확인",
            benefit_reflection_review="당시급여비반영방식미확정.현재후속고시부재를전수확인한주장아님"))


def run_regression():
    parts=[];web_status=[]
    for kind in ("survey","plan"):
        p=research_payload(kind);r=estimate_routed_item(p)
        w=calculate_erce_web_item({**p,"bill_no":"SIMILAR_ACTIVITY_SUPPORT_RESEARCH","evidence_mode":"holdout"})
        parts.append(dict(kind=kind,payload=p,result=dataclasses.asdict(r)));web_status.append(w["status"])
    annual=[sum(p["result"]["annual_amounts_thousand"][i] for p in parts) for i in range(5)]
    total=sum(annual)
    decision=validate_non_estimation_review(pay_review())
    return dict(bill_no="2212766",post_answer_regression=True,independent_evaluation=False,
        parts=parts,reusable_web_status=web_status,annual_thousand=annual,partial_total_thousand=total,
        gold_partial_total_thousand=220000,error_percent=abs(total-220000)/220000*100,
        pay_non_estimation=decision,pay_review_payload=pay_review(),whole_bill_total=None,
        other_scope_review=["지방연간시행계획","분리청구/전산처리","시정명령행정비"],
        limitation="일부연구용역추계와적정인건비3호미추계재현.현장조사전체비/전체사업완료아님.사후회귀")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
