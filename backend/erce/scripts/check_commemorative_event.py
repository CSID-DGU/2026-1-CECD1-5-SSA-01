"""Partial-cost regression with separately validated, sourced non-estimation."""
import dataclasses
import json
from backend.erce.commemorative_event_evidence import BASIS
from backend.erce.engine import estimate_routed_item
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.web_bridge import calculate_erce_web_item


def event_payload():
    method="2201850:annual_commemorative_event"
    keys=["2201850:commemorative_event:unit_cost:reviewed","2201850:commemorative_event:annual_quantity:reviewed"]
    return dict(bill_no="2201850",route_key="quantity_unit",cutoff_date="2026-10-06",evidence_mode="development_review",
        start_year=2025,years=5,service_cost_basis=BASIS,commemorative_event_scale="national_single_day_event",
        event_price_projection="freeze_reviewed_event_package",selected_evidence_keys=keys,
        evidence_selection_reasons={k:"동일국가차원학대예방기념일의과업·규모를검토한사후준용" for k in keys},
        selected_method_keys=[method],payer="government",method_selection_reasons={method:"캠페인영상이아닌기념일행사"},
        method_confirmations={method:dict(national_event_scope="국가의연간예방의날기념행사.지자체추가사업미포함",
            annual_recurrence="연1회행사가정.예방주간7일을7회로계산하지않음",historical_price_freeze="2024예산9700만원참고연1억원동결선례",
            forecast_start_basis="공포후6개월의2025~2029시작은해당정답의가정이며확정공포일아님")})


def non_estimation_payload():
    return dict(bill_no="2201850",cutoff_date="2026-10-06",evidence_mode="development_review",
        decision_evidence_key="2201850:regional_advocacy_expansion_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(existing_all_regions_covered=True,revised_population_area_rule=True,
            reliable_incremental_installation_basis_available=False,quantified_expansion_standard_available=False),
        decision_confirmations=dict(existing_regional_coverage="당시정답PDF3쪽17시도모두설치·19지역기관·경기충북각2 확인",
            incremental_plan_review="역사적정답의추가설치여부·소요재정자료부재를확인.현재모든사업계획부재를전수검색한주장아님",
            quantitative_installation_standard_review="원문인구·면적고려1개소이상은정량별추가수량을직접정하지않음"))


def run_regression():
    p=event_payload();r=estimate_routed_item(p)
    decision=validate_non_estimation_review(non_estimation_payload())
    web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_PREVENTION_EVENT","evidence_mode":"holdout"})
    similar=validate_non_estimation_review({**non_estimation_payload(),"bill_no":"SYNTHETIC_ADVOCACY_REVIEW","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)
    return dict(bill_no="2201850",post_answer_regression=True,independent_evaluation=False,
        event_payload=p,event_result=dataclasses.asdict(r),required_variables_filled=2,required_variable_count=2,
        partial_total_thousand=total,gold_partial_total_thousand=500000,difference_percent=abs(total-500000)/500000*100,
        non_estimation=decision,non_estimation_payload=non_estimation_payload(),synthetic_web_status=web["status"],
        synthetic_non_estimation=similar,local_additional_cost=None,whole_bill_total_thousand=None,
        reporting_duty_increment="review_pending",
        limitation="정답확인후연간행사·단가동결가정재사용및기관미추계사유검증.일부추계5억원,추가기관/지방행사0이라는뜻아님")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
