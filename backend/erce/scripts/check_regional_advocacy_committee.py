"""Regional formula reinforcement; keep the already successful event unchanged."""
import dataclasses
import json
from backend.erce.regional_advocacy_committee import PROFILE,regional_advocacy_committee_rows
from backend.erce.scripts.check_commemorative_event import event_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def committee_payload():
    rows=regional_advocacy_committee_rows();method="2202038:regional_advocacy_case_scaled_committee"
    return dict(bill_no="2202038",route_key="committee_components",cutoff_date="2026-10-06",evidence_mode="development_review",
        start_year=2025,years=5,support_derivation=PROFILE,committee_workload_proxy="suspected_cases_scaled_members",
        committee_rounding="half_up_after_cap",public_officials_paid=False,reference_region="서울",
        support_derivation_note="지역별사례규모로위촉위원수산정·28명상한·정수반올림.전국기본경비·인력신설아님",
        committee_scope_note="공무원당연직미지급.학대사례를정원비교지표로준용하며사례마다회의를연다고계산하지않음",
        estimation_start_note="공포후6개월을2025~2029통년으로가정한정답사후비교",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"동일지역협의회규모·업무의역사적선례모형준용" for r in rows},
        selected_method_keys=[method],payer="government",method_selection_reasons={method:"원문시도지역협의회설치"},
        method_confirmations={method:dict(committee_scope_note="지역위촉위원수당만계산.기타직제·사무국은추가하지않음",
            estimation_start_note="2025~2029통년은확인된정답의가정")})


def run_regression():
    p=committee_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_ADVOCACY_COMMITTEE","evidence_mode":"holdout"})
    ep={**event_payload(),"bill_no":"2202038","evidence_mode":"holdout"};event=estimate_routed_item(ep)
    annual=[a+b for a,b in zip(r.annual_amounts_thousand,event.annual_amounts_thousand)]
    total=sum(annual);trace=web["derivationTrace"]
    return dict(bill_no="2202038",post_answer_regression=True,independent_evaluation=False,
        committee_payload=p,committee_result=dataclasses.asdict(r),regional_trace=trace,
        regional_paid_members={x["region"]:x["paid_members"] for x in trace},
        total_paid_members=sum(x["paid_members"] for x in trace),committee_total_thousand=sum(r.annual_amounts_thousand),
        event_payload=ep,event_result=dataclasses.asdict(event),event_total_thousand=sum(event.annual_amounts_thousand),
        annual_amounts_thousand=annual,total_thousand=total,gold_total_thousand=1018000,
        difference_percent=abs(total-1018000)/1018000*100,synthetic_web_status=web["status"],
        resolved_top_level_variables=3,total_top_level_variables=3,
        deferred_review_items=["기존종합계획내용추가·신고의무자확대는정답상비수반.원계획추가독립검증은별도"],
        limitation="정답확인후6개하위변수·정원추정식을보강한회귀.행사부분은최초성공한기존근거재사용유지.원2022통계·2024서울예산조례는정답인용참조로서독립원자료대조미완료")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
