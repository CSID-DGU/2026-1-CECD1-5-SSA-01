import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.central_social_committee_evidence import PROFILE


def committee_payload(mode="face_to_face"):
    keys=["2215239:central_committee:annual_meetings",f"2215239:central_committee:meeting_price:{mode}"]
    method="2215239:central_social_committee"
    notes=dict(committee_scale_note="법정16~26중최소16명시나리오.무급차관위원장1명·5유형각3명·공무원1유형제외,유급12명",
        meeting_frequency_note="분기별1회연4회선례가정확인,법정고정횟수아님",
        committee_payment_note="대면20만원·서면10만원사회보장위원회사례.사전자료준비포함,공식일당상한과구분")
    return dict(bill_no="2215239",evidence_mode="development_review",cutoff_date="2026-10-08",
        route_key="committee_components",support_derivation=PROFILE,payer="government",start_year=2027,years=5,
        committee_role_profile="central_social_policy_deliberation",meeting_mode=mode,exclude_duty_public_officials=True,
        support_derivation_note="정답확인후중앙정책위원회운영과법안구성조건분리",**notes,
        explicit_inputs={k:dict(value=v,unit=u,source_ref="원문제4조의3구성규칙과최소정원참고시나리오")
            for k,v,u in (("committee_total_members",16,"person"),("unpaid_chair_count",1,"person"),
                ("equal_member_categories",5,"category"),("paid_member_categories",4,"category"))},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"동일중앙심의역할·빈도·회의형태검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"지역실무위원회아닌중앙정책본회의"},
        method_confirmations={method:notes})


def plan_payload():
    keys=["2215239:governance_plan:plan_unit_cost","2215239:governance_plan:recurrence_interval_years"]
    method="2215239:governance_plan_research"
    return dict(bill_no="2215239",evidence_mode="development_review",cutoff_date="2026-10-08",
        route_key="research_plan",payer="government",agency="보건복지부",policy_domain="장애인활동지원",
        start_year=2027,years=5,research_service_function="activity_support_governance_plan",research_cost_scope="research_contract_only",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"2022당사자관계·고도화연구과업선택.2018신규서비스개발과구분" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"관계기반사업고도화과업범위"},
        method_confirmations={method:dict(research_task_scope_note="2022관계기반발전방안연구8900만원참조",
            price_freeze_note="9000만원준용동결",recurrence_phase_note="5년계획2027첫해사례")})


def run_regression():
    p=committee_payload();q=plan_payload()
    c=estimate_routed_item(p);r=estimate_routed_item(q)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_CENTRAL_POLICY","evidence_mode":"holdout"})
    total=sum(c.annual_amounts_thousand)+sum(r.annual_amounts_thousand)
    return dict(bill_no="2215239",post_answer_regression=True,independent_evaluation=False,
        committee_payload=p,committee_result=dataclasses.asdict(c),committee_trace=web["derivationTrace"],
        plan_payload=q,plan_result=dataclasses.asdict(r),reusable_web_status=web["status"],
        annual_thousand=[a+b for a,b in zip(c.annual_amounts_thousand,r.annual_amounts_thousand)],
        total_thousand=total,gold_total_thousand=138000,error_percent=abs(total-138000)/138000*100,
        local_plan_cost=None,limitation="계획+본회의수당의정답범위회귀.지방계획/실무위등추가범위미검증,새의안독립성과아님")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
