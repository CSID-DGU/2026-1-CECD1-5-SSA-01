import dataclasses
import json
from backend.erce.survey_annualization_evidence import PROFILE,ROUTE,survey_annualization_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def care_survey_payload():
    method="2207176:survey_annualization_delta"
    notes=dict(survey_task_scope_note="동일보호종료아동 자립지원 전국실태조사, 새매년과기존3년예산 차액",
        survey_phase_note="실시이력2023,현행3년이면2026·2029. 공포후6개월·준비기간 고려개정2026부터매년",
        survey_price_note="2023조사예산2억원에2024.12 CPI2024부터적용,정부별·연구항목별중복곱셈없음")
    keys=[r["evidence_key"] for r in survey_annualization_rows()]
    return dict(bill_no="2207176",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=ROUTE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        research_service_function="care_leaver_independent_living_survey",survey_annualization_confirmed=True,**notes,
        explicit_inputs={"existing_survey_interval":dict(value=3,unit="year",source_ref="2207176 원문PDF5쪽 현행3년"),
            "amended_survey_interval":dict(value=1,unit="year",source_ref="2207176 원문PDF3쪽 매년")},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"동일조사·기준예산년·실시이력·물가전망 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"기존주기에해당하는조사비를차감하는연례화순증"},
        method_confirmations={method:notes})


def counselling_review():
    return dict(bill_no="2207176",evidence_mode="development_review",cutoff_date="2026-10-11",
        decision_evidence_key="2207176:counselling_existing_program",reliable_estimation_basis_available=True,
        decision_facts=dict(counselling_already_provided=True,new_service_scope_or_staffing_expansion_confirmed=False),
        decision_confirmations=dict(existing_counselling_program_note="정답PDF3쪽 2024자립지원체계사업의전담인력 심리상담/사례관리 제공근거",
            counselling_scope_overlap_note="동일기존서비스·새물량이나인력확대 미명시.현행2026서비스현황 독립전수확인아닌역사적선례 적용성 검토"))


def run_regression(db_path=None):
    p=care_survey_payload();options={"variable_db_path":db_path} if db_path else {}
    if db_path:
        p["variable_db_path"]=str(db_path)
    r=estimate_routed_item(p);web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_CARE_LEAVER_SURVEY","evidence_mode":"holdout"},**options)
    annual=list(r.annual_amounts_thousand);total=sum(annual)/100000
    review=counselling_review();decision=validate_non_estimation_review(review,**({"db_path":db_path} if db_path else {}))
    return dict(bill_no="2207176",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(r),web_result=web,total_eok=total,gold_display_total_eok=6.71,
        raw_error_percent=abs(total-6.71)/6.71*100,annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,[0,218,222,0,231])),
        displayed_total_million=sum(round(x/1000) for x in annual),engine_and_web_same=annual==web["annualAmountsThousand"],
        counselling_review_payload=review,counselling_decision=decision,
        limitation="정답확인후단가·실시이력·기존사업근거 저장한회귀. 원시반올림차이를0%로표시하지않고 기존사업예산을신규추가총액에합산하지않음")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
